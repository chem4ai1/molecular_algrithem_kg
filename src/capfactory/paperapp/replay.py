"""跨 run 回放：LESSONS.json → REPLAY_CONTEXT.json，失败也是知识点。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from . import config, util

NEGATIVE_KEYS = ("failed_experiments", "idea_rollbacks", "code_errors",
                 "human_hypothesis_rollbacks")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _runs(out_dir=None) -> Path:
    return Path(out_dir) if out_dir else config.RUNS_DIR


def collect_lessons(run_ids: Iterable[str], *, out_dir=None) -> Dict[str, Any]:
    base = _runs(out_dir)
    rows: List[Dict[str, Any]] = []
    for rid in run_ids:
        p = base / rid.replace(":", "_") / "LESSONS.json"
        if p.exists():
            try:
                rows.append({"run_id": rid, **json.loads(p.read_text(encoding="utf-8"))})
            except (ValueError, OSError):
                continue
    return {"items": rows, "n": len(rows)}


def build_context(run_ids: Iterable[str], *, out_dir=None,
                  allow_frontier_restart: bool = True) -> Dict[str, Any]:
    col = collect_lessons(run_ids, out_dir=out_dir)
    avoid, worked = [], []
    for item in col["items"]:
        for k in NEGATIVE_KEYS:
            for row in item.get(k, []) or []:
                avoid.append({"lesson": row.get("lesson", ""),
                              "reason": row.get("reason", k),
                              "source_run": item["run_id"]})
        for row in item.get("what_worked", []) or []:
            worked.append({"lesson": row.get("lesson", ""),
                           "evidence": row.get("evidence", ""),
                           "source_run": item["run_id"]})
    ctx = {"schema_version": "1.0", "generated_at": _now(),
           "source_run_ids": [x["run_id"] for x in col["items"]],
           "avoid": avoid, "what_worked": worked,
           "n_hard_excluded": len(avoid),
           "allow_frontier_restart": allow_frontier_restart,
           "frontiers": [{"direction": a["lesson"], "status": "failed",
                          "source": "human_or_experiment"}
                         for a in avoid if a["lesson"]]}
    base = _runs(out_dir)
    out = base / "REPLAY_CONTEXT.json"
    util.atomic_write(out, ctx)
    return ctx


def hard_excluded(ctx: Dict[str, Any], value: str) -> bool:
    return any(value and value.lower() in a["lesson"].lower()
               for a in ctx.get("avoid", []))


def restart_frontier(direction: str, *, reason: str, out_dir=None) -> Dict[str, Any]:
    """I3：失败方向可 untried 重启，但必须写理由，不永久 avoid。"""
    base = _runs(out_dir)
    p = base / "REPLAY_CONTEXT.json"
    ctx = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"frontiers": []}
    if not reason:
        return {"ok": False, "reason_code": "reason_required"}
    for f in ctx.setdefault("frontiers", []):
        if f.get("direction") == direction:
            f["status"] = "untried"
            f["restart_reason"] = reason
            f["restarted_at"] = _now()
    util.atomic_write(p, ctx)
    return {"ok": True, "action": "frontier_restarted", "reason_code": "ok"}
