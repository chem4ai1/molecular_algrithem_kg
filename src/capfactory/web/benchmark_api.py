"""基准族 schema、节点属性、指标与模型结果列表 API。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from ..sciforge.benchmark_schema import (FAMILIES, schema_for, enum_values,
                                         FAMILY_IDS)


def families() -> Dict[str, Any]:
    return {"count": len(FAMILIES), "families": [
        {"id": k, "label": v["label"], "code": v["code"],
         "description": v["description"], "aliases": v["aliases"],
         "n_fields": len(v["fields"]),
         "fields": [{"key": kk, **vv} for kk, vv in v["fields"].items()]}
        for k, v in FAMILIES.items()]}


def family_schema(family_id: str) -> Dict[str, Any]:
    s = schema_for(family_id)
    if not s:
        raise HTTPException(404, f"未知基准族：{family_id}")
    return {**s, "enums": enum_values(family_id)}


def benchmark_node(node_id: str) -> Dict[str, Any]:
    from ..po import POGraph
    from .extraction_api import GRAPH_PATH
    g = POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists() else POGraph("v8")
    n = g.nodes.get(node_id)
    if not n:
        raise HTTPException(404, f"节点不存在：{node_id}")
    fam = n.attrs.get("schema_family") or ""
    s = schema_for(fam)
    from ..sciforge.leaderboard import CORE_FIELDS, CORE_LABELS
    fields = [{"key": k, "label": CORE_LABELS.get(k, k),
               "value": n.attrs.get(k, "unknown")}
              for k in CORE_FIELDS]
    return {"id": n.id, "label": n.label, "family": fam,
            "schema": s.get("label"), "description": s.get("description"),
            "fields": fields,
            "metrics": n.attrs.get("metrics") or [],
            "model_results": n.attrs.get("model_results") or [],
            "matrix": n.attrs.get("matrix") or {},
            "sota_by_metric": n.attrs.get("sota_by_metric") or {},
            "source_papers": n.attrs.get("source_papers") or [],
            "provenance": n.attrs.get("provenance"),
            "counts": {"metrics": len(n.attrs.get("metrics") or []),
                       "results": len(n.attrs.get("model_results") or []),
                       "models": len({r.get("model") for r in
                                      n.attrs.get("model_results") or []})}}


def report() -> Dict[str, Any]:
    p = Path("storage_cf/sciforge/benchmark_fill_report.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


_V8B = [
    ("/api/v8/benchmark/families", families, "GET", True),
    ("/api/v8/benchmark/families/{family_id}", family_schema, "GET", True),
    ("/api/v8/benchmark/node/{node_id}", benchmark_node, "GET", True),
    ("/api/v8/benchmark/report", report, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V8B:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
