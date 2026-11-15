"""PO 图结构校验（Python 版 SHACL 关键约束 + 报告 §7 全链覆盖）.

对照 ``constraints.shacl.ttl``：
- MetricObservation: ``OF_METRIC`` max/min 1、``HAS_CONDITION`` ≥1、
  ``SUPPORTED_BY`` ≥1、``unit`` max/min 1、``value`` 与 ``missingState`` xone；
- Evidence: ``EXTRACTED_FROM`` max/min 1、``locator`` max/min 1；
- CapabilityClaim: ``ABOUT_METHOD`` / ``SUPPORTED_BY`` / ``EVALUATED_IN`` ≥1；
- 所有边：关系类型合法、domain/range 合法、无悬空端点。

报告 §10「开放世界与校验分离」：**未出现边不等于事实为假**，
所以这里只报告结构违规与「未声明」，不下生物学结论。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence, Set

from .concepts import RELATION_DOMAIN_RANGE
from .vocab import default_registry

# SHACL 最小基数约束：concept type -> [(relation, min, max)]
SHAPE_CARDINALITY: Dict[str, Sequence[tuple]] = {
    "MetricObservation": (("OF_METRIC", 1, 1), ("HAS_CONDITION", 1, None),
                          ("SUPPORTED_BY", 1, None)),
    "Evidence": (("EXTRACTED_FROM", 1, 1),),
    "CapabilityClaim": (("ABOUT_METHOD", 1, None), ("SUPPORTED_BY", 1, None),
                        ("EVALUATED_IN", 1, None)),
    "EvaluationRun": (("USES_METRIC", 1, None), ("PRODUCES_OBSERVATION", 1, None)),
    "Dataset": (("HAS_SPLIT", 0, None),),
    "PaperVersion": (("CORRECTED_BY", 0, 1),),
}

# 报告 §8 的「20 篇全链覆盖」检查路径
FULL_CHAIN = (
    ("Paper", "FORMULATES", "ResearchQuestion"),
    ("ResearchQuestion", "OPERATIONALIZED_AS", "Task"),
    ("Task", "ADDRESSED_BY", "Algorithm"),
    ("Paper", "HAS_CLAIM", "CapabilityClaim"),
    ("CapabilityClaim", "EVALUATED_IN", "EvaluationRun"),
    ("EvaluationRun", "PRODUCES_OBSERVATION", "MetricObservation"),
    ("MetricObservation", "SUPPORTED_BY", "Evidence"),
)


def validate_po_graph(graph: Any, registry=None, *,
                      strict_chain: bool = False) -> List[str]:
    """返回结构违规列表（空 = 通过）。"""
    reg = registry or default_registry
    problems: List[str] = []
    nodes: Dict[str, Any] = graph.nodes
    edges: List[Any] = graph.assertions

    # 1) 节点契约
    for n in nodes.values():
        problems.extend(f"[{n.id}] {p}" for p in n.validate(reg))
    if len({n.id for n in nodes.values()}) != len(nodes):
        problems.append("存在重复节点 ID")

    # 2) 边：类型 / domain-range / 端点 / 归属 / 证据
    for e in edges:
        _, ok = reg.normalize("relation_type", e.relation)
        if not ok:
            problems.append(f"[{e.id}] 未知关系类型 {e.relation!r}")
        if e.source not in nodes or e.target not in nodes:
            problems.append(f"[{e.id}] 悬空端点 {e.source} -> {e.target}")
            continue
        spec = RELATION_DOMAIN_RANGE.get(e.relation)
        if spec:
            src_t, dst_t = nodes[e.source].type, nodes[e.target].type
            if src_t not in spec[0]:
                problems.append(f"[{e.id}] {e.relation} 源类型应为 {spec[0]}，实际 {src_t}")
            if dst_t not in spec[1]:
                problems.append(f"[{e.id}] {e.relation} 目标类型应为 {spec[1]}，实际 {dst_t}")
        _, aok = reg.normalize("attribution", e.attribution)
        if not aok:
            problems.append(f"[{e.id}] 非法 attribution {e.attribution!r}")
        for evid in e.evidence_ids:
            if evid not in nodes:
                problems.append(f"[{e.id}] 引用了不存在的证据 {evid}")

    # 3) SHACL 基数约束（按出边计算）
    out_rel: Dict[str, Counter] = defaultdict(Counter)
    for e in edges:
        out_rel[e.source][e.relation] += 1
    for n in nodes.values():
        for rel, lo, hi in SHAPE_CARDINALITY.get(n.type, ()):
            cnt = out_rel[n.id][rel]
            if cnt < lo:
                problems.append(f"[{n.id}] {n.type} 缺少 {rel}（需要 ≥{lo}，实际 {cnt}）")
            if hi is not None and cnt > hi:
                problems.append(f"[{n.id}] {n.type} 的 {rel} 超过 {hi} 条")

    # 4) 归属语义：论文—问题边必须携带三种语义之一，且 attribution 明确
    paper_problem = {"ADDRESSES", "EXPOSES_LIMITATION", "ANALYST_RELEVANT_TO"}
    for e in edges:
        if e.relation in paper_problem and nodes[e.target].type == "ResearchProblem":
            if e.attribution in ("", "unknown"):
                problems.append(f"[{e.id}] 论文—问题边缺少明确归属")
    pp_count = sum(1 for e in edges if e.relation in paper_problem)
    if not pp_count and any(n.type == "Paper" for n in nodes.values()):
        problems.append("图中没有任何论文—问题关联边（ADDRESSES/EXPOSES_LIMITATION/ANALYST_RELEVANT_TO）")

    # 5) 全链覆盖（报告 §8）
    if strict_chain:
        for src_t, rel, dst_t in FULL_CHAIN:
            have = any(e.relation == rel and nodes[e.source].type == src_t
                       and nodes[e.target].type == dst_t
                       for e in edges if e.source in nodes and e.target in nodes)
            if not have:
                problems.append(f"全链缺失环节 {src_t} -{rel}-> {dst_t}")

    # 6) 可比性：同名指标观测若可比键不同，只记提示，不阻断结构校验
    return problems
