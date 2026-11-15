"""图引擎 API：networkx 适配层（统计 / 邻居 / 最短路 / 导出）。"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

_EXPORT = Path("storage/sciforge/exports")


def _graph(name: str):
    from .graph_source import load
    try:
        return load(name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"未知图：{name}（{type(exc).__name__}）")


def nx_stats(graph: str = "semantic") -> Dict[str, Any]:
    from ..po.nx_adapter import stats
    return stats(_graph(graph))


def nx_neighbors(node_id: str, hops: int = 1,
                 graph: str = "semantic") -> Dict[str, Any]:
    from ..po.nx_adapter import neighbours
    hops = max(1, min(int(hops), 4))
    return neighbours(_graph(graph), node_id, hops)


def nx_shortest(src: str, dst: str,
                graph: str = "semantic") -> Dict[str, Any]:
    from ..po.nx_adapter import shortest_path
    return shortest_path(_graph(graph), src, dst)


def nx_export(graph: str = "semantic", fmt: str = "graphml"):
    from ..po.nx_adapter import export
    from fastapi.responses import FileResponse
    fmt = (fmt or "graphml").lower()
    if fmt not in ("graphml", "gexf", "json"):
        raise HTTPException(400, "fmt 只支持 graphml / gexf / json")
    _EXPORT.mkdir(parents=True, exist_ok=True)
    out = _EXPORT / f"{graph}.{fmt}"
    info = export(_graph(graph), str(out), fmt)
    return FileResponse(str(out), filename=out.name,
                        media_type="application/octet-stream",
                        headers={"X-Graph-Nodes": str(info["n_nodes"]),
                                 "X-Graph-Edges": str(info["n_edges"])})


_V9 = [
    ("/api/v9/graph/nx/stats", nx_stats, "GET", True),
    ("/api/v9/graph/nx/neighbors/{node_id}", nx_neighbors, "GET", True),
    ("/api/v9/graph/nx/shortest", nx_shortest, "GET", True),
    ("/api/v9/graph/nx/export", nx_export, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V9:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
