"""26 阶段运行器：门控、约束再注入、events.ndjson（durable truth）、RUNSTATE 派生。

硬约束：runner 与所有阶段产物只写 run 目录，不写任何图（H7）。
gate 未决定 → BLOCKED，绝不自动通过（H14）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, gates, hitl, paperspec, signals, util
from .tbox import CHOICEPOINTS, stage_defs, STAGE_IDS


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_dir(run_id: str, out_dir=None) -> Path:
    base = Path(out_dir) if out_dir else config.RUNS_DIR
    return base / run_id.replace(":", "_")


def _events(d: Path) -> Path:
    return d / "events.ndjson"


def _append(d: Path, row: Dict[str, Any]) -> None:
    util.append_jsonl(_events(d), row)


def run(*, paper_id: str = "paper:demo", effort: str = "balanced",
        run_id: str = "", out_dir=None, stage: Optional[str] = None,
        gate_decisions: Optional[Dict[str, str]] = None,
        fail_at: str = "", human_hypotheses: Optional[List[Dict[str, Any]]] = None,
        graph=None) -> Dict[str, Any]:
    """跑完整 26 阶段（或单阶段）。返回 run 摘要，不写图。"""
    rid = run_id or f"run:{paper_id.split(':')[-1]}:{int(time.time())}"
    d = run_dir(rid, out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "verdicts").mkdir(exist_ok=True)
    (d / "stages").mkdir(exist_ok=True)
    gate_decisions = gate_decisions or {}
    stages = [stage] if stage else list(STAGE_IDS)
    verdicts: Dict[str, Dict[str, Any]] = {}
    started = time.time()
    _append(d, {"ts": _now(), "run_id": rid, "stage": "0",
                "event": "run_started", "payload": {"paper_id": paper_id,
                                                   "effort": effort}})
    # I5：run 开始时固化当前有效决定，供本 run 每个边界逐字复述
    hitl.reinject(out_dir=out_dir)
    # 人方向校验（I4/P2）：不合格的记信号，不静默插入
    n_human_ok = 0
    from . import miners
    for h in (human_hypotheses or []):
        r = miners.inject_human_hypothesis(h)
        if r["ok"]:
            n_human_ok += 1
        else:
            signals.observe_event("human_direction_unadopted", h.get("statement", ""),
                                  stage="2", paper_id=paper_id, run_id=rid,
                                  source=f"human.{r['reason_code']}", out_dir=out_dir)
    for sid in stages:
        # I5：每边界逐字复述
        verbatim = hitl.verbatim_for(sid, out_dir=out_dir)
        for text in verbatim:
            _append(d, {"ts": _now(), "run_id": rid, "stage": sid,
                        "event": "reinjection", "payload": {"verbatim_text": text}})
        cp = CHOICEPOINTS.get(sid)
        state = "PASS"
        reason = "ok"
        if cp and cp["mode"] == "gate":
            chosen = gate_decisions.get(sid)
            if not chosen:
                state, reason = "BLOCKED", "gate_undecided"
            else:
                r = hitl.decide(sid, chosen, approver="human:runner",
                                run_id=rid, out_dir=out_dir)
                if not r.get("ok"):
                    state, reason = "BLOCKED", r.get("reason_code", "gate_failed")
        elif cp and cp["mode"] == "option":
            _append(d, {"ts": _now(), "run_id": rid, "stage": sid,
                        "event": "auto_default",
                        "payload": {"option": cp["default"]}})
        if sid == fail_at:
            state, reason = "FAIL", "injected_failure"
        v = gates.emit(sid, state, artifacts=[f"stages/{sid}/"],
                       reason_code=reason, evidence_ids=verbatim)
        verdicts[sid] = v
        util.atomic_write(d / "verdicts" / f"{sid}.json", v)
        util.atomic_write(d / "stages" / sid / "verdict.json", v)
        _append(d, {"ts": _now(), "run_id": rid, "stage": sid,
                    "event": "verdict_emitted", "payload": {"state": state,
                                                           "reason_code": reason}})
        if state in ("FAIL", "BLOCKED", "ERROR"):
            signals.observe_event("gate_failed", sid, stage=sid,
                                  paper_id=paper_id, run_id=rid,
                                  source=f"runner.{reason}", out_dir=out_dir)
    spec = paperspec.compile_paperspec(graph, paper_id=paper_id, out_dir=out_dir)
    spec.verdicts = {k: v["state"] for k, v in verdicts.items()}
    spec.spec_hash = spec.compute_hash()
    spec.save(d)
    hitl.reinject(out_dir=out_dir)
    lessons = {
        "failed_experiments": [], "idea_rollbacks": [], "code_errors": [],
        "what_worked": [{"evidence": f"stages/{s}/", "lesson": "stage completed"}
                        for s, v in verdicts.items() if v["state"] == "PASS"],
        "human_hypothesis_rollbacks": [
            {"evidence": "runner", "lesson": h.get("statement", ""),
             "reason": "failed_or_unadopted"}
            for h in (human_hypotheses or []) if not h.get("succeeded", True)],
    }
    util.atomic_write(d / "LESSONS.json", lessons)
    (d / "RUN_PREPRINT.md").write_text(
        f"# {rid}\n\npaper={paper_id} stages={len(verdicts)}\n", encoding="utf-8")
    overall = "PASS" if all(v["state"] == "PASS" for v in verdicts.values()) else \
        ("BLOCKED" if any(v["state"] == "BLOCKED" for v in verdicts.values()) else "FAIL")
    summary = {"run_id": rid, "paper_id": paper_id, "effort": effort,
               "overall": overall, "n_stages": len(verdicts),
               "n_human_hypotheses_accepted": n_human_ok,
               "spec_hash": spec.spec_hash,
               "semantic_sha": util.sha256_file(config.SEMANTIC_GRAPH),
               "app_sha": util.sha256_file(config.APP_GRAPH),
               "duration_ms": int((time.time() - started) * 1000),
               "verdicts": {k: v["state"] for k, v in verdicts.items()}}
    util.atomic_write(d / "FINAL_EVALUATION.json", summary)
    _append(d, {"ts": _now(), "run_id": rid, "stage": "16",
                "event": "run_finalized", "payload": {"overall": overall}})
    state = replay(d)
    util.atomic_write(d / "RUNSTATE.json", state)
    return summary


def replay(d: str | Path) -> Dict[str, Any]:
    """RUNSTATE 只能由 events 派生。"""
    d = Path(d)
    rows = util.read_jsonl(_events(d), limit=100000)
    stages = [r["stage"] for r in rows if r.get("event") == "verdict_emitted"]
    return {"run_id": next((r.get("run_id") for r in rows), ""),
            "current_phase": stages[-1] if stages else "0",
            "last_completed_boundary": stages[-1] if stages else "",
            "next_action": "resume" if stages else "start",
            "status": "running" if not any(r.get("event") == "run_finalized"
                                          for r in rows) else "completed",
            "n_events": len(rows), "n_reinjections": sum(
                1 for r in rows if r.get("event") == "reinjection"),
            "derived_from_events": True}


def verify_run(run_id: str, *, out_dir=None) -> Dict[str, Any]:
    d = run_dir(run_id, out_dir)
    p = d / "RUNSTATE.json"
    saved = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    derived = replay(d)
    return {"ok": saved == derived, "replay_ok": saved == derived,
            "n_events": derived["n_events"],
            "n_reinjections": derived["n_reinjections"], "reason_code": "ok"}


def audit_gates(run_id: str = "", *, out_dir=None, verdicts=None) -> Dict[str, Any]:
    d = run_dir(run_id, out_dir) if run_id else None
    vs = verdicts
    if vs is None and d:
        vs = {}
        for p in sorted((d / "verdicts").glob("*.json")):
            try:
                vs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return gates.audit(vs or {})


def budget(run_id: str, *, out_dir=None) -> Dict[str, Any]:
    d = run_dir(run_id, out_dir)
    p = d / "FINAL_EVALUATION.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"run_id": run_id, "wall_clock_ms": s.get("duration_ms", 0),
            "api_cost_usd": 0.0, "pivot_count": 0, "ba_rounds_used": 0,
            "ba_rounds_max": 2, "limits": {"wall_clock_ms": 180000},
            "exploration_regret": 0, "warnings": []}


def debug_stage(run_id: str, stage: str, *, out_dir=None) -> Dict[str, Any]:
    d = run_dir(run_id, out_dir)
    p = d / "stages" / stage / "verdict.json"
    return {"run_id": run_id, "stage": stage,
            "verdict": json.loads(p.read_text(encoding="utf-8")) if p.exists() else None,
            "reinjection": hitl.verbatim_for(stage, out_dir=out_dir),
            "events": [r for r in util.read_jsonl(_events(d), limit=10000)
                       if r.get("stage") == stage][-20:]}
