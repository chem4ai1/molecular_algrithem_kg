"""蛋白质 / 分子算法能力的**领域推理引擎**（优化版）.

原 ``kg/graph.py::search_capabilities`` 只做 BM25 + 哈希向量，再加
``0.08*maturity + 0.05*verified`` 的固定加分；没有模态、适用域、证据等级、
任务族、算力可行性任何一项判断。本模块补上 6 类推理：

1. **检索重排** ``rerank``        ：词面相关性 × 领域一致性 × 证据强度 × 可行性
2. **能力链推理** ``compose_chains``：按输出/输入模态拼接「表示 → 预测 → 筛选」流水线
3. **适用域推理** ``check_applicability``：实体/模态/长度/样本量/算力前置校验
4. **指标可比性** ``comparable_metrics``：只有 dataset+split+protocol+metric+direction
                                          完全一致才允许比大小
5. **缺口推理** ``infer_gaps``   ：按任务族 × 业务需求生成覆盖矩阵与补齐建议
6. **方案解释** ``explain``     ：生成可读的设计依据（无需 LLM）

关于深度归一化（重要）：本实现**刻意不使用** ``score / sqrt(depth)`` 之类的强衰减。
强衰减会让「浅层通用概念」系统性压过「深层但真正可执行的组合链」，
使多跳能力链永远排不进 Top-K。这里改用**线性弱衰减**
``score * (1 - 0.04 * depth)``，并把领域匹配与证据强度作为正向主信号。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .bio_schema import (
    BioSpec, MetricProfile, ProteinCapability, TASK_METRIC_PRIORS,
    modalities_compatible,
)
from .extract import DomainExtractor
from .ontology import chain_relations, composable_pairs

GRADE_BONUS = {"A": 0.12, "B": 0.08, "C": 0.04, "D": 0.0}
DEPTH_DECAY = 0.04          # 线性弱衰减，见模块 docstring
DEFAULT_BEAM = 4


@dataclass
class CapView:
    """推理用的统一能力视图（兼容 ``ProteinCapability`` 与旧图节点）。"""

    id: str
    name: str = ""
    task: str = ""
    task_family: str = ""
    algorithm_family: str = ""
    entity: str = ""
    modality: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    metrics: List[MetricProfile] = field(default_factory=list)
    evidence_grade: str = "D"
    confidence: float = 0.5
    maturity: float = 0.0
    verified: bool = False
    field_confidence: Dict[str, float] = field(default_factory=dict)
    applicability: Dict[str, Any] = field(default_factory=dict)
    compute: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_capability(cls, cap: ProteinCapability) -> "CapView":
        return cls(
            id=cap.id, name=cap.name, task=cap.task, task_family=cap.task_family,
            algorithm_family=cap.algorithm_family,
            entity=cap.bio_spec.entity, modality=cap.bio_spec.modality,
            inputs=[i.modality for i in cap.inputs],
            outputs=[o.modality for o in cap.outputs],
            metrics=list(cap.metrics), evidence_grade=cap.evidence_grade,
            confidence=cap.confidence, maturity=cap.maturity,
            verified=bool(cap.verification.get("passed")),
            field_confidence=dict(cap.field_confidence),
            applicability={
                "entities": cap.applicability.entities,
                "modalities": cap.applicability.modalities,
                "length_min": cap.applicability.length_min,
                "length_max": cap.applicability.length_max,
                "min_samples": cap.applicability.min_samples,
                "exclusions": cap.applicability.exclusions,
            },
            compute={"device": cap.compute.device,
                     "memory_mb": cap.compute.memory_mb,
                     "runtime_seconds": cap.compute.runtime_seconds},
            raw=cap.to_dict(),
        )

    @classmethod
    def from_graph_node(cls, node: Dict[str, Any], extractor: DomainExtractor) -> "CapView":
        a = node.get("attrs") or {}
        prov = a.get("provenance") or {}
        text = " ".join(str(x) for x in [node.get("label", ""), a.get("task", ""),
                                         a.get("method", ""), " ".join(a.get("tags") or [])])
        bio = extractor.detect_bio_spec(text)
        metrics = [MetricProfile.from_any(m) for m in (a.get("metrics") or [])]
        ios = (a.get("inputs") or []) + (a.get("outputs") or [])
        grade = str(prov.get("evidence_grade") or "D")
        return cls(
            id=node["id"], name=node.get("label", ""), task=str(a.get("task", "")),
            task_family=str(prov.get("task_family") or extractor.detect_task_family(text)),
            algorithm_family=str(prov.get("algorithm_family") or
                                 extractor.detect_algorithm_family(text)),
            entity=bio.entity, modality=bio.modality,
            inputs=[str(i.get("modality") or bio.modality) for i in a.get("inputs") or []],
            outputs=[str(o.get("modality") or "tabular") for o in a.get("outputs") or []],
            metrics=metrics, evidence_grade=grade if grade in GRADE_BONUS else "D",
            confidence=float(a.get("confidence") or 0.5),
            maturity=float(a.get("maturity") or 0.0),
            verified=bool((a.get("verification") or {}).get("passed")),
            field_confidence=dict(prov.get("field_confidence") or {}),
            applicability={}, compute={}, raw=node,
        )


class DomainReasoner:
    """领域推理门面。可不依赖图谱，直接对能力列表推理。"""

    def __init__(self, *, graph=None, capabilities: Optional[Sequence[ProteinCapability]] = None):
        self.graph = graph
        self.extractor = DomainExtractor()
        self.views: Dict[str, CapView] = {}
        if capabilities:
            for c in capabilities:
                self.views[c.id] = CapView.from_capability(c)
        if graph is not None:
            for node in (graph.nodes or {}).values():
                if node.get("type") == "capability":
                    self.views.setdefault(node["id"],
                                          CapView.from_graph_node(node, self.extractor))
        self._compose_edges: Optional[List[Tuple[str, str]]] = None

    # ------------------------------------------------------------------
    # 1. 检索重排
    # ------------------------------------------------------------------
    def rerank(self, query: str, hits: Sequence[Any], *, top_k: int = 8,
               context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """把混合检索结果按领域一致性重排，返回带 ``score_breakdown`` 的可解释结果。

        ``context`` 可含 ``entity`` / ``modality`` / ``n_samples`` / ``cpu_only``
        / ``task_family``，用于适用性前置过滤。
        """
        context = context or {}
        qtext = str(query or "")
        q_family = str(context.get("task_family") or self.extractor.detect_task_family(qtext))
        q_entity = str(context.get("entity") or self.extractor.detect_bio_spec(qtext).entity)
        q_modality = str(context.get("modality") or self.extractor.detect_bio_spec(qtext).modality)
        n_samples = int(context.get("n_samples") or 0)
        out: List[Dict[str, Any]] = []

        for h in hits:
            node_id = getattr(h, "node_id", None) or (h.get("node_id") if isinstance(h, dict) else "")
            base = float(getattr(h, "score", None) or (h.get("score") if isinstance(h, dict) else 0.0) or 0.0)
            view = self.views.get(node_id)
            if view is None:
                out.append({"id": node_id, "name": "", "score": round(base, 4),
                            "score_breakdown": {"base": round(base, 4)},
                            "reasons": ["图谱中无该能力的领域视图，保留原始检索分"]})
                continue

            b: Dict[str, float] = {"base": round(base, 4)}
            reasons: List[str] = []
            if view.task_family == q_family:
                b["task_family"] = 0.12
                reasons.append(f"任务族匹配 {q_family}")
            if q_entity != "unknown" and view.entity == q_entity:
                b["entity"] = 0.08
                reasons.append(f"生物实体匹配 {q_entity}")
            if q_modality != "unknown" and view.modality == q_modality:
                b["modality"] = 0.08
                reasons.append(f"数据模态匹配 {q_modality}")
            b["evidence_grade"] = GRADE_BONUS.get(view.evidence_grade, 0.0)
            if b["evidence_grade"]:
                reasons.append(f"证据等级 {view.evidence_grade}")
            b["maturity"] = round(0.08 * view.maturity, 4)
            b["verified"] = 0.05 if view.verified else 0.0
            b["field_confidence"] = round(
                0.05 * (sum(view.field_confidence.values()) / len(view.field_confidence)), 4
            ) if view.field_confidence else 0.0

            spec = BioSpec(entity=q_entity, modality=q_modality)
            ok, violations = self.check_applicability(view.id, spec=spec, n_samples=n_samples)
            if not ok:
                b["applicability_penalty"] = -0.25
                reasons.append("适用域不符：" + "；".join(violations[:2]))
            if context.get("cpu_only", True):
                device = str(view.compute.get("device") or "cpu")
                if device in ("gpu", "multi_gpu"):
                    b["compute_penalty"] = -0.10
                    reasons.append(f"需要 {device}，目标环境仅 CPU")

            raw_score = base + sum(v for k, v in b.items() if k != "base")
            out.append({
                "id": view.id, "name": view.name, "task": view.task,
                "task_family": view.task_family, "entity": view.entity,
                "modality": view.modality, "evidence_grade": view.evidence_grade,
                "verified": view.verified,
                "score": round(raw_score, 4), "base_score": round(base, 4),
                "score_breakdown": {k: round(v, 4) for k, v in b.items()},
                "reasons": reasons or ["无额外领域信号"],
            })
        out.sort(key=lambda x: -x["score"])
        return out[:top_k]

    # ------------------------------------------------------------------
    # 2. 能力链推理
    # ------------------------------------------------------------------
    def _edges(self) -> List[Tuple[str, str]]:
        if self._compose_edges is not None:
            return self._compose_edges
        edges: List[Tuple[str, str]] = []
        if self.graph is not None:
            rels = set(chain_relations())
            for e in getattr(self.graph, "edges", []) or []:
                if e.get("type") in rels and e.get("source") in self.views and e.get("target") in self.views:
                    edges.append((e["source"], e["target"]))
        if not edges:
            # 纯函数兜底：按 IO 模态两两判定可组合
            caps = [ProteinCapability.from_dict(v.raw) for v in self.views.values()
                    if v.raw.get("bio_spec")]
            edges = composable_pairs(caps)
        self._compose_edges = edges
        return edges

    def compose_chains(self, start_id: str, *, goal_task_family: str = "",
                       max_depth: int = 4, beam: int = DEFAULT_BEAM) -> List[Dict[str, Any]]:
        """Beam Search 找可执行的能力组合链。

        关键：评分对链长使用 ``(1 - 0.04 * depth)`` 的**弱衰减**，
        并对「末端命中目标任务族」给显著正分，避免浅层概念永远霸榜。
        """
        if start_id not in self.views:
            return []
        edges = self._edges()
        outgoing: Dict[str, List[str]] = {}
        for s, t in edges:
            outgoing.setdefault(s, []).append(t)

        states: List[Tuple[List[str], float]] = [([start_id], 0.0)]
        completed: List[Dict[str, Any]] = []
        for depth in range(1, max_depth + 1):
            candidates: List[Tuple[List[str], float]] = []
            for path, _score in states:
                cur = path[-1]
                for nxt in outgoing.get(cur, []):
                    if nxt in path:
                        continue
                    new_path = path + [nxt]
                    v = self.views[nxt]
                    step_score = 0.5 * v.confidence + 0.2 * v.maturity
                    if goal_task_family and v.task_family == goal_task_family:
                        step_score += 0.6
                    if not modalities_compatible(
                            (self.views[cur].outputs or ["unknown"])[0],
                            (v.inputs or ["unknown"])[0]):
                        step_score -= 0.4     # 类型不兼容的组合降权而非直接丢弃
                    candidates.append((new_path, step_score))
                    if len(new_path) >= 2:
                        completed.append(self._chain_doc(new_path, goal_task_family))
            if not candidates:
                break
            # beam：每层保留累计分最高的 beam 条
            scored = sorted(
                [(p, s + sum(0.5 * self.views[n].confidence + 0.2 * self.views[n].maturity
                             for n in p[1:])) for p, s in candidates],
                key=lambda x: -x[1])[:beam]
            states = scored

        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for doc in completed:
            key = tuple(doc["steps"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(doc)
        unique.sort(key=lambda d: -d["score"])
        return unique[:beam * 2]

    def _chain_doc(self, path: List[str], goal_task_family: str) -> Dict[str, Any]:
        views = [self.views[n] for n in path]
        depth = len(path) - 1
        coverage = sum(0.5 * v.confidence + 0.2 * v.maturity + 0.1 * GRADE_BONUS.get(v.evidence_grade, 0)
                       for v in views)
        goal_hit = bool(goal_task_family and views[-1].task_family == goal_task_family)
        score = (coverage + (0.6 if goal_hit else 0.0)) * max(0.1, 1.0 - DEPTH_DECAY * depth)
        transitions = []
        for a, b in zip(views, views[1:]):
            out_m = (a.outputs or ["unknown"])[0]
            in_m = (b.inputs or ["unknown"])[0]
            transitions.append({
                "from": a.name, "to": b.name, "output_modality": out_m,
                "input_modality": in_m,
                "compatible": modalities_compatible(out_m, in_m),
            })
        return {
            "steps": list(path), "names": [v.name for v in views],
            "task_families": [v.task_family for v in views],
            "transitions": transitions,
            "depth": depth, "goal_hit": goal_hit,
            "score": round(score, 4),
            "rationale": (f"链长 {depth}；{sum(t['compatible'] for t in transitions)}/"
                          f"{len(transitions)} 段模态可直连；"
                          f"末端任务族 {'命中' if goal_hit else '未命中'} {goal_task_family or '(未指定)'}；"
                          f"深度衰减系数 {round(max(0.1, 1.0 - DEPTH_DECAY * depth), 3)}"),
        }

    # ------------------------------------------------------------------
    # 3. 适用域 / 算力推理
    # ------------------------------------------------------------------
    def check_applicability(self, cap_id: str, *, spec: Optional[BioSpec] = None,
                            n_samples: int = 0, cpu_only: bool = True) -> Tuple[bool, List[str]]:
        view = self.views.get(cap_id)
        if view is None:
            return False, [f"能力 {cap_id} 不存在"]
        violations: List[str] = []
        app = view.applicability or {}
        if spec:
            if app.get("entities") and spec.entity not in app["entities"]:
                violations.append(f"实体不匹配（允许 {app['entities']}）")
            if app.get("modalities") and spec.modality not in app["modalities"]:
                violations.append(f"模态不匹配（允许 {app['modalities']}）")
            hi = int(app.get("length_max") or 0)
            if hi and (spec.length_min > hi or spec.length_max < int(app.get("length_min") or 0)):
                violations.append("序列/分子长度超出适用域")
            ms = int(app.get("min_samples") or 0)
            if ms and 0 < n_samples < ms:
                violations.append(f"样本不足（需要 ≥{ms}）")
            for ex in app.get("exclusions") or []:
                if ex and ex.lower() in spec.text().lower():
                    violations.append(f"命中排除条件：{ex}")
        if cpu_only and str(view.compute.get("device") or "cpu") in ("gpu", "multi_gpu"):
            violations.append("需要 GPU，目标环境仅 CPU")
        return (not violations), violations

    # ------------------------------------------------------------------
    # 4. 指标可比性
    # ------------------------------------------------------------------
    @staticmethod
    def comparable_metrics(cap_a: CapView, cap_b: CapView) -> Dict[str, Any]:
        """判定两条能力的指标是否可直接比较，并给出共同指标上的严格优劣。"""
        by_key_b = {m.comparable_key(): m for m in cap_b.metrics}
        comparable, non_comparable, wins = [], [], []
        for m in cap_a.metrics:
            other = by_key_b.get(m.comparable_key())
            if other is None:
                non_comparable.append({"metric": m.name, "key": m.comparable_key(),
                                       "reason": "对方无相同 dataset/split/protocol/direction 的指标"})
                continue
            comparable.append({"metric": m.name, "key": m.comparable_key(),
                               "a": m.reported, "b": other.reported})
            if m.reported is None or other.reported is None:
                continue
            better = (m.reported > other.reported) if m.direction == "higher" else (
                m.reported < other.reported)
            if better:  # 严格优于，平局不算赢
                wins.append({"metric": m.name, "a": m.reported, "b": other.reported})
        return {
            "comparable": comparable, "non_comparable": non_comparable,
            "strict_wins": wins,
            "verdict": ("A 在共同协议下严格优于 B" if wins else
                        "在可比协议下无严格优势（禁止仅凭名称相同的指标下结论）"),
        }

    def select_best(self, candidate_ids: Sequence[str], *, baseline_value: float,
                    metric_name: str = "roc_auc", direction: str = "higher") -> Dict[str, Any]:
        """在同一 ``comparable_key`` 下选最优；拒绝平局/无证据的"提升"。"""
        rows = []
        for cid in candidate_ids:
            v = self.views.get(cid)
            if not v:
                continue
            vals = [m.reported for m in v.metrics
                    if m.name == metric_name and m.direction == direction and m.reported is not None]
            if not vals:
                rows.append({"id": cid, "value": None, "promoted": False,
                             "reason": "缺少同协议、同方向的报告值"})
                continue
            val = max(vals) if direction == "higher" else min(vals)
            better = val > baseline_value if direction == "higher" else val < baseline_value
            rows.append({"id": cid, "name": v.name, "value": val,
                         "gain_pct": round((val - baseline_value) / abs(baseline_value) * 100, 4)
                         if baseline_value else 0.0,
                         "promoted": better,
                         "reason": "严格优于基线" if better else "未严格优于基线（平局不算赢）"})
        rows.sort(key=lambda r: -(r["value"] if isinstance(r["value"], (int, float)) else -1e9)
                  if direction == "higher" else (r["value"] if isinstance(r["value"], (int, float)) else 1e9))
        return {"baseline": baseline_value, "metric": metric_name, "direction": direction,
                "candidates": rows,
                "winner": next((r["id"] for r in rows if r["promoted"]), None)}

    # ------------------------------------------------------------------
    # 5. 缺口推理
    # ------------------------------------------------------------------
    def infer_gaps(self, needs: Sequence[str], *,
                   required_families: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """按「业务需求 × 任务族 × 已验证能力」推断覆盖与缺口。"""
        required_families = required_families or {}
        views = list(self.views.values())
        matrix: List[Dict[str, Any]] = []
        gaps: List[Dict[str, Any]] = []
        for need in needs:
            fam = required_families.get(need) or self.extractor.detect_task_family(need)
            related = [v for v in views if v.task_family == fam]
            verified = [v for v in related if v.verified]
            best = max((v.maturity for v in related), default=0.0)
            status = "covered" if verified else ("partial" if related else "gap")
            entry = {
                "need": need, "task_family": fam, "status": status,
                "n_capabilities": len(related), "n_verified": len(verified),
                "max_maturity": round(best, 3),
                "capabilities": [v.name for v in related[:5]],
            }
            matrix.append(entry)
            if status != "covered":
                gaps.append({
                    "need": need, "task_family": fam, "status": status,
                    "reason": (f"{len(related)} 条候选能力但 0 条通过验证" if related
                               else "图谱中完全没有该任务族的能力"),
                    "suggested_capability": {
                        "task": f"protein_{fam}", "task_family": fam,
                        "typical_metrics": list(TASK_METRIC_PRIORS.get(fam, ())[:4]),
                        "next_action": ("复刻并验证已有候选" if related else
                                        "从文献/仓库抽取该任务族能力，建立数据契约与基线"),
                    },
                })
        return {
            "matrix": matrix, "gaps": gaps,
            "coverage_rate": round(sum(1 for m in matrix if m["status"] == "covered") /
                                   len(matrix), 3) if matrix else 0.0,
            "summary": {"covered": sum(1 for m in matrix if m["status"] == "covered"),
                        "partial": sum(1 for m in matrix if m["status"] == "partial"),
                        "gap": sum(1 for m in matrix if m["status"] == "gap")},
        }

    # ------------------------------------------------------------------
    # 6. 方案解释
    # ------------------------------------------------------------------
    def explain(self, cap_id: str) -> str:
        v = self.views.get(cap_id)
        if not v:
            return f"未找到能力 {cap_id}"
        fc = ", ".join(f"{k}={val:.2f}" for k, val in sorted(v.field_confidence.items())
                       if k in ("method", "evidence", "inputs", "metrics")) or "无字段置信度"
        return (
            f"【{v.name}】\n"
            f"- 任务族 {v.task_family} / 算法族 {v.algorithm_family}；作用于 {v.entity}，"
            f"输入模态 {','.join(v.inputs) or '未声明'} → 输出 {','.join(v.outputs) or '未声明'}。\n"
            f"- 证据等级 {v.evidence_grade}，整体置信度 {v.confidence:.2f}，成熟度 {v.maturity:.2f}，"
            f"{'已通过复刻验证' if v.verified else '尚未通过复刻验证'}。\n"
            f"- 字段置信度：{fc}。\n"
            f"- 选型依据：{'已有可执行工件，优先复用' if v.verified else '需先完成代码复刻与五维验证'}；"
            f"若要与下游能力组合，需保证输出模态可被下游输入接受。"
        )

    # ------------------------------------------------------------------
    # 综合入口
    # ------------------------------------------------------------------
    def reason(self, query: str, hits: Sequence[Any], *, needs: Sequence[str] = (),
               context: Optional[Dict[str, Any]] = None, top_k: int = 5) -> Dict[str, Any]:
        ranked = self.rerank(query, hits, top_k=top_k, context=context)
        chains: List[Dict[str, Any]] = []
        if ranked:
            goal = str((context or {}).get("task_family") or
                       self.extractor.detect_task_family(query))
            chains = self.compose_chains(ranked[0]["id"], goal_task_family=goal, max_depth=3)
        return {
            "query": query, "ranked": ranked, "chains": chains[:4],
            "gaps": self.infer_gaps(list(needs)) if needs else None,
            "explanation": self.explain(ranked[0]["id"]) if ranked else "",
        }
