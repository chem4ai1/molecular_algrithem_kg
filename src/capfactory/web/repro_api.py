"""复现生命周期 API：四环节状态、单环节触发、产物明细、完整性校验。"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

BASE = Path("storage/repro_test")
RUNS = Path("storage/repro_runs")
FILES = {"lock": "METHOD_LOCK.json", "codegen": "CODE_PLAN.json",
         "execute": "EXECUTION_LOG.json", "anchor": "CLAIM_ANCHORS.json"}


def _ws(aid: str) -> Path:
    # 新四环节工作区优先（repro_test），其次旧 repro_runs
    for p in (BASE / aid, RUNS / aid, RUNS / "regression" / aid):
        if p.exists():
            return p
    raise HTTPException(404, "未找到复现工作区：" + aid)


def papers() -> Dict[str, Any]:
    """按 arxiv_id 去重；四个环节齐全的工作区优先。"""
    import json as _json
    seen: Dict[str, Dict[str, Any]] = {}
    for root in (BASE, RUNS, RUNS / "regression"):
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            spec = d / "REPRO_SPEC.json"
            if not d.is_dir() or not spec.exists():
                continue
            try:
                aid = str(_json.loads(spec.read_text(encoding="utf-8"))
                          .get("arxiv_id") or d.name)
            except Exception:  # noqa: BLE001
                aid = d.name
            stages = sorted(k for k, f in FILES.items() if (d / f).exists())
            row = {"arxiv_id": aid, "workspace": str(d),
                   "has_lifecycle": (d / "LIFECYCLE.json").exists(),
                   "stages": stages}
            old = seen.get(aid)
            if old is None or len(stages) > len(old["stages"]):
                seen[aid] = row
    return {"papers": sorted(seen.values(), key=lambda x: x["arxiv_id"]),
            "count": len(seen)}


def status(aid: str) -> Dict[str, Any]:
    from ..reprospec.lifecycle import stage_status
    return stage_status(_ws(aid))


def lifecycle(aid: str) -> Dict[str, Any]:
    p = _ws(aid) / "LIFECYCLE.json"
    if not p.exists():
        raise HTTPException(404, "尚未运行完整生命周期")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


def _stage_doc(aid: str, stage: str) -> Dict[str, Any]:
    import json
    p = _ws(aid) / FILES[stage]
    if not p.exists():
        raise HTTPException(404, f"{stage} 尚未产出")
    d = json.loads(p.read_text(encoding="utf-8"))
    if stage == "anchor":
        d = dict(d)
        d["claims"] = (d.get("claims") or [])[:200]
    return d


def method_lock(aid: str) -> Dict[str, Any]:
    return _stage_doc(aid, "lock")


def code_plan(aid: str) -> Dict[str, Any]:
    return _stage_doc(aid, "codegen")


def execution(aid: str) -> Dict[str, Any]:
    return _stage_doc(aid, "execute")


def anchors(aid: str) -> Dict[str, Any]:
    return _stage_doc(aid, "anchor")


def verify(aid: str) -> Dict[str, Any]:
    from ..reprospec.lifecycle import verify_lifecycle
    return verify_lifecycle(_ws(aid))


def run(aid: str, stage: str = "all", effort: str = "lite") -> Dict[str, Any]:
    """stage=all 跑四环节；否则只重跑该环节（依赖前序产物）。"""
    from ..reprospec.compiler import compile_reprospec
    from ..reprospec import lifecycle as LC
    from ..po import POGraph
    ws = _ws(aid) if (BASE / aid).exists() or (RUNS / aid).exists() \
        or (RUNS / "regression" / aid).exists() else (BASE / aid)
    ws.mkdir(parents=True, exist_ok=True)
    if stage == "all":
        return LC.run_lifecycle("paper:" + aid, ws, effort=effort)
    spec = compile_reprospec(paper_id="paper:" + aid, out_dir=ws)
    g = POGraph.load("storage_cf/sciforge/app_reproduction.json")
    if stage == "lock":
        r = LC.run_lock(spec, ws)
    elif stage == "codegen":
        r = LC.run_codegen(spec, g, ws)
    elif stage == "execute":
        r = LC.run_execute(spec, ws)
    elif stage == "anchor":
        r = LC.run_anchor(spec, g, ws)
    else:
        raise HTTPException(400, "stage 只能是 all/lock/codegen/execute/anchor")
    return {"stage": r.to_dict(), "status": LC.stage_status(ws),
            "verify": LC.verify_lifecycle(ws)}


def page():
    from fastapi.responses import HTMLResponse
    from .extraction_api import STATIC_DIR
    f = STATIC_DIR / "repro.html"
    if not f.exists():
        raise HTTPException(500, "repro.html 缺失")
    return HTMLResponse(f.read_text(encoding="utf-8"))


_V9 = [
    ("/repro", page, "GET", False),
    ("/api/v9/repro/papers", papers, "GET", True),
    ("/api/v9/repro/{aid}/status", status, "GET", True),
    ("/api/v9/repro/{aid}/lifecycle", lifecycle, "GET", True),
    ("/api/v9/repro/{aid}/method-lock", method_lock, "GET", True),
    ("/api/v9/repro/{aid}/code-plan", code_plan, "GET", True),
    ("/api/v9/repro/{aid}/execution", execution, "GET", True),
    ("/api/v9/repro/{aid}/anchors", anchors, "GET", True),
    ("/api/v9/repro/{aid}/verify", verify, "GET", True),
    ("/api/v9/repro/{aid}/run", run, "POST", True),
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
