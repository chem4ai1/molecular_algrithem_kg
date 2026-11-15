"""P3/P4：算法族 schema 与填充结果 API。"""
from __future__ import annotations
from typing import Any, Dict

from fastapi import HTTPException

from ..sciforge.algorithm_schema import (FAMILIES, schema_for, enum_values,
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
        raise HTTPException(404, f"未知算法族：{family_id}")
    return {**s, "enums": enum_values(family_id)}


def algorithm_schema_of(node_id: str) -> Dict[str, Any]:
    from ..po import POGraph
    from .extraction_api import GRAPH_PATH
    g = POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists() else POGraph("v8")
    n = g.nodes.get(node_id)
    if not n:
        raise HTTPException(404, f"节点不存在：{node_id}")
    fam = n.attrs.get("schema_family")
    s = schema_for(fam) if fam else {}
    return {"id": n.id, "label": n.label, "family": fam,
            "schema": s.get("label"), "description": s.get("description"),
            "fields": [{"key": k, "value": n.attrs.get(k, "unknown"),
                        "spec": v}
                       for k, v in s.get("all_fields", {}).items()]}


def library_report() -> Dict[str, Any]:
    from pathlib import Path
    import json
    p = Path("storage_cf/sciforge/algorithm_fill_report.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


_V8 = [
    ("/api/v8/algorithm/families", families, "GET", True),
    ("/api/v8/algorithm/families/{family_id}", family_schema, "GET", True),
    ("/api/v8/algorithm/node/{node_id}", algorithm_schema_of, "GET", True),
    ("/api/v8/algorithm/report", library_report, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V8 + _EXTRA:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n


def problem_centric(node_id: str) -> Dict[str, Any]:
    """算法核心卡片：任务类型 / 解决问题 / 机理 / 原论文 / 可对比基线。"""
    from ..po import POGraph
    from ..sciforge.algorithm_problem import CORE_FIELDS, CORE_LABELS
    from .extraction_api import GRAPH_PATH
    g = POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists() else POGraph("v8")
    n = g.nodes.get(node_id)
    if not n:
        raise HTTPException(404, f"节点不存在：{node_id}")
    fields = [{"key": k, "label": CORE_LABELS.get(k, k),
               "value": n.attrs.get(k, "unknown")}
              for k in CORE_FIELDS
              if k not in ("search_text",)]
    peers = [x.label for x in g.by_type("Algorithm")
             if x.id != n.id and
             x.attrs.get("task_type") == n.attrs.get("task_type")][:12]
    return {"id": n.id, "name": n.label,
            "task_type": n.attrs.get("task_type"),
            "task_type_label": n.attrs.get("task_type_label"),
            "problems_solved": n.attrs.get("problems_solved") or [],
            "mechanism": n.attrs.get("mechanism"),
            "why_it_works": n.attrs.get("why_it_works"),
            "applicable_to": n.attrs.get("applicable_to") or [],
            "limitations": n.attrs.get("limitations") or [],
            "source_paper": n.attrs.get("source_paper") or {},
            "source_ref_no": n.attrs.get("source_ref_no"),
            "filled_by": n.attrs.get("filled_by"),
            "fields": fields, "comparable_baselines": peers}


def search(q: str, top_k: int = 8, task_type: str = "") -> Dict[str, Any]:
    from ..sciforge.algorithm_problem import search_algorithms
    if not q or not q.strip():
        raise HTTPException(400, "查询不能为空")
    return search_algorithms(q, top_k=max(1, min(top_k, 20)),
                             task_type=task_type)


def task_types() -> Dict[str, Any]:
    from ..sciforge.algorithm_problem import TASK_TYPES
    return {"count": len(TASK_TYPES),
            "task_types": [{"id": k, "label": v}
                           for k, v in TASK_TYPES.items()]}


def extraction_plan() -> Dict[str, Any]:
    from ..sciforge.algorithm_problem import (EXTRACTION_PLAN,
                                              OPTIMIZATION_ADVICE)
    from ..sciforge.algorithm_schema import FAMILIES
    return {"n_families": len(FAMILIES),
            "steps": EXTRACTION_PLAN, "optimization_advice": OPTIMIZATION_ADVICE}


_EXTRA = [
    ("/api/v8/algorithm/problems/{node_id}", problem_centric, "GET", True),
    ("/api/v8/algorithm/search", search, "GET", True),
    ("/api/v8/algorithm/task-types", task_types, "GET", True),
    ("/api/v8/algorithm/extraction-plan", extraction_plan, "GET", True),
]


def register_problem_routes(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _EXTRA:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
