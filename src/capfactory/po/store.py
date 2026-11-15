"""PO 图容器：概念节点 + 带来源的断言（Assertion reification）.

对应报告 ``graph_seed.json / nodes.csv / edges.csv``：每条边都是
``assertion:NNNN``，带 ``evidenceIds`` 与 ``attribution``，即 RDF reification
在属性图里的落地。这样「分析者关联」不会被误读成「作者声明」。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils import now_iso
from .comparability import compare_observations
from .concepts import CONCEPT_CLASSES, DIMENSIONS, Concept, RELATION_DOMAIN_RANGE
from .validation import validate_po_graph
from .vocab import default_registry


@dataclass
class Assertion:
    """一条带来源的断言（属性图边的 reification）。"""

    id: str
    source: str
    target: str
    relation: str
    attribution: str = "analyst_synthesis"
    evidence_ids: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Assertion":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


class POGraph:
    """问题导向知识图谱（可与主 KnowledgeGraph 并行存在）。"""

    def __init__(self, graph_id: str = ""):
        self.graph_id = graph_id or f"po::{now_iso()}"
        self.nodes: Dict[str, Concept] = {}
        self.assertions: List[Assertion] = []
        self._keys: set = set()
        self.meta: Dict[str, Any] = {"schema_version": "po_v1", "created_at": now_iso(),
                                     "source": "问题导向本体与知识图谱架构_20261109"}

    # -- 写入 -------------------------------------------------------------
    def add(self, concept: Concept) -> Concept:
        if concept.id in self.nodes:
            self.nodes[concept.id].attrs.update(concept.attrs)
            if concept.label:
                self.nodes[concept.id].label = concept.label
        else:
            self.nodes[concept.id] = concept
        return self.nodes[concept.id]

    def node(self, cid: str, ctype: str, node_label: str = "", **attrs: Any) -> Concept:
        # 形参刻意叫 node_label：让 ``label`` 作为普通属性进入 attrs，
        # 避免与 Molecule / Endpoint 等以 label 为必填字段的概念冲突。
        a = dict(attrs)
        label = node_label or str(a.get("label") or cid)
        a.setdefault("label", label)
        attribution = a.pop("attribution", "analyst_synthesis")
        evidence_ids = a.pop("evidence_ids", [])
        source_version = a.pop("source_version", "")
        missing_states = a.pop("missing_states", {})
        return self.add(Concept(id=cid, type=ctype, label=label, attrs=a,
                                attribution=attribution, evidence_ids=list(evidence_ids),
                                source_version=source_version,
                                missing_states=dict(missing_states)))

    def assert_rel(self, source: str, target: str, relation: str, *,
                   attribution: str = "analyst_synthesis",
                   evidence_ids: Sequence[str] = (),
                   assertion_id: str = "", **properties: Any) -> bool:
        if source not in self.nodes or target not in self.nodes:
            return False
        key = (source, target, relation)
        if key in self._keys:
            return False
        self._keys.add(key)
        self.assertions.append(Assertion(
            id=assertion_id or f"assertion:{len(self.assertions)+1:04d}",
            source=source, target=target, relation=relation,
            attribution=attribution, evidence_ids=list(evidence_ids),
            properties=dict(properties)))
        return True

    # -- 查询 -------------------------------------------------------------
    def by_type(self, ctype: str) -> List[Concept]:
        return [n for n in self.nodes.values() if n.type == ctype]

    def _ensure_adj(self) -> None:
        """惰性邻接索引：断言列表变化（含整体替换）时自动重建。
        原来 outgoing/incoming 每次全扫 assertions，6000 节点图上前端树
        要扫数千万次；建索引后 O(1) 查表。
        """
        sig = (len(self.assertions), id(self.assertions))
        if (getattr(self, "_adj_sig", None) == sig
                and getattr(self, "_adj_out", None) is not None):
            return
        out: Dict[Any, List[Assertion]] = {}
        inn: Dict[Any, List[Assertion]] = {}
        for e in self.assertions:
            out.setdefault((e.source, e.relation), []).append(e)
            out.setdefault((e.source, ""), []).append(e)
            inn.setdefault((e.target, e.relation), []).append(e)
            inn.setdefault((e.target, ""), []).append(e)
        self._adj_out, self._adj_in, self._adj_sig = out, inn, sig

    def outgoing(self, cid: str, relation: str = "") -> List[Assertion]:
        self._ensure_adj()
        return list(self._adj_out.get((cid, relation), ()))

    def incoming(self, cid: str, relation: str = "") -> List[Assertion]:
        self._ensure_adj()
        return list(self._adj_in.get((cid, relation), ()))

    def neighbours(self, cid: str, hops: int = 1) -> List[Tuple[str, int]]:
        seen, q, out = {cid}, deque([(cid, 0)]), []
        while q:
            cur, d = q.popleft()
            if d >= hops:
                continue
            for e in self.assertions:
                nxt = e.target if e.source == cur else (e.source if e.target == cur else "")
                if nxt and nxt not in seen:
                    seen.add(nxt)
                    out.append((nxt, d + 1))
                    q.append((nxt, d + 1))
        return out

    def stats(self) -> Dict[str, Any]:
        by_type = Counter(n.type for n in self.nodes.values())
        by_rel = Counter(e.relation for e in self.assertions)
        by_dim: Counter = Counter()
        for n in self.nodes.values():
            from .concepts import CONCEPT_SPECS
            by_dim[CONCEPT_SPECS[n.type].dimension if n.type in CONCEPT_SPECS else "other"] += 1
        return {
            "graph_id": self.graph_id, "n_nodes": len(self.nodes),
            "n_assertions": len(self.assertions),
            "nodes_by_type": dict(by_type), "assertions_by_relation": dict(by_rel),
            "nodes_by_dimension": dict(by_dim),
            "problem_categories": by_type.get("ProblemCategory", 0),
            "research_problems": by_type.get("ResearchProblem", 0),
            "metric_observations": by_type.get("MetricObservation", 0),
            "evidence": by_type.get("Evidence", 0),
            "validation_problems": self.validate(),
        }

    def validate(self) -> List[str]:
        return validate_po_graph(self, default_registry)

    # -- 报告 §7 Competency Questions --------------------------------------
    def competency_questions(self) -> Dict[str, Any]:
        """把报告 §7 的 12 个 CQ 落成可执行查询（能回答的给答案，不能的显式说明）。"""
        out: Dict[str, Any] = {}
        papers = self.by_type("Paper")

        # CQ1：P06 下三类论文—问题边
        p06_ids = ({n.id for t in ("ResearchProblem", "ProblemCategory")
                    for n in self.by_type(t) if "P06" in n.id}
                   | {"problem:P06"})
        cq1: Dict[str, List[str]] = {"ADDRESSES": [], "EXPOSES_LIMITATION": [],
                                    "ANALYST_RELEVANT_TO": []}
        for e in self.assertions:
            if e.relation in cq1 and e.target in p06_ids:
                cq1[e.relation].append(e.source)
        out["CQ1_problem_P06_relation_types"] = {k: sorted(set(v)) for k, v in cq1.items()}

        # CQ2：能力主张属于算法还是完整流程 + 证据版本
        claims = []
        for c in self.by_type("CapabilityClaim"):
            methods = [e.target for e in self.outgoing(c.id, "ABOUT_METHOD")]
            versions = sorted({self.nodes[ev].attrs.get("paper_version_id", "")
                               for e in self.outgoing(c.id, "SUPPORTED_BY")
                               for ev in [e.target] if ev in self.nodes})
            claims.append({"claim": c.id, "methods": methods,
                           "method_types": [self.nodes[m].type for m in methods if m in self.nodes],
                           "evidence_versions": versions})
        out["CQ2_claim_method_and_version"] = claims[:20]

        # CQ3：同名指标观测可比性
        groups: Dict[str, List[Concept]] = defaultdict(list)
        for o in self.by_type("MetricObservation"):
            groups[str(o.attrs.get("metric") or o.label)].append(o)
        conflicts = []
        for metric, obs in groups.items():
            for i, a in enumerate(obs):
                for b in obs[i + 1:]:
                    r = compare_observations(a, b)
                    if not r["comparable"]:
                        conflicts.append({"metric": metric, "a": a.id, "b": b.id,
                                          "blocking": [d["dimension"] for d in
                                                       r["blocking_differences"]][:6]})
        out["CQ3_incomparable_pairs"] = conflicts[:20]
        out["CQ3_n_incomparable_pairs"] = len(conflicts)

        # CQ4：命中率分母（selection stage）
        out["CQ4_selection_stages"] = [
            {"id": s.id, "stage": s.attrs.get("stage_type") or s.attrs.get("stage"),
             "count": s.attrs.get("count"), "unit": s.attrs.get("unit")}
            for s in self.by_type("SelectionStage")]

        # CQ5：IC50 的 pH/底物条件
        ic50 = []
        for o in self.by_type("MetricObservation"):
            if str(o.attrs.get("metric", "")).upper() == "IC50":
                conds = [self.nodes[e.target].attrs for e in self.outgoing(o.id, "HAS_CONDITION")
                         if e.target in self.nodes]
                ic50.append({"id": o.id, "value": o.attrs.get("value"),
                             "unit": o.attrs.get("unit"),
                             "conditions": [{k: v for k, v in c.items()
                                            if k in ("pH", "substrate", "system", "dose")}
                                           for c in conds]})
        out["CQ5_IC50_conditions"] = ic50

        # CQ6：证据层级分布
        out["CQ6_modality_distribution"] = dict(Counter(
            str(o.attrs.get("modality", "unknown")) for o in self.by_type("MetricObservation")))

        # CQ8：共享平台（非独立复现）
        out["CQ8_evidence_families"] = [
            {"id": f.id, "label": f.label, "basis": f.attrs.get("basis"),
             "members": [e.source for e in self.incoming(f.id, "MEMBER_OF")]}
            for f in self.by_type("EvidenceFamily")]

        # CQ9：缺失状态统计（缺失 ≠ false）
        missing: Counter = Counter()
        for n in self.nodes.values():
            for v in n.missing_states.values():
                missing[str(v)] += 1
            if n.attrs.get("missing_state"):
                missing[str(n.attrs["missing_state"])] += 1
        out["CQ9_missing_state_distribution"] = dict(missing)

        # CQ11：代码/权重/数据三轴开放性
        out["CQ11_openness"] = {
            t: dict(Counter(str(n.attrs.get("availability", "unknown"))
                            for n in self.by_type(t)))
            for t in ("CodeArtifact", "WeightArtifact", "DataArtifact")}

        # CQ7/CQ10/CQ12 需要更完整的分子/条件/目标实例，明确说明覆盖边界
        out["coverage_note"] = (
            "报告 §7 已声明：种子未全面抽取 MoleculeState/Organism/所有阴性结果，"
            "CQ7(同源重叠)、CQ10(联合证据)、CQ12(暴露方向) 需补录实例后才能完整回答；"
            "查询不到不等于论文没做。")
        return out

    # -- 序列化 -----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {"meta": {**self.meta, "stats": self.stats()},
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "assertions": [e.to_dict() for e in self.assertions]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "POGraph":
        g = cls(str((d.get("meta") or {}).get("graph_id", "")))
        g.meta = dict(d.get("meta") or {})
        for n in d.get("nodes", []):
            g.add(Concept.from_dict(n))
        for e in d.get("assertions", []):
            a = Assertion.from_dict(e)
            key = (a.source, a.target, a.relation)
            if key not in g._keys and a.source in g.nodes and a.target in g.nodes:
                g._keys.add(key)
                g.assertions.append(a)
        return g

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "POGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def project_to_main_graph(self, kg: Any) -> Dict[str, int]:
        """把 PO 节点投影进主 ``KnowledgeGraph``（需 domain/ontology 已注册类型）。"""
        added = 0
        allowed = set(kg.NODE_TYPES) if hasattr(kg, "NODE_TYPES") else None
        for n in self.nodes.values():
            if allowed is not None and n.type not in allowed:
                continue
            before = len(kg.nodes)
            kg.add_node(n.id, n.type, n.label,
                        **{k: v for k, v in n.attrs.items()
                           if not isinstance(v, (list, dict))},
                        attribution=n.attribution)
            added += len(kg.nodes) - before
        e_before = len(kg.edges)
        for e in self.assertions:
            if e.source in kg.nodes and e.target in kg.nodes:
                kg.add_edge(e.source, e.target, e.relation, evidence=", ".join(e.evidence_ids))
        return {"nodes_added": added, "edges_added": len(kg.edges) - e_before}
