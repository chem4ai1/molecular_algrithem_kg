"""PG 榜单与 facet API（P3）：Benchmark 表格、数据树分类维度。"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from .extraction_api import GRAPH_PATH

_LOCK = threading.Lock()
_IMPORTED: Dict[str, float] = {}


def _ensure_imported() -> Dict[str, Any]:
    """首次访问时把主图导入 PG（幂等，按文件 mtime 判断）。"""
    from ..sciforge.pgstore import import_graph
    from ..po import POGraph
    if not GRAPH_PATH.exists():
        return {"ok": False, "reason": "graph missing"}
    mtime = GRAPH_PATH.stat().st_mtime
    with _LOCK:
        if abs(_IMPORTED.get("mtime", 0) - mtime) < 1:
            return {"ok": True, "cached": True}
        stats = import_graph(POGraph.load(str(GRAPH_PATH)))
        _IMPORTED["mtime"] = mtime
        return {"ok": True, "cached": False, **stats}


def pg_status() -> Dict[str, Any]:
    from ..sciforge import pgstore
    try:
        conn = pgstore.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) n FROM kg.entity")
                e = cur.fetchone()["n"]
                cur.execute("SELECT count(*) n FROM kg.result")
                r = cur.fetchone()["n"]
                cur.execute("SELECT count(*) n FROM kg.mv_benchmark_columns")
                b = cur.fetchone()["n"]
        finally:
            conn.close()
        return {"ok": True, "dsn": f"{pgstore.DSN['host']}:{pgstore.DSN['port']}"
                                   f"/{pgstore.DSN['dbname']}",
                "counts": {"entity": e, "result": r, "benchmarks_with_values": b}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:200]}


def benchmark_overview() -> Dict[str, Any]:
    from ..sciforge.pgstore import overview
    if not _ensure_imported().get("ok"):
        raise HTTPException(503, "PG 不可用")
    ov = overview()
    return {"count": len(ov["benchmarks"]),
            "benchmarks": [{"id": b["id"], "name": b["name"],
                            "n_models": len(b["models"] or []),
                            "n_metrics": len(b["metrics"] or []),
                            "n_values": b["n_values"]} for b in ov["benchmarks"]]}


def benchmark_table(benchmark_id: str, limit: int = 40) -> Dict[str, Any]:
    from ..sciforge.pgstore import leaderboard
    if not _ensure_imported().get("ok"):
        raise HTTPException(503, "PG 不可用")
    try:
        return leaderboard(benchmark_id, limit=limit)
    except KeyError:
        raise HTTPException(404, f"基准不存在：{benchmark_id}")


def data_facets() -> Dict[str, Any]:
    from ..sciforge.pgstore import facets
    if not _ensure_imported().get("ok"):
        raise HTTPException(503, "PG 不可用")
    return {"facets": facets()}


_V9 = [
    ("/api/v6/pg/status", pg_status, "GET", True),
    ("/api/v6/benchmark/overview", benchmark_overview, "GET", True),
    ("/api/v6/benchmark/{benchmark_id}/leaderboard", benchmark_table, "GET", True),
    ("/api/v6/data/facets", data_facets, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, ep, method, ins in _V9:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        added += 1
    return added
