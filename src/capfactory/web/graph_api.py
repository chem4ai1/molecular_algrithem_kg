"""P2 图谱：论文 / 算法 / 数据三视图（同一张图 + 边白名单过滤）。"""
from __future__ import annotations
from typing import Any, Dict, List, Set

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .data_api import _graph, node_card
from .extraction_api import STATIC_DIR

VIEWS: Dict[str, Dict[str, Any]] = {
    "paper": {
        "label": "论文关系",
        "rels": {"RELATED_TO", "ADDRESSES", "EVALUATED_ON", "REPORTS",
                 "PROPOSES_METHOD", "HAS_CODE", "CITES_PAPER", "BROADER",
                 "HAS_SECTION"},
        "types": {"Paper", "ResearchQuestion", "ProblemCategory",
                  "Benchmark", "CodeRepository", "SourcePaper"}},
    "algorithm": {
        "label": "算法关系",
        "rels": {"PROPOSES_METHOD", "HAS_MODULE_DETAIL", "HAS_STEP",
                 "HAS_FORMULA", "USES_TOOL", "REALIZED_BY",
                 "HAS_MODULE_IMPL", "IMPLEMENTS_MODULE", "PARTICIPATES_IN",
                 "APPLIES_TO"},
        "types": {"Paper", "Algorithm", "AlgorithmStep", "Formula", "Tool",
                  "CodeFunction", "CodeModule", "CodeRepository"}},
    "data": {
        "label": "数据关系",
        "rels": {"EVALUATED_ON", "REPORTS", "REPORTS_VALUE", "USES_METRIC",
                 "OF_METRIC", "HAS_DATA_CONTRACT", "HAS_INPUT_FORM",
                 "HAS_OUTPUT_FORM", "HAS_INPUT_OBJECT", "HAS_OUTPUT_OBJECT",
                 "ADDRESSES", "BROADER", "BINDS_EVAL_TOOL"},
        "types": {"Paper", "Benchmark", "MetricDefinition",
                  "MetricObservation", "Observation", "DataContract",
                  "DataForm", "ResearchObject", "EvaluationTool",
                  "ProblemCategory", "ResearchQuestion"}},
}

_STYLE = {"Paper": "paper", "Algorithm": "method", "AlgorithmStep": "method",
          "Formula": "method", "Tool": "method", "CodeFunction": "code",
          "CodeModule": "code", "CodeRepository": "code",
          "Benchmark": "benchmark", "MetricDefinition": "benchmark",
          "MetricObservation": "benchmark", "Observation": "benchmark",
          "DataContract": "benchmark", "DataForm": "benchmark",
          "ResearchObject": "benchmark", "ResearchQuestion": "main_chain",
          "ProblemCategory": "main_chain", "SourcePaper": "tech_tree"}


def graph_view(view: str = "paper", focus: str = "", limit: int = 260
               ) -> Dict[str, Any]:
    if view not in VIEWS:
        raise HTTPException(400, f"未知视图：{view}")
    spec = VIEWS[view]
    g = _graph()
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for a in g.assertions:
        if a.relation not in spec["rels"]:
            continue
        s, t = g.nodes.get(a.source), g.nodes.get(a.target)
        if not s or not t:
            continue
        if s.type not in spec["types"] or t.type not in spec["types"]:
            continue
        for n in (s, t):
            nodes[n.id] = {"id": n.id, "label": n.label[:44], "type": n.type,
                           "style": _STYLE.get(n.type, "main_chain")}
        edges.append({"source": a.source, "target": a.target,
                      "rel": a.relation})
        if len(edges) >= limit * 3:
            break
    if focus and focus in g.nodes:
        keep = {focus}
        for e in edges:
            if e["source"] == focus or e["target"] == focus:
                keep |= {e["source"], e["target"]}
        for e in edges:
            if e["source"] in keep or e["target"] in keep:
                keep |= {e["source"], e["target"]}
        nodes = {k: v for k, v in nodes.items() if k in keep}
        edges = [e for e in edges if e["source"] in nodes
                 and e["target"] in nodes]
    nl = list(nodes.values())[:limit]
    keep_ids = {n["id"] for n in nl}
    el = [e for e in edges if e["source"] in keep_ids
          and e["target"] in keep_ids]
    return {"view": view, "label": spec["label"],
            "nodes": nl, "edges": el[:limit * 2],
            "stats": {"n_nodes": len(nl), "n_edges": len(el),
                      "types": sorted({n["type"] for n in nl})}}


def views_meta() -> Dict[str, Any]:
    g = _graph()
    out = []
    for k, v in VIEWS.items():
        cnt = sum(1 for n in g.nodes.values() if n.type in v["types"])
        out.append({"id": k, "label": v["label"], "types": sorted(v["types"]),
                    "node_count": cnt, "rels": sorted(v["rels"])})
    return {"views": out}


def graph_page() -> RedirectResponse:
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/relations", status_code=302)


_V8 = [
    ("/api/v6/graph", graph_view, "GET", True),
    ("/api/v6/graph/views", views_meta, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, ep, method, ins in _V8:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        added += 1
    return added
