"""6 态 verdict 封装。直接复用 sciforge/contracts.py，不造第二套词汇。"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from capfactory.sciforge.contracts import (VERDICT_STATES, validate_verdict,
                                           verdict)


def emit(stage: str, state: str, *, artifacts: Iterable[str] = (),
         reason_code: str = "", evidence_ids: Iterable[str] = ()) -> Dict[str, Any]:
    if state not in VERDICT_STATES:
        raise ValueError(f"invalid verdict state: {state}")
    d = verdict(state, artifacts=list(artifacts), notes=reason_code)
    d["reason_code"] = reason_code
    d["state"] = state
    d["stage"] = stage
    d["evidence_ids"] = list(evidence_ids)
    problems = validate_verdict(d, strict=False)
    if problems:
        raise ValueError(f"invalid verdict: {problems}")
    return d


def audit(verdicts: Dict[str, Dict[str, Any]], *, na_verdicts=()) -> Dict[str, Any]:
    """H7/H11：缺 verdict、非法 state、NOT_APPLICABLE 无文件、PENDING 检查。"""
    missing, invalid, na_without_file = [], [], []
    for stage, v in (verdicts or {}).items():
        state = v.get("state") or v.get("verdict")
        if not state:
            missing.append(stage)
        elif state not in VERDICT_STATES:
            invalid.append({"stage": stage, "state": state})
        elif state == "NOT_APPLICABLE" and not v.get("artifacts"):
            na_without_file.append(stage)
    pending = [s for s, v in (verdicts or {}).items()
               if (v.get("state") or v.get("verdict")) in ("BLOCKED", "ERROR", "FAIL")
               and s not in set(na_verdicts)]
    return {"ok": not (missing or invalid or na_without_file or pending),
            "missing": missing, "invalid": invalid,
            "not_applicable_without_file": na_without_file,
            "blocking": pending, "n": len(verdicts or {})}
