"""P4 关系浏览器 API：左列表 + 右按链分组关系，替代图谱。"""
from __future__ import annotations
from typing import Any, Dict

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from .extraction_api import GRAPH_PATH, STATIC_DIR


def _graph():
    from ..po import POGraph
    # 关系浏览器只读语义层（应用层按任务另行构建）
    from .graph_source import load as _load_source
    return _load_source("semantic")


def views() -> Dict[str, Any]:
    from ..sciforge.relation_layer import CHAIN_SPECS
    return {"views": [{"id": k, "label": v["label"],
                       "chains": [{"id": c, "label": s["label"],
                                   "color": s["color"]}
                                  for c, s in v["chains"].items()]}
                      for k, v in CHAIN_SPECS.items()]}


def instances(view: str = "paper", q: str = "", limit: int = 200
              ) -> Dict[str, Any]:
    from ..sciforge.relation_layer import instances as _inst
    return _inst(_graph(), view, q, limit)


def relations(node_id: str, view: str = "paper") -> Dict[str, Any]:
    from ..sciforge.relation_layer import relations_for
    d = relations_for(node_id, view)
    n = _graph().nodes.get(node_id)
    if n:
        # 节点溯源卡片 + 单元格级溯源
        try:
            from ..semantic.provenance import trace
            t = trace(_graph(), node_id)
            d["provenance"] = {
                "traced": t.get("traced", False),
                "papers": [{"id": x["paper_id"],
                            "title": x.get("title", ""),
                            "relation": x["relation"],
                            "arxiv_id": x.get("arxiv_id", "")}
                           for x in t.get("relations", [])[:8]],
                "paper_id_attr": t.get("paper_id_attr") or "",
                "report_hits": t.get("report_hits", [])[:8],
                "n_cells": t.get("n_cells", 0),
                "cells": t.get("cells", [])[:12]}
        except Exception:
            d["provenance"] = {"traced": False, "papers": [],
                               "n_cells": 0, "cells": []}
        d["label"] = n.label
        d["type"] = n.type
        d["attrs"] = {k: v for k, v in n.attrs.items()
                      if k in ("research_problem", "domain", "problem_type",
                               "algorithm_family", "task_type_label",
                               "mechanism", "input_form", "output_form",
                               "n_samples", "scale")}
    return d


def rebuild() -> Dict[str, Any]:
    from ..sciforge.relation_layer import build_relations
    return build_relations(_graph(), persist=True)


def relations_page() -> HTMLResponse:
    p = STATIC_DIR / "relations.html"
    if not p.exists():
        raise HTTPException(500, "relations.html 缺失")
    return HTMLResponse(p.read_text(encoding="utf-8"))


_V8R = [
    ("/api/v8/relations/views", views, "GET", True),
    ("/api/v8/relations/instances", instances, "GET", True),
    ("/api/v8/relations/rebuild", rebuild, "POST", True),
    ("/api/v8/relations/node/{node_id}", relations, "GET", True),
    ("/relations", relations_page, "GET", False),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V8R:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
