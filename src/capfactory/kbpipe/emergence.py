"""Other 缓冲与类型涌现：链不上时先留痕，再决定晋升什么.

为什么需要它——四类「链不上」本质不同，不能用同一个动作处理：

| 现象 | 本质 | 机制 |
|---|---|---|
| `Paper: arXiv:1802.05283v4` | **身份别名缺失** | 补 `doi/arxiv_id/aliases` 后 exact 即可；补不上则 novel |
| `ResearchProblem: Fixed-size input limitation` | **粒度错配**（论文级 vs P 类） | 归入上位类（`subsumed`），原文进 other 缓冲 |
| `Algorithm: Differentiable Neural Graph Fingerprints` | **真新实体** | novel → other 缓冲 → 证据够了晋升为实例 |
| `Task: Computing molecular fingerprints` | **命名空间不同** | novel + 建议 `task_family`，不硬并到别的论文任务 |

关键原则：**自动发现，人工晋升**。

- 类型**合法但实例缺**（`candidate_type ∈ CONCEPT_SPECS`）→ 可批量晋升为实例节点（低风险）；
- 类型**本身不存在** → 只产出 `type_proposal`，必须人工确认后才改 `CONCEPT_SPECS`
  （本体是 schema，LLM 自造类型不能直接写进去）。

缓冲按 ``other:{type}:{hash}`` 归一，同一实体的不同写法先聚类再计数，
避免「出现 1 次但换了 3 种写法」被误判为 3 个候选。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..po.concepts import CONCEPT_SPECS, Concept
from ..po.store import POGraph
from ..utils import now_iso
from .linking import LinkResult, normalize_key

# 这些类型即使链不上，也能给一个family建议（属性有上位概念）
FAMILY_OF = {
    "Algorithm": "algo_code",
    "Task": "task_family",
    "Domain": "domain_code",
}


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()[:12]


@dataclass
class OtherNode:
    """一个「链不上」的候选实体。"""

    id: str
    candidate_type: str
    label: str
    normalized: str
    papers: List[str] = field(default_factory=list)
    mentions: int = 1
    first_seen: str = ""
    last_seen: str = ""
    status: str = "candidate"        # candidate | promoted | merged | rejected
    merged_into: str = ""
    cluster: str = ""
    neighbors: List[Dict[str, Any]] = field(default_factory=list)
    best_existing: Dict[str, Any] = field(default_factory=dict)
    suggested_family: str = ""
    promoted_node_id: str = ""
    samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OtherBuffer:
    """novel 实体的持久缓冲（JSONL），支持聚类、提案与晋升。"""

    def __init__(self, path: str | Path = "storage_cf/other/other_nodes.jsonl",
                 embedder: Any = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.nodes: Dict[str, OtherNode] = {}
        self.load()

    # -- 持久化 -----------------------------------------------------------
    def load(self) -> "OtherBuffer":
        self.nodes = {}
        if self.path.exists():
            with self.path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    n = OtherNode(**{k: v for k, v in d.items()
                                     if k in OtherNode.__dataclass_fields__})
                    self.nodes[n.id] = n
        return self

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for n in self.nodes.values():
                fh.write(json.dumps(n.to_dict(), ensure_ascii=False) + "\n")

    # -- 写入 -------------------------------------------------------------
    def observe(self, res: LinkResult, *, paper_id: str = "",
                context: str = "") -> Optional[OtherNode]:
        """记录一个 novel 结果；已存在则累加提及与来源。"""
        if res.state != "novel":
            return None
        norm = normalize_key(res.source_label)
        if not norm:
            return None
        nid = f"other:{res.source_type.lower()}:{_hash(norm)}"
        now = now_iso()
        n = self.nodes.get(nid)
        if n is None:
            best = (res.candidates or [{}])[0]
            n = OtherNode(
                id=nid, candidate_type=res.source_type, label=res.source_label,
                normalized=norm, papers=[paper_id] if paper_id else [],
                mentions=1, first_seen=now, last_seen=now,
                best_existing={"id": best.get("id", ""), "score": best.get("score", 0.0),
                               "label": best.get("label", "")},
                samples=[context[:160]] if context else [],
            )
            self.nodes[nid] = n
        else:
            n.mentions += 1
            n.last_seen = now
            if paper_id and paper_id not in n.papers:
                n.papers.append(paper_id)
            if context and len(n.samples) < 3:
                n.samples.append(context[:160])
        return n

    def observe_many(self, results: Sequence[LinkResult], *,
                     papers: Optional[Dict[str, str]] = None) -> Dict[str, int]:
        added = 0
        for r in results:
            # 兼容 LinkResult 对象与 to_dict() 后的 dict
            obj = r if isinstance(r, LinkResult) else LinkResult(
                **{k: v for k, v in r.items() if k in LinkResult.__dataclass_fields__})
            n = self.observe(obj, paper_id=(papers or {}).get(obj.source_id, ""))
            added += int(n is not None)
        self.save()
        return {"observed": added, "n_nodes": len(self.nodes)}

    # -- 聚类（合并同义写法） ---------------------------------------------
    def cluster(self, *, threshold: float = 0.86) -> int:
        """同类型内按向量相似度合并「同一实体的不同写法」。"""
        if not self.embedder:
            return 0
        merged = 0
        by_type: Dict[str, List[OtherNode]] = {}
        for n in self.nodes.values():
            if n.status in ("merged", "rejected"):
                continue
            by_type.setdefault(n.candidate_type, []).append(n)
        for ctype, items in by_type.items():
            if len(items) < 2:
                continue
            try:
                import numpy as np
                mat = self.embedder.embed([n.label for n in items])
            except Exception:  # noqa: BLE001
                continue
            norm = np.linalg.norm(mat, axis=1, keepdims=True)
            norm[norm == 0] = 1.0
            mat = mat / norm
            sims = mat @ mat.T
            for i, a in enumerate(items):
                if a.status == "merged":
                    continue
                neighbors = []
                for j, b in enumerate(items):
                    if i == j or b.status == "merged":
                        continue
                    s = float(sims[i, j])
                    if s >= threshold:
                        neighbors.append({"id": b.id, "label": b.label,
                                          "score": round(s, 4)})
                        # 把提及合并到代表节点
                        a.mentions += b.mentions
                        a.papers = list(dict.fromkeys(a.papers + b.papers))
                        b.status = "merged"
                        b.merged_into = a.id
                        merged += 1
                a.neighbors = neighbors
                a.cluster = a.id
        self.save()
        return merged

    # -- 提案 -------------------------------------------------------------
    def proposals(self, *, min_mentions: int = 2) -> Dict[str, Any]:
        """产出「该晋升什么」的建议；**不自动改本体**。"""
        active = [n for n in self.nodes.values()
                  if n.status not in ("merged", "rejected")]
        by_type: Dict[str, List[OtherNode]] = {}
        for n in active:
            by_type.setdefault(n.candidate_type, []).append(n)

        instance_props: List[Dict[str, Any]] = []
        type_props: List[Dict[str, Any]] = []
        for ctype, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
            known = ctype in CONCEPT_SPECS
            strong = [n for n in items if n.mentions >= min_mentions]
            if known:
                for n in sorted(strong, key=lambda x: -x.mentions)[:8]:
                    instance_props.append({
                        "other_id": n.id, "candidate_type": ctype,
                        "label": n.label, "mentions": n.mentions,
                        "papers": n.papers[:4],
                        "nearest": n.best_existing,
                        "action": "promote_instance",
                        "reason": (f"{ctype} 是已定义概念，图内缺该实例；"
                                   f"出现 {n.mentions} 次、{len(n.papers)} 篇论文提及"),
                    })
            else:
                type_props.append({
                    "candidate_type": ctype, "n_candidates": len(items),
                    "n_mentions": sum(n.mentions for n in items),
                    "top_labels": [n.label for n in
                                   sorted(items, key=lambda x: -x.mentions)[:5]],
                    "action": "review_new_type",
                    "reason": (f"「{ctype}」不在 36 类概念内，"
                               f"可能是模型自造类型；需人工确认后才写入本体"),
                })
        # 已有类型但实例缺口很大时，也给一条类型级提示
        for ctype, items in by_type.items():
            if ctype in CONCEPT_SPECS and len(items) >= 3:
                type_props.append({
                    "candidate_type": ctype, "n_candidates": len(items),
                    "n_mentions": sum(n.mentions for n in items),
                    "top_labels": [n.label for n in
                                   sorted(items, key=lambda x: -x.mentions)[:5]],
                    "action": "consider_expanding_instances",
                    "reason": (f"{ctype} 类型合法；本轮新增 {len(items)} 个候选实体，"
                               f"建议批量晋升为实例节点（可先人工抽样复核）"),
                })
        return {
            "stats": self.stats(),
            "by_type": {k: {"n": len(v), "mentions": sum(n.mentions for n in v)}
                        for k, v in by_type.items()},
            "instance_proposals": instance_props,
            "type_proposals": type_props,
            "policy": ("已知类型缺实例 → 可批量晋升；未知类型 → 只出提案，"
                       "人工确认后才改 CONCEPT_SPECS"),
            "generated_at": now_iso(),
        }

    # -- 晋升（人工闸门） -------------------------------------------------
    def promote(self, other_id: str, graph: POGraph, *,
                node_id: str = "", node_type: str = "",
                attrs: Optional[Dict[str, Any]] = None) -> Optional[Concept]:
        """把一个候选晋升为图节点（显式调用 = 人工确认）。"""
        n = self.nodes.get(other_id)
        if n is None or n.status == "merged":
            return None
        ctype = node_type or n.candidate_type
        if ctype not in CONCEPT_SPECS:
            raise ValueError(f"{ctype} 不是已定义概念；先人工评审 type_proposal")
        nid = node_id or f"{ctype.lower()}:{_hash(n.normalized)}"
        concept = graph.node(
            nid, ctype, n.label,
            **{**(attrs or {}), "origin": "emerged_from_other",
               "other_id": n.id, "mentions": n.mentions,
               "papers": n.papers, "promoted_at": now_iso()})
        n.status = "promoted"
        n.promoted_node_id = nid
        self.save()
        return concept

    def merge_into(self, other_id: str, target_id: str, *, reason: str = "") -> None:
        n = self.nodes.get(other_id)
        if n:
            n.status = "merged"
            n.merged_into = target_id
            n.samples.append(f"merged->{target_id} {reason}"[:160])
            self.save()

    def reject(self, other_id: str, *, reason: str = "") -> None:
        n = self.nodes.get(other_id)
        if n:
            n.status = "rejected"
            n.samples.append(f"rejected: {reason}"[:160])
            self.save()

    # -- 观察 -------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        from collections import Counter
        st = Counter(n.status for n in self.nodes.values())
        return {"n_total": len(self.nodes), "by_status": dict(st),
                "by_type": dict(Counter(n.candidate_type for n in self.nodes.values()
                                        if n.status != "merged")),
                "promotable": sum(1 for n in self.nodes.values()
                                  if n.status == "candidate" and n.mentions >= 2),
                "path": str(self.path)}
