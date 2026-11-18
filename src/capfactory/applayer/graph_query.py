"""B 类图谱 → C 类决策的查询层。

每条查询返回 (value, evidence)，evidence 记录「这个值从哪个图节点/边查出来的」，
使决策可追溯，而不是手写常量。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


def _source_of(graph, node_id: str, rel: str) -> List[str]:
    return [a.source for a in graph.incoming(node_id, rel)]


def _targets(graph, node_id: str, rel: str) -> List[str]:
    return [a.target for a in graph.outgoing(node_id, rel)]


def query_evaluation_norm(graph, evidence_type: str) -> Dict[str, Any]:
    """④ 用：按证据类型查领域规范。返回规范值 + 来源节点。"""
    matches = [n for n in graph.by_type("EvaluationNorm")
               if n.attrs.get("evidence_type") == evidence_type]
    if not matches:
        return {"found": False, "evidence_type": evidence_type,
                "min_fidelity": "qualitative", "source": None,
                "note": "无对应 EvaluationNorm，回落 qualitative"}
    n = matches[0]
    return {"found": True, "evidence_type": evidence_type,
            "min_fidelity": n.attrs.get("min_fidelity"),
            "accepted_metrics": list(n.attrs.get("accepted_metrics") or []),
            "n_papers": n.attrs.get("n_papers"),
            "source": n.id,
            "via": "DERIVED_FROM_PAPERS"}


def query_frontier_baseline(graph, task_type: str = "") -> Dict[str, Any]:
    """② 用：从 MethodLineage 查前沿基线（方法数最多的族谱末端）。"""
    lineages = [n for n in graph.by_type("MethodLineage")
                if not task_type or n.attrs.get("task_type") == task_type]
    if not lineages:
        return {"found": False, "baseline": "unknown", "source": None}
    top = max(lineages, key=lambda n: n.attrs.get("n") or 0)
    methods = list(top.attrs.get("methods") or [])
    # 从方法 id 反查 label
    labels = [graph.nodes[m].label for m in methods if m in graph.nodes]
    return {"found": True, "baseline": " / ".join(labels[:3]) or methods[0] if methods else "unknown",
            "n_methods": top.attrs.get("n"), "source": top.id,
            "via": "LINEAGE_OF", "task_type": top.attrs.get("task_type")}


def query_failure_checks(graph, paper_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """⑦ 用：从 FailureModeLibrary 查本次相关的失败模式。"""
    libs = graph.by_type("FailureModeLibrary")
    if not libs:
        return {"found": False, "checks": [], "source": None}
    lib = libs[0]
    limits = list(lib.attrs.get("limitations") or [])
    negs = list(lib.attrs.get("negative_results") or [])
    if paper_ids:
        related = [a.source for a in graph.assertions
                   if a.relation == "FAILURE_SEEN_IN" and a.target in paper_ids]
    else:
        related = []
    return {"found": True, "checks": limits[:5] + negs[:3],
            "n_limitations": len(limits), "n_negative": len(negs),
            "related_papers": related, "source": lib.id, "via": "FAILURE_SEEN_IN"}


def query_venue_profile(graph, venue: str = "") -> Dict[str, Any]:
    """⑧⑨ 用：查 venue 惯例；unknown 时如实返回 found=False。"""
    profiles = [n for n in graph.by_type("VenueProfile")
                if n.attrs.get("venue") == venue] if venue else graph.by_type("VenueProfile")
    if not profiles or all(p.attrs.get("venue") == "unknown" for p in profiles):
        return {"found": False, "venue": venue or "unknown",
                "citation_style": "unknown", "section_pattern": [],
                "source": profiles[0].id if profiles else None,
                "note": "无 venue 元数据，不伪造惯例"}
    p = profiles[0]
    return {"found": True, "venue": p.attrs.get("venue"),
            "citation_style": p.attrs.get("citation_style"),
            "section_pattern": list(p.attrs.get("section_pattern") or []),
            "source": p.id, "via": "VENUE_OF"}
