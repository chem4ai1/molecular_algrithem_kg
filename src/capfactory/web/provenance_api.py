"""溯源 API：单节点追踪 / 审计 / 缺失论文 CSV / 向量检索。"""
from __future__ import annotations
from typing import Any, Dict, List

from fastapi import HTTPException


def provenance_node(node_id: str) -> Dict[str, Any]:
    from ..po import POGraph
    from ..semantic.provenance import SEM_GRAPH, trace
    g = POGraph.load(str(SEM_GRAPH))
    r = trace(g, node_id)
    if not r.get("found"):
        raise HTTPException(404, "节点不存在：" + node_id)
    return r


def provenance_audit() -> Dict[str, Any]:
    from ..po import POGraph
    from ..semantic.provenance import SEM_GRAPH, audit
    g = POGraph.load(str(SEM_GRAPH))
    a = audit(g)
    return {"catalog_size": a["catalog_size"], "n_reports": a["n_reports"],
            "by_type": {k: {x: v[x] for x in
                            ("total", "traced_by_relation",
                             "traced_by_attr_only", "preset_kb",
                             "no_clue", "coverage", "repairable")}
                        for k, v in a["by_type"].items()}}


def provenance_missing(kind: str = "all") -> Dict[str, Any]:
    from ..po import POGraph
    from ..semantic.provenance import SEM_GRAPH, CSV_FIELDS, audit
    g = POGraph.load(str(SEM_GRAPH))
    a = audit(g)
    out = {}
    for k in ("Algorithm", "Benchmark"):
        if kind not in ("all", k.lower()):
            continue
        out[k] = {"n": len(a["by_type"][k]["missing"]),
                  "fields": list(CSV_FIELDS),
                  "rows": a["by_type"][k]["missing"][:200]}
    return out


def provenance_export() -> Dict[str, Any]:
    from ..po import POGraph
    from ..semantic.provenance import (SEM_GRAPH, export_missing_csv,
                                       build_index)
    g = POGraph.load(str(SEM_GRAPH))
    r = export_missing_csv(g)
    idx = build_index(g)
    return {"csv": r["csv"], "n_missing": r["n_missing"],
            "report": r["report_path"], "index": idx}


def vector_search(q: str, k: int = 10,
                  types: str = "") -> List[Dict[str, Any]]:
    from ..semantic.vector_sync import search
    tl = [x for x in types.split(",") if x] or None
    return search(q or "", types=tl, k=min(max(k, 1), 50))


def provenance_refresh() -> Dict[str, Any]:
    """一条命令重算全部派生层（溯源修正后调用）。"""
    from ..semantic.refresh import refresh_all
    r = refresh_all()
    return {"ok": r["ok"], "graph": r["graph"],
            "n_missing": r["steps"]["missing_csv"]["n_missing"],
            "repair": r["steps"]["repair"]["n"],
            "vector": r["steps"].get("vector", {}).get("count"),
            "application": r["steps"].get("application", {}).get("nodes")}


def batch_status() -> Dict[str, Any]:
    """全量抽取进度（断点续跑状态）。"""
    from ..semantic.batch_extract import status
    return status()


def vector_stats() -> Dict[str, Any]:
    from ..semantic.vector_sync import stats
    return stats()


_V8 = [
    ("/api/v8/provenance/node/{node_id}", provenance_node, "GET", True),
    ("/api/v8/provenance/audit", provenance_audit, "GET", True),
    ("/api/v8/provenance/missing", provenance_missing, "GET", True),
    ("/api/v8/provenance/export", provenance_export, "POST", True),
    ("/api/v8/provenance/refresh", provenance_refresh, "POST", True),
    ("/api/v8/provenance/vector-search", vector_search, "GET", True),
    ("/api/v8/provenance/vector-stats", vector_stats, "GET", True),
    ("/api/v8/extraction/batch-status", batch_status, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V8:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
