"""CapFactory Web 服务（v6）。

页面（v8 标准化）：
``/``                  主界面
``/data``              数据工作台（论文/算法/数据三库属性与分类树）
``/relations``         关系浏览器（左实例列表 + 右按链分组关系）
``/pipeline``          Pipeline 长 DAG
``/pipeline/extract``  论文抽取（各阶段输入/输出/链/原文溯源）

``/data/graph`` 已废弃，302 重定向到 ``/relations``（图谱视图已砍掉）。
旧入口 /po /domain /algograph /extraction 统一回主界面；旧 API 见 web/_legacy。
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..config import REPO_ROOT
from ..utils import setup_logging
from .home_api import register as register_home_routes
from .home_api import home_summary

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CapFactory", version="6.0.0",
              description="论文知识图谱 × 复现流水线")

# v6 路由用显式注册（兼容 FastAPI 0.135–0.162+）
register_home_routes(app)

# 显式注册清单（唯一权威）。失败不再静默吞：记录到 app.state 供 /api/status 排查。
WEB_API_MODULES = ("data_api", "graph_api", "pg_api", "extract_v7",
                   "algorithm_api", "benchmark_api", "relation_api",
                   "tbox_api", "provenance_api", "repro_api",
                   "nx_api", "paperapp_api")
app.state.api_registration_errors = {}
for _mod in WEB_API_MODULES:
    try:
        _m = __import__(f"capfactory.web.{_mod}", fromlist=["register"])
        _m.register(app)
    except Exception as _exc:              # noqa: BLE001
        app.state.api_registration_errors[_mod] = (
            f"{type(_exc).__name__}:{_exc}"[:200])

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _page(name: str) -> HTMLResponse:
    p = STATIC_DIR / name
    if not p.exists():
        return HTMLResponse(f"<!doctype html><meta charset=utf-8>"
                            f"<p>页面缺失：{name}</p>", status_code=500)
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _page("home.html")


@app.get("/data", response_class=HTMLResponse)
def data_page() -> HTMLResponse:
    return _page("data.html")


@app.get("/data/graph")
def graph_page():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/relations", status_code=302)


@app.get("/pipeline", response_class=HTMLResponse)
def pipeline_page() -> HTMLResponse:
    return _page("pipeline.html")


@app.get("/pipeline/extract", response_class=HTMLResponse)
def extract_page() -> HTMLResponse:
    return _page("pipeline_extract.html")


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    s = home_summary()
    errs = getattr(app.state, "api_registration_errors", {})
    return {"ok": not errs, "root": str(REPO_ROOT), **s,
            "api_registration_errors": errs}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "root": str(REPO_ROOT), "version": "6.0.0"}


# 旧入口统一回到主界面，避免继续干扰当前图谱
_LEGACY_PATHS = ("/po", "/domain", "/algograph", "/extraction",
                 "/api/v5/extraction")


@app.get("/po")
@app.get("/domain")
@app.get("/algograph")
@app.get("/extraction")
@app.get("/api/v5/extraction")
def legacy_redirect() -> RedirectResponse:
    return RedirectResponse("/", status_code=301)


def main() -> None:
    import uvicorn
    ap = argparse.ArgumentParser(description="CapFactory Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    setup_logging("INFO")
    uvicorn.run("capfactory.web.server:app", host=args.host, port=args.port,
                reload=args.reload)


if __name__ == "__main__":
    main()
