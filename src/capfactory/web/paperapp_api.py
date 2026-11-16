"""/api/v10/paperapp/* —— 动态本体与人类决策的统一 API（S5）。

注册范式与 repro_api._V9 一致：由 server.WEB_API_MODULES 调用 register(app)。
所有列表默认 limit=200 / 上限 500；GET 响应 no-store；错误统一结构。
不读 graph_source.py，直接读 app_generation.json（避免污染既有页面）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from capfactory.paperapp import (config, coverage, hitl, materialize,
                                 nodecache, promote, registry, replay, runner,
                                 signals, tbox, util)
from capfactory.paperapp import cli as pcli

STATIC = Path(__file__).parent / "static"


def _q(request: Request, key: str, default: str = "") -> str:
    return request.query_params.get(key, default)


def _limit(request: Request) -> int:
    try:
        n = int(request.query_params.get("limit", "200"))
    except ValueError:
        return 400
    if n > 500:
        return -1
    return max(1, n)


def _err(code: str, detail: str = "", status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "reason_code": code,
                         "detail": detail[:200]}, status_code=status)


def _app_graph() -> Dict[str, Any]:
    p = config.APP_GRAPH
    if not p.exists():
        return {"meta": {}, "nodes": [], "assertions": []}
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------ handlers ------------------------------
def h_status(r: Request): return pcli.status()


def h_overview(r: Request):
    s = pcli.status()
    sig = signals.signal_stats()
    d = registry.load_registry()
    cov = config.NODE_CACHE / "MINING_COVERAGE.json"
    coverage_ratio = None
    if cov.exists():
        try:
            coverage_ratio = json.loads(cov.read_text(encoding="utf-8")).get("coverage_ratio")
        except (ValueError, OSError):
            pass
    return {**s, "n_registered_classes": len(d.get("classes", {})),
            "cache": {"n_signals": sig["n_signals"],
                      "signal_capture_rate": sig["signal_capture_rate"]},
            "mining_coverage_ratio": coverage_ratio,
            "pending_gate_choices": sum(1 for k, v in tbox.CHOICEPOINTS.items()
                                        if v["mode"] == "gate" and not hitl.open_choice(k)
                                        .get("choice", {}).get("verdict_file")),
            "api_registration_errors": {}}


def h_registry(r: Request):
    d = registry.load_registry()
    return {"classes": list(d.get("classes", {}).values()),
            "count": len(d.get("classes", {})),
            "dynamic_tbox_version": d.get("version")}


def h_registry_audit(r: Request): return pcli.registry_audit()
def h_verify_rebuild(r: Request): return pcli.verify_rebuild_cli()
def h_gates_audit(r: Request):
    return runner.audit_gates(_q(r, "run", "")) if _q(r, "run") else {
        "ok": True, "missing": [], "invalid": [],
        "not_applicable_without_file": [], "blocking": [], "n": 0}


def h_cache_requests(r: Request):
    n = _limit(r)
    if n < 0: return _err("limit_too_large")
    st = nodecache.cache_status()
    return {"items": [], "count": st["n_requests"], "hit_rate": st["cache_hit_rate"],
            "summary": st}


def h_cache_proposals(r: Request):
    n = _limit(r)
    if n < 0: return _err("limit_too_large")
    status = _q(r, "status")
    ps = nodecache.load_proposals()
    if status:
        ps = [p for p in ps if p.status == status]
    return {"items": [p.to_dict() for p in ps[:n]], "count": len(ps),
            "by_status": {s: sum(1 for p in ps if p.status == s)
                          for s in ("proposed", "validated", "registered",
                                    "deprecated", "rejected")}}


def h_proposals(r: Request):
    pid = _q(r, "id")
    if not pid:
        return h_cache_proposals(r)
    for p in nodecache.load_proposals():
        if p.proposal_id == pid:
            return p.to_dict()
    return _err("proposal_not_found", status=404)


def h_cache_nodes(r: Request):
    n = _limit(r)
    if n < 0: return _err("limit_too_large")
    d = config.NODES_DIR
    items = []
    if d.exists():
        for p in sorted(d.glob("*.json"))[:n]:
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    return {"items": items, "count": len(list(d.glob("*.json"))) if d.exists() else 0}


def h_cache_conflicts(r: Request):
    rows = util.read_jsonl(config.NODE_CACHE / "conflicts" / "CONFLICT_LOG.jsonl")
    return {"items": rows[-200:], "count": len(rows)}


def h_signals(r: Request):
    return {"items": [s.to_dict() for s in signals.load_signals()[:_limit(r)]],
            "count": len(signals.load_signals()),
            "stats": signals.signal_stats()}


def h_signals_audit(r: Request): return pcli.audit_signals()
def h_choices(r: Request):
    rows = []
    p = config.DYNAMIC_TBOX / "CHOICEPOINTS.json"
    if p.exists():
        rows = json.loads(p.read_text(encoding="utf-8")).get("choices", [])
    mode = _q(r, "mode")
    if mode:
        rows = [x for x in rows if x["mode"] == mode]
    status = _q(r, "status")
    if status:
        rows = [x for x in rows if x["status"] == status]
    return {"items": rows, "count": len(rows)}


def h_decisions(r: Request):
    return {"items": [d.to_dict() for d in hitl.load_decisions()[:_limit(r)]],
            "count": len(hitl.load_decisions()),
            "append_only": True}


def h_decisions_audit(r: Request): return pcli.audit_decisions()
def h_sover(r: Request): return pcli.audit_sovereignty()
def h_reinjection(r: Request): return hitl.load_reinjection()
def h_reinjection_audit(r: Request): return pcli.audit_reinjection()
def h_frontiers(r: Request):
    p = config.RUNS_DIR / "REPLAY_CONTEXT.json"
    ctx = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"frontiers": []}
    return {"items": ctx.get("frontiers", []), "count": len(ctx.get("frontiers", []))}


def h_mining_coverage(r: Request): return pcli.mining_coverage()
def h_stages(r: Request):
    return {"stages": tbox.stage_defs(), "enabled": len(config.STAGE_IDS),
            "total": 26, "parallel_groups": [["7", "8"], ["11", "12"]],
            "choicpoints": tbox.CHOICEPOINTS}


def h_stages_detail(r: Request):
    sid = _q(r, "id")
    c = hitl.open_choice(sid)
    return {"stage": sid, "gate": tbox._GATES.get(sid, ""),
            "choice": c.get("choice"), "events": [],
            "reinjection": hitl.verbatim_for(sid)}


def h_spec(r: Request):
    from capfactory.paperapp import paperspec
    try:
        return paperspec.compile_paperspec(paper_id=_q(r, "arxiv", ""),
                                           include_derived=False).to_dict()
    except Exception as exc:  # noqa: BLE001
        return _err("spec_not_built", str(exc), 404)


def h_runs(r: Request):
    base = config.RUNS_DIR
    items = []
    if base.exists():
        for p in sorted(base.glob("*/FINAL_EVALUATION.json")):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    return {"runs": items[-_limit(r):], "count": len(items)}


def h_run_detail(r: Request):
    rid = _q(r, "id")
    p = config.RUNS_DIR / rid.replace(":", "_") / "FINAL_EVALUATION.json"
    if not p.exists():
        return _err("run_not_found", status=404)
    return json.loads(p.read_text(encoding="utf-8"))


def h_run_stages(r: Request):
    rid = _q(r, "id")
    d = config.RUNS_DIR / rid.replace(":", "_") / "verdicts"
    vs = {}
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                vs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {"stages": [{"id": k, **v} for k, v in vs.items()],
            "count": len(vs), "parallel_groups": [["7", "8"], ["11", "12"]]}


def h_verdict(r: Request):
    sid = _q(r, "id")
    rid = _q(r, "run", "")
    p = (config.RUNS_DIR / rid.replace(":", "_") / "verdicts" / f"{sid}.json") if rid \
        else None
    if p and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"stage": sid, "state": None}


def h_events(r: Request):
    rid = _q(r, "id")
    lim = _limit(r)
    if lim < 0: return _err("limit_too_large")
    p = config.RUNS_DIR / rid.replace(":", "_") / "events.ndjson"
    rows = util.read_jsonl(p, limit=100000)
    stage = _q(r, "stage")
    if stage:
        rows = [x for x in rows if x.get("stage") == stage]
    return {"items": rows[-lim:], "count": len(rows),
            "replay_ok": runner.verify_run(rid)["replay_ok"] if p.exists() else False}


def h_loopbacks(r: Request):
    return {"items": [], "count": 0, "ba_rounds_used": 0, "ba_rounds_max": 2}


def h_budget(r: Request):
    return runner.budget(_q(r, "id"))


def h_materialize_report(r: Request):
    p = config.RUNS_DIR / _q(r, "run", "").replace(":", "_") / "MATERIALIZE_REPORT.json"
    if not p.exists():
        return _err("not_materialized", status=404)
    return json.loads(p.read_text(encoding="utf-8"))


def h_materialize_diff(r: Request):
    report = h_materialize_report(r)
    return {"nodes_added": report.get("delta_ids", []) if isinstance(report, dict) else [],
            "assertions_added": [], "nodes_removed": [],
            "equivalence": {"ok": report.get("rebuild_equivalence", False)
                            if isinstance(report, dict) else False}}


def h_stale(r: Request):
    return {"items": [], "scope": 0.0, "ceiling": config.STALE_SCOPE_CEILING,
            "stages_to_rerun": []}


def h_promotions(r: Request): return promote.audit_promotions()
def h_replay(r: Request):
    p = config.RUNS_DIR / "REPLAY_CONTEXT.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else \
        {"source_run_ids": [], "avoid": [], "what_worked": [], "n_hard_excluded": 0}


def h_graph_nodes(r: Request):
    lim = _limit(r)
    if lim < 0: return _err("limit_too_large")
    g = _app_graph()
    rows = g.get("nodes", [])
    if _q(r, "attribution"):
        rows = [n for n in rows if n.get("attribution") == _q(r, "attribution")]
    if _q(r, "layer"):
        rows = [n for n in rows if (n.get("attrs") or {}).get("layer") == _q(r, "layer")]
    q = _q(r, "q").lower()
    if q:
        rows = [n for n in rows if q in (n.get("id", "") + n.get("label", "")).lower()]
    return {"items": rows[:lim], "count": len(rows)}


def h_graph_node(r: Request):
    nid = _q(r, "id")
    g = _app_graph()
    for n in g.get("nodes", []):
        if n["id"] == nid:
            inn = [a for a in g.get("assertions", []) if a["target"] == nid][:50]
            out = [a for a in g.get("assertions", []) if a["source"] == nid][:50]
            return {"node": n, "in_edges": inn, "out_edges": out,
                    "evidence_summary": n.get("evidence_ids", [])}
    return _err("node_not_found", status=404)


def h_debug_health(r: Request):
    return {"ok": True, "graphs": {"semantic": config.SEMANTIC_GRAPH.exists(),
                                  "app": config.APP_GRAPH.exists()},
            "registry": registry.load_registry().get("version"),
            "api_registration_errors": {}, "lock_file": str(config.LOCK_FILE)}


def h_debug_events(r: Request):
    rows = []
    for p in sorted(config.RUNS_DIR.glob("*/events.ndjson")):
        rows.extend(util.read_jsonl(p, limit=10000))
    return {"items": rows[-int(_q(r, "tail", "50") or 50):], "count": len(rows)}


def h_debug_replay(r: Request):
    return {"replay_ok": True, "runs": len(list(config.RUNS_DIR.glob("*/RUNSTATE.json")))
            if config.RUNS_DIR.exists() else 0}


def h_page(r: Request) -> HTMLResponse:
    p = STATIC / "paperapp.html"
    return HTMLResponse(p.read_text(encoding="utf-8") if p.exists() else
                        "<h1>paperapp.html missing</h1>")


# POST handlers（body 用 Request 读取，统一在 _post 分派）
async def p_run(r: Request):
    body = await r.json()
    return runner.run(paper_id=body.get("arxiv", "paper:demo"),
                      effort=body.get("effort", "balanced"),
                      gate_decisions=body.get("gate_decisions"))


async def p_decide(r: Request):
    body = await r.json()
    return hitl.decide(body.get("stage", ""), body.get("option", ""),
                       approver=body.get("approver", ""),
                       reason=body.get("reason", ""),
                       timeout=bool(body.get("timeout", False)))


async def p_hypotheses(r: Request):
    from capfactory.paperapp import miners
    body = await r.json()
    return miners.inject_human_hypothesis(body)


async def p_promote(r: Request):
    body = await r.json()
    pid, approver = body.get("proposal_id", ""), body.get("approver", "")
    for x in nodecache.load_proposals():
        if x.proposal_id == pid and x.status == "validated":
            return promote.promote(x, approver=approver)
    return _err("proposal_not_validated", status=403)


async def p_invalidate(r: Request):
    body = await r.json()
    return nodecache.invalidate(body.get("key", ""), reason=body.get("reason", ""))


async def p_materialize(r: Request):
    body = await r.json()
    return materialize.materialize(body.get("run_id", ""), write=False)


def _get(fn: Callable):
    def ep(request: Request):
        try:
            return fn(request)
        except Exception as exc:  # noqa: BLE001
            return _err("internal_error", f"{type(exc).__name__}: {exc}", 500)
    return ep


_V10 = [
    ("/paperapp", h_page, "GET", False),
    ("/api/v10/paperapp/status", h_status, "GET", True),
    ("/api/v10/paperapp/overview", h_overview, "GET", True),
    ("/api/v10/paperapp/registry", h_registry, "GET", True),
    ("/api/v10/paperapp/registry/audit", h_registry_audit, "GET", True),
    ("/api/v10/paperapp/verify-rebuild", h_verify_rebuild, "GET", True),
    ("/api/v10/paperapp/gates/audit", h_gates_audit, "GET", True),
    ("/api/v10/paperapp/cache/requests", h_cache_requests, "GET", True),
    ("/api/v10/paperapp/cache/proposals", h_cache_proposals, "GET", True),
    ("/api/v10/paperapp/cache/conflicts", h_cache_conflicts, "GET", True),
    ("/api/v10/paperapp/cache/nodes", h_cache_nodes, "GET", True),
    ("/api/v10/paperapp/proposals", h_proposals, "GET", True),
    ("/api/v10/paperapp/signals", h_signals, "GET", True),
    ("/api/v10/paperapp/signals/audit", h_signals_audit, "GET", True),
    ("/api/v10/paperapp/choices", h_choices, "GET", True),
    ("/api/v10/paperapp/decisions", h_decisions, "GET", True),
    ("/api/v10/paperapp/decisions/audit", h_decisions_audit, "GET", True),
    ("/api/v10/paperapp/audit-sovereignty", h_sover, "GET", True),
    ("/api/v10/paperapp/reinjection", h_reinjection, "GET", True),
    ("/api/v10/paperapp/reinjection/audit", h_reinjection_audit, "GET", True),
    ("/api/v10/paperapp/frontiers", h_frontiers, "GET", True),
    ("/api/v10/paperapp/mining-coverage", h_mining_coverage, "GET", True),
    ("/api/v10/paperapp/stages", h_stages, "GET", True),
    ("/api/v10/paperapp/stages/detail", h_stages_detail, "GET", True),
    ("/api/v10/paperapp/spec", h_spec, "GET", True),
    ("/api/v10/paperapp/runs", h_runs, "GET", True),
    ("/api/v10/paperapp/runs/detail", h_run_detail, "GET", True),
    ("/api/v10/paperapp/runs/stages", h_run_stages, "GET", True),
    ("/api/v10/paperapp/verdict", h_verdict, "GET", True),
    ("/api/v10/paperapp/events", h_events, "GET", True),
    ("/api/v10/paperapp/loopbacks", h_loopbacks, "GET", True),
    ("/api/v10/paperapp/budget", h_budget, "GET", True),
    ("/api/v10/paperapp/materialize/report", h_materialize_report, "GET", True),
    ("/api/v10/paperapp/materialize/diff", h_materialize_diff, "GET", True),
    ("/api/v10/paperapp/stale", h_stale, "GET", True),
    ("/api/v10/paperapp/promotions", h_promotions, "GET", True),
    ("/api/v10/paperapp/replay", h_replay, "GET", True),
    ("/api/v10/paperapp/graph/nodes", h_graph_nodes, "GET", True),
    ("/api/v10/paperapp/graph/node", h_graph_node, "GET", True),
    ("/api/v10/paperapp/debug/health", h_debug_health, "GET", True),
    ("/api/v10/paperapp/debug/events", h_debug_events, "GET", True),
    ("/api/v10/paperapp/debug/replay", h_debug_replay, "GET", True),
]
_POST = {
    "/api/v10/paperapp/run": p_run,
    "/api/v10/paperapp/decide": p_decide,
    "/api/v10/paperapp/hypotheses": p_hypotheses,
    "/api/v10/paperapp/promote": p_promote,
    "/api/v10/paperapp/invalidate": p_invalidate,
    "/api/v10/paperapp/materialize": p_materialize,
}


def register(app) -> int:
    existing = {getattr(rt, "path", "") for rt in app.routes}
    n = 0
    for path, ep, method, ins in _V10:
        if path in existing:
            continue
        kw: Dict[str, Any] = {"methods": [method], "include_in_schema": ins}
        if path == "/paperapp":
            kw["response_class"] = HTMLResponse
        app.add_api_route(path, h_page if path == "/paperapp" else _get(ep), **kw)
        n += 1
    for path, ep in _POST.items():
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=["POST"], include_in_schema=True)
        n += 1
    return n
