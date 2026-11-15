"""能力知识图谱.

节点类型：``paper`` / ``capability`` / ``dataset`` / ``metric`` / ``task`` /
``artifact`` / ``lesson`` / ``direction``。

关系类型：``PROPOSES`` / ``APPLIES_TO`` / ``EVALUATED_BY`` / ``USES_DATASET`` /
``SIMILAR_TO`` / ``REALIZED_BY`` / ``FAILED_WITH`` / ``SUGGESTS`` / ``DEPENDS_ON``。

图谱同时承担三件事：
1. **存储**：能力、论文、验证结果的唯一事实来源（JSON 落盘，可版本化）；
2. **去重与融合**：同一能力被多篇论文提出时合并证据、提升置信度；
3. **图增强检索**：为方案规划提供相似能力与跳数邻居。
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..config import Settings, get_settings
from ..schema import Artifact, Capability, Lesson, PaperRecord, ResearchDirection, VerificationReport
from ..utils import now_iso, read_json, short_hash, write_json
from .retrieval import HybridIndex, SearchHit

try:  # 领域本体扩展是可选的，缺失时退回基础 8 类节点
    from ..domain.ontology import ALL_NODE_TYPES as _DOMAIN_NODE_TYPES
except Exception:  # pragma: no cover
    _DOMAIN_NODE_TYPES = ()

logger = logging.getLogger(__name__)

NODE_TYPES = {"paper", "capability", "dataset", "metric", "task",
              "artifact", "lesson", "direction"} | set(_DOMAIN_NODE_TYPES)


class KnowledgeGraph:
    """可增量构建、可持久化的能力知识图谱。"""

    def __init__(self, settings: Optional[Settings] = None, path: Optional[Path] = None):
        self.settings = settings or get_settings()
        self.path = Path(path) if path else self.settings.path("kg_dir") / "graph.json"
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self._edge_keys: Set[Tuple[str, str, str]] = set()
        self._adj: Optional[Dict[str, List[Tuple[str, str]]]] = None
        self._index: Optional[HybridIndex] = None
        self._index_size = -1

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------
    def add_node(self, node_id: str, node_type: str, label: str, **attrs: Any) -> str:
        if node_type not in NODE_TYPES:
            raise ValueError(f"未知节点类型：{node_type}")
        if node_id in self.nodes:
            self.nodes[node_id].setdefault("attrs", {}).update(attrs)
            self.nodes[node_id]["label"] = label or self.nodes[node_id]["label"]
        else:
            self.nodes[node_id] = {
                "id": node_id, "type": node_type, "label": label,
                "attrs": attrs, "created_at": now_iso(),
            }
        self._index = None
        return node_id

    def add_edge(self, source: str, target: str, rel: str, weight: float = 1.0,
                 evidence: str = "") -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        key = (source, target, rel)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append({
            "source": source, "target": target, "type": rel,
            "weight": round(float(weight), 3), "evidence": evidence[:300],
            "created_at": now_iso(),
        })
        self._adj = None

    # ------------------------------------------------------------------
    # 实体写入
    # ------------------------------------------------------------------
    def add_paper(self, paper: PaperRecord) -> str:
        pid = self.add_node(
            paper.id, "paper", paper.title,
            abstract=paper.abstract[:1200], year=paper.year, url=paper.url,
            arxiv_id=paper.arxiv_id, repo_url=paper.repo_url,
            research_object=paper.research_object, background=paper.background,
            progress=paper.progress, contributions=paper.contributions[:6],
            limitations=paper.limitations[:6], datasets=paper.datasets[:6],
            metrics=paper.metrics[:8], source=paper.source,
        )
        if paper.research_object:
            tid = f"task::{short_hash(paper.research_object, length=6)}"
            self.add_node(tid, "task", paper.research_object[:80])
            self.add_edge(pid, tid, "STUDIES", 1.0)
        for ds in paper.datasets[:6]:
            name = ds.split("(")[0].strip()[:60] if isinstance(ds, str) else str(ds)[:60]
            if not name:
                continue
            did = f"dataset::{short_hash(name.lower(), length=8)}"
            self.add_node(did, "dataset", name)
            self.add_edge(pid, did, "USES_DATASET", 1.0)
        return pid

    def add_capability(self, cap: Capability, paper_id: Optional[str] = None,
                       dedup: bool = True) -> Tuple[str, bool]:
        """写入能力节点，返回 ``(id, merged)``。"""
        if dedup:
            existing = self.find_similar_capability(cap)
            if existing:
                merged = self._merge_capability(existing, cap)
                if paper_id:
                    self.add_edge(paper_id, merged, "PROPOSES", 0.8)
                return merged, True

        self.add_node(
            cap.id, "capability", cap.name,
            summary=cap.summary, category=cap.category, task=cap.task,
            method=cap.method, inputs=[asdict(i) for i in cap.inputs],
            outputs=[asdict(o) for o in cap.outputs],
            metrics=[asdict(m) for m in cap.metrics],
            conditions=cap.conditions, constraints=cap.constraints,
            dependencies=cap.dependencies,
            evidence=[asdict(e) for e in cap.evidence],
            tags=cap.tags, confidence=cap.confidence, maturity=cap.maturity,
            version=cap.version, provenance=cap.provenance,
            verification=cap.verification, artifact_ids=cap.artifact_ids,
            created_at=cap.created_at, updated_at=cap.updated_at,
        )
        # 只为主任务建节点（标签保留在属性里），避免 task 节点爆炸
        if cap.task:
            tid = f"task::{short_hash(cap.task.lower(), length=6)}"
            self.add_node(tid, "task", cap.task)
            self.add_edge(cap.id, tid, "APPLIES_TO", 1.0)
        for m in cap.metrics[:6]:
            if not m.name:
                continue
            mid = f"metric::{m.name.lower()}"
            self.add_node(mid, "metric", m.name)
            self.add_edge(cap.id, mid, "EVALUATED_BY", 0.7,
                          evidence=f"reported={m.reported}")
        if paper_id:
            self.add_edge(paper_id, cap.id, "PROPOSES", 1.0)
        return cap.id, False

    def _merge_capability(self, existing_id: str, cap: Capability) -> str:
        """合并同一能力的多次抽取结果。"""
        node = self.nodes[existing_id]
        attrs = node["attrs"]
        attrs["version"] = int(attrs.get("version", 1)) + 1
        attrs["confidence"] = round(max(float(attrs.get("confidence", 0)), cap.confidence), 3)
        attrs["maturity"] = round(max(float(attrs.get("maturity", 0)), cap.maturity), 3)
        # 证据去重合并
        old_evidence = attrs.get("evidence") or []
        seen = {e.get("quote", "")[:80] for e in old_evidence}
        for e in cap.evidence:
            if e.quote[:80] not in seen:
                old_evidence.append(asdict(e))
                seen.add(e.quote[:80])
        attrs["evidence"] = old_evidence[:12]
        attrs["constraints"] = list(dict.fromkeys((attrs.get("constraints") or []) + cap.constraints))[:10]
        attrs["conditions"] = list(dict.fromkeys((attrs.get("conditions") or []) + cap.conditions))[:10]
        attrs["tags"] = list(dict.fromkeys((attrs.get("tags") or []) + cap.tags))[:10]
        # 报告指标取最优
        metrics = {m.get("name"): m for m in (attrs.get("metrics") or []) if m.get("name")}
        for m in cap.metrics:
            if not m.name:
                continue
            cur = metrics.get(m.name)
            if cur is None or (m.reported or 0) > (cur.get("reported") or 0):
                metrics[m.name] = asdict(m)
        attrs["metrics"] = list(metrics.values())[:8]
        # 更详细的方法描述优先保留更长的
        if len(cap.method or "") > len(attrs.get("method") or ""):
            attrs["method"] = cap.method
        provenance = attrs.setdefault("provenance", {})
        provenance.setdefault("merged_papers", [])
        paper = cap.provenance.get("paper_title", "")
        if paper and paper not in provenance["merged_papers"]:
            provenance["merged_papers"].append(paper)
        attrs["updated_at"] = now_iso()
        node["label"] = attrs.get("label") or node["label"]
        self._index = None
        logger.info("能力合并：%s ← %s（version=%s）", node["label"], cap.name, attrs["version"])
        return existing_id

    def add_artifact(self, artifact: Artifact) -> str:
        self.add_node(
            artifact.id, "artifact", f"{artifact.entry} @ {artifact.capability_id}",
            **artifact.to_dict(),
        )
        self.add_edge(artifact.capability_id, artifact.id, "REALIZED_BY", 1.0)
        return artifact.id

    def add_verification(self, report: VerificationReport) -> None:
        node_id = f"verification::{report.id}"
        self.add_node(
            node_id, "artifact", f"验证报告 {report.id}",
            passed=report.passed, score=report.overall_score,
            metrics=report.metrics.get("values", {}),
            failures=report.failures, created_at=report.created_at,
        )
        self.add_edge(report.artifact_id, node_id, "VERIFIED_BY", 1.0)
        self.add_edge(report.capability_id, node_id, "VERIFIED_BY",
                      round(report.overall_score, 3))

    def add_lesson(self, lesson: Lesson) -> str:
        self.add_node(
            lesson.id, "lesson", lesson.symptom[:80],
            root_cause=lesson.root_cause, fix=lesson.fix,
            error_signature=lesson.error_signature,
            occurrences=lesson.occurrences, created_at=lesson.created_at,
        )
        self.add_edge(lesson.capability_id, lesson.id, "FAILED_WITH", 1.0)
        return lesson.id

    def add_direction(self, direction: ResearchDirection) -> str:
        self.add_node(
            direction.id, "direction", direction.title,
            gap=direction.gap, rationale=direction.rationale,
            priority=direction.priority, difficulty=direction.difficulty,
            experiments=direction.experiments,
        )
        for cap_id in direction.supporting_capabilities:
            if cap_id in self.nodes:
                self.add_edge(direction.id, cap_id, "DEPENDS_ON", 0.6)
        return direction.id

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def remove_nodes_of_type(self, node_type: str) -> int:
        """删除某一类节点及其关联边（用于重建派生数据，如研究方向）。"""
        ids = {nid for nid, n in self.nodes.items() if n["type"] == node_type}
        if not ids:
            return 0
        for nid in ids:
            self.nodes.pop(nid, None)
        before = len(self.edges)
        self.edges = [e for e in self.edges if e["source"] not in ids and e["target"] not in ids]
        self._edge_keys = {(e["source"], e["target"], e["type"]) for e in self.edges}
        self._adj = None
        self._index = None
        return before - len(self.edges)

    def capabilities(self) -> List[Dict[str, Any]]:
        return [n for n in self.nodes.values() if n["type"] == "capability"]

    def papers(self) -> List[Dict[str, Any]]:
        return [n for n in self.nodes.values() if n["type"] == "paper"]

    def get(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def neighbours(self, node_id: str, hops: int = 1) -> List[Tuple[str, int]]:
        """返回 ``(node_id, hop)`` 列表。"""
        adj = self._adjacency()
        seen = {node_id: 0}
        queue = deque([(node_id, 0)])
        out: List[Tuple[str, int]] = []
        while queue:
            cur, d = queue.popleft()
            if d >= hops:
                continue
            for nxt, _rel in adj.get(cur, []):
                if nxt in seen:
                    continue
                seen[nxt] = d + 1
                out.append((nxt, d + 1))
                queue.append((nxt, d + 1))
        return out

    def _adjacency(self) -> Dict[str, List[Tuple[str, str]]]:
        if self._adj is not None:
            return self._adj
        adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for e in self.edges:
            adj[e["source"]].append((e["target"], e["type"]))
            adj[e["target"]].append((e["source"], e["type"]))
        self._adj = adj
        return adj

    def build_index(self) -> HybridIndex:
        """为能力节点建立混合检索索引（带缓存）。"""
        caps = self.capabilities()
        if self._index is not None and self._index_size == len(caps):
            return self._index
        items = []
        for c in caps:
            a = c["attrs"]
            text = "\n".join(filter(None, [
                c["label"], a.get("summary", ""), a.get("task", ""),
                a.get("method", ""), " ".join(a.get("tags") or []),
                " ".join(a.get("conditions") or []),
            ]))
            items.append((c["id"], text, {"label": c["label"], "task": a.get("task", ""),
                                          "maturity": a.get("maturity", 0)}))
        idx = HybridIndex(dim=int(self.settings.kg.get("embedding_dim", 512)))
        idx.build(items)
        self._index, self._index_size = idx, len(caps)
        return idx

    def search_capabilities(self, query: str, top_k: int = 8,
                            graph_boost: bool = True) -> List[SearchHit]:
        """检索能力；``graph_boost`` 时对高 maturity / 已验证节点加权。"""
        idx = self.build_index()
        hits = idx.search(query, top_k=max(top_k * 2, top_k))
        if graph_boost:
            for h in hits:
                node = self.nodes.get(h.node_id, {})
                attrs = node.get("attrs", {})
                bonus = 0.08 * float(attrs.get("maturity", 0) or 0)
                if attrs.get("verification", {}).get("passed"):
                    bonus += 0.05
                h.graph_bonus = round(bonus, 4)
                h.score = round(h.score + bonus, 4)
            hits.sort(key=lambda h: -h.score)
        return hits[:top_k]

    def find_similar_capability(self, cap: Capability) -> Optional[str]:
        """按（任务 + 名称/方法相似度）判定是否与已有能力重复。"""
        thr = float(self.settings.kg.get("dedup_similarity", 0.9))
        idx = self.build_index()
        if not idx.ids:
            return None
        query = f"{cap.name}\n{cap.task}\n{cap.method}"
        for hit in idx.search(query, top_k=5):
            node = self.nodes[hit.node_id]
            attrs = node["attrs"]
            same_task = (attrs.get("task", "").strip().lower() == cap.task.strip().lower())
            sim = hit.vector  # 用向量相似度衡量语义重复
            if (same_task and sim >= thr) or sim >= min(0.99, thr + 0.06):
                logger.info("判定重复：%s ≈ %s (sim=%.3f, same_task=%s)",
                            cap.name, node["label"], sim, same_task)
                return hit.node_id
        return None

    def landscape(self, limit: int = 40) -> List[Dict[str, Any]]:
        """给研究方向分析用的能力全景（精简）。"""
        caps = sorted(self.capabilities(),
                      key=lambda n: (-float(n["attrs"].get("maturity", 0) or 0),
                                     -float(n["attrs"].get("confidence", 0) or 0)))
        out = []
        for c in caps[:limit]:
            a = c["attrs"]
            out.append({
                "name": c["label"], "task": a.get("task", ""),
                "category": a.get("category", ""),
                "maturity": round(float(a.get("maturity", 0) or 0), 2),
                "confidence": round(float(a.get("confidence", 0) or 0), 2),
                "verified": bool(a.get("verification", {}).get("passed")),
                "constraints": (a.get("constraints") or [])[:3],
            })
        return out

    def stats(self) -> Dict[str, Any]:
        by_type = Counter(n["type"] for n in self.nodes.values())
        rel = Counter(e["type"] for e in self.edges)
        caps = self.capabilities()
        verified = [c for c in caps if c["attrs"].get("verification", {}).get("passed")]
        maturities = [float(c["attrs"].get("maturity", 0) or 0) for c in caps]
        tasks = Counter(c["attrs"].get("task", "unknown") for c in caps)
        return {
            "nodes": dict(by_type),
            "edges": dict(rel),
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "n_capabilities": len(caps),
            "n_papers": by_type.get("paper", 0),
            "n_verified": len(verified),
            "avg_maturity": round(sum(maturities) / len(maturities), 3) if maturities else 0.0,
            "top_tasks": tasks.most_common(8),
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path else self.path
        write_json(target, {
            "meta": {"created_at": now_iso(), "stats": self.stats(),
                     "schema_version": "1.0"},
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        })
        logger.info("图谱已保存：%s（%d 节点 / %d 边）", target, len(self.nodes), len(self.edges))
        return target

    def load(self, path: Optional[Path] = None) -> "KnowledgeGraph":
        target = Path(path) if path else self.path
        data = read_json(target)
        if not data:
            logger.warning("图谱文件不存在或为空：%s", target)
            return self
        for node in data.get("nodes", []):
            self.nodes[node["id"]] = node
        for edge in data.get("edges", []):
            key = (edge["source"], edge["target"], edge["type"])
            if key not in self._edge_keys:
                self._edge_keys.add(key)
                self.edges.append(edge)
        self._adj = None
        self._index = None
        logger.info("图谱已加载：%s（%d 节点 / %d 边）", target, len(self.nodes), len(self.edges))
        return self
