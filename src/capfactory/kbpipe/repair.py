"""抽取图的确定性修复：关系方向纠正、悬空证据剪除、词表补登记.

LLM 抽出来的三元组有三类高频错误，都能用规则修掉（不需要重跑模型）：

1. **关系方向反了**：``Algorithm -ADDRESSES-> Task``，而 schema 是
   ``Paper -ADDRESSES-> ResearchProblem``、``Task -ADDRESSED_BY-> Algorithm``。
   这类可以**无损反向**（``ADDRESSED_BY`` 是 ``ADDRESSES`` 的逆），直接纠正；
2. **编造证据 ID**：``evidence:Fig1a`` 图里不存在 → 剪除引用并记账，
   不删整条边（边本身可能有效，只是证据没对齐）；
3. **语义不匹配**：``CapabilityClaim -ABOUT_SUBJECT-> Dataset`` 没有合法反向，
   只能丢弃并记 ``dropped``，避免污染图。

原则：**能纠正就纠正，不能纠正就丢弃并留痕**，绝不静默通过。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ..po.concepts import RELATION_DOMAIN_RANGE
from ..po.store import POGraph

# 可无损反向的关系：value 是反向关系名
INVERSE_REPAIR: Dict[str, str] = {
    "ADDRESSES": "ADDRESSED_BY",
    "ADDRESSED_BY": "ADDRESSES",
    "HAS_CLAIM": "ABOUT_METHOD",
    "CONTAINS": "PART_OF",
}


def _type_ok(graph: POGraph, nid: str, allowed: Tuple[str, ...]) -> bool:
    n = graph.nodes.get(nid)
    if n is None:
        return False
    return not allowed or n.type in allowed


def repair_graph(graph: POGraph, *, evidence_ns: str = "evidence:",
                 drop_unknown_relations: bool = True) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"assertions_before": len(graph.assertions),
                             "reversed": 0, "dropped": 0,
                             "evidence_trimmed": 0, "evidence_removed": 0,
                             "kept": 0, "reasons": Counter(), "samples": []}
    known_evidence = {n.id for n in graph.by_type("Evidence")}
    keep = []
    for a in graph.assertions:
        spec = RELATION_DOMAIN_RANGE.get(a.relation)
        if spec is None:
            if drop_unknown_relations:
                stats["dropped"] += 1
                stats["reasons"][f"unknown_relation:{a.relation}"] += 1
                continue
        else:
            dom, rng = spec
            ok = _type_ok(graph, a.source, tuple(dom)) and _type_ok(graph, a.target, tuple(rng))
            if not ok:
                inv = INVERSE_REPAIR.get(a.relation)
                if inv and inv in RELATION_DOMAIN_RANGE:
                    idom, irng = RELATION_DOMAIN_RANGE[inv]
                    if (_type_ok(graph, a.target, tuple(idom))
                            and _type_ok(graph, a.source, tuple(irng))):
                        a.source, a.target = a.target, a.source
                        a.relation = inv
                        a.properties["repaired"] = "reversed"
                        stats["reversed"] += 1
                        keep.append(a)
                        continue
                stats["dropped"] += 1
                stats["reasons"][f"type_mismatch:{a.relation}"] += 1
                if len(stats["samples"]) < 8:
                    stats["samples"].append(
                        {"rel": a.relation, "src": a.source, "tgt": a.target,
                         "why": "type_mismatch"})
                continue
        # 证据剪枝：只保留图里真实存在的 Evidence 节点
        if a.evidence_ids and known_evidence:
            kept = [e for e in a.evidence_ids
                    if e in known_evidence or not str(e).startswith(evidence_ns)]
            if len(kept) != len(a.evidence_ids):
                stats["evidence_trimmed"] += 1
                stats["evidence_removed"] += len(a.evidence_ids) - len(kept)
            a.evidence_ids = kept[:8]
        keep.append(a)
        stats["kept"] += 1
    graph.assertions[:] = keep

    # 节点侧：同样剪掉悬空的 evidence_ids
    for n in graph.nodes.values():
        if n.evidence_ids and known_evidence:
            kept = [e for e in n.evidence_ids
                    if e in known_evidence or not str(e).startswith(evidence_ns)]
            if len(kept) != len(n.evidence_ids):
                stats["evidence_trimmed"] += 1
                n.evidence_ids = kept[:8]
    stats["assertions_after"] = len(graph.assertions)
    stats["reasons"] = dict(stats["reasons"])
    return stats


def add_vocab_aliases(registry: Any, pairs: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    """把抽取中真实出现、但规范名不同的写法登记为别名（不新增规范值）。"""
    added: Dict[str, int] = {}
    for name, mapping in pairs.items():
        try:
            vocab = registry.get(name)
        except KeyError:
            continue
        n = 0
        for raw, canonical in mapping.items():
            if canonical in vocab.values and raw not in vocab.aliases:
                vocab.aliases[raw] = canonical
                n += 1
        if n:
            added[name] = n
    return added
