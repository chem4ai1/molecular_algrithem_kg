"""I4 人类主权 / I5 决定可传播。

gate 超时只能 BLOCKED；HumanDecision 是 append-only 的一等节点；
CONSTRAINT_REINJECTION.json 在后续每边界逐字复述。
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, util
from .tbox import CHOICEPOINTS, GATE_STAGES, STAGE_IDS

DECISION_DIR = config.DYNAMIC_TBOX / "decisions"
DECISION_LOG = config.DYNAMIC_TBOX / "DECISION_LOG.jsonl"
CHOICES_FILE = config.DYNAMIC_TBOX / "CHOICEPOINTS.json"
REINJECTION_FILE = config.DYNAMIC_TBOX / "CONSTRAINT_REINJECTION.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class HumanDecision:
    decision_id: str
    choice_id: str
    stage: str
    chosen_option_id: str
    approver: str
    ts: str
    evidence_ids: List[str] = field(default_factory=list)
    reason: str = ""
    supersedes: str = ""
    valid_from: str = ""
    valid_to: Optional[str] = None
    origin: str = "human"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def verbatim_text(self) -> str:
        return (f"[HumanDecision {self.decision_id}] stage={self.stage} "
                f"approver={self.approver} chose={self.chosen_option_id} "
                f"reason={self.reason or '(none)'}")


def _paths(out_dir=None):
    base = Path(out_dir) if out_dir else config.DYNAMIC_TBOX
    return (base / "decisions", base / "DECISION_LOG.jsonl",
            base / "CHOICEPOINTS.json", base / "CONSTRAINT_REINJECTION.json")


def seed_choices(*, out_dir=None) -> Dict[str, Any]:
    """从 tbox.CHOICEPOINTS 生成 14 个 ChoicePoint 文件。"""
    ddir, _, cfile, _ = _paths(out_dir)
    ddir.mkdir(parents=True, exist_ok=True)
    rows = []
    for stage, spec in CHOICEPOINTS.items():
        cid = f"choice:{stage}"
        rows.append({"choice_id": cid, "stage": stage, "mode": spec["mode"],
                     "options": [{"id": o, "rationale": "", "cost": "",
                                  "risk": "", "suggested_by": "system"}
                                 for o in spec["options"]],
                     "default_option": spec["default"], "deadline": None,
                     "status": "pending", "verdict_file": ""})
    util.atomic_write(cfile, {"choices": rows, "n": len(rows)})
    return {"ok": True, "n": len(rows), "n_gate": len(GATE_STAGES)}


def open_choice(stage: str, *, out_dir=None) -> Dict[str, Any]:
    if stage not in CHOICEPOINTS:
        return {"ok": False, "reason_code": "no_choicepoint_for_stage"}
    _, _, cfile, _ = _paths(out_dir)
    data = {}
    if cfile.exists():
        import json
        data = json.loads(cfile.read_text(encoding="utf-8"))
    for c in data.get("choices", []):
        if c["choice_id"] == f"choice:{stage}":
            return {"ok": True, "choice": c}
    return {"ok": False, "reason_code": "choice_not_seeded"}


def decide(stage: str, option_id: str, *, approver: str, reason: str = "",
           evidence_ids=None, run_id: str = "", timeout: bool = False,
           out_dir=None) -> Dict[str, Any]:
    """gate 超时 → BLOCKED，绝不自动通过（H14）。"""
    ddir, dlog, _, _ = _paths(out_dir)
    ddir.mkdir(parents=True, exist_ok=True)
    spec = CHOICEPOINTS.get(stage)
    if not spec:
        return {"ok": False, "action": "reject", "reason_code": "no_choicepoint_for_stage"}
    if timeout and spec["mode"] == "gate":
        row = {"ts": _now(), "event": "choice_timeout_blocked", "stage": stage,
               "policy": config.GATE_TIMEOUT_POLICY}
        util.append_jsonl(dlog, row)
        from .gates import emit
        verdict = emit(stage, "BLOCKED", reason_code="choice_timeout_blocked")
        util.atomic_write(ddir / f"verdict_{stage}.json", verdict)
        return {"ok": False, "action": "blocked",
                "reason_code": "choice_timeout_blocked", "verdict": verdict}
    if spec["mode"] == "gate" and not approver:
        return {"ok": False, "action": "reject", "reason_code": "approver_required"}
    if option_id not in spec["options"]:
        return {"ok": False, "action": "reject", "reason_code": "unknown_option"}
    did = "dec:" + util.sha256_json([stage, option_id, approver, _now(), run_id])[7:23]
    dec = HumanDecision(decision_id=did, choice_id=f"choice:{stage}", stage=stage,
                        chosen_option_id=option_id, approver=approver, ts=_now(),
                        evidence_ids=list(evidence_ids or []), reason=reason,
                        valid_from=_now())
    util.atomic_write(ddir / (did.replace(":", "_") + ".json"), dec.to_dict())
    util.append_jsonl(dlog, {"ts": _now(), "event": "decision_made",
                             "decision_id": did, "stage": stage,
                             "chosen": option_id, "approver": approver})
    from .gates import emit
    util.atomic_write(ddir / f"verdict_{stage}.json",
                      emit(stage, "PASS", reason_code="human_decision"))
    return {"ok": True, "action": "decided", "decision": dec.to_dict(),
            "reason_code": "ok"}


def load_decisions(*, out_dir=None) -> List[HumanDecision]:
    ddir, _, _, _ = _paths(out_dir)
    out: List[HumanDecision] = []
    if not ddir.exists():
        return out
    import json
    for p in sorted(ddir.glob("dec_*.json")):
        try:
            out.append(HumanDecision(**json.loads(p.read_text(encoding="utf-8"))))
        except (ValueError, TypeError, OSError):
            continue
    return out


def active_decisions(*, out_dir=None) -> List[HumanDecision]:
    ids = {d.supersedes for d in load_decisions(out_dir=out_dir) if d.supersedes}
    return [d for d in load_decisions(out_dir=out_dir)
            if d.decision_id not in ids and d.valid_to is None]


def decision_fp(*, out_dir=None) -> str:
    return util.sha256_json(sorted((d.decision_id, d.chosen_option_id)
                                   for d in active_decisions(out_dir=out_dir)))


def supersede(old_decision_id: str, stage: str, option_id: str, *,
              approver: str, reason: str, out_dir=None) -> Dict[str, Any]:
    """人改主意：旧决定标 valid_to，新决定 SUPERSEDES，不删除。"""
    ddir, dlog, _, _ = _paths(out_dir)
    found = None
    for d in load_decisions(out_dir=out_dir):
        if d.decision_id == old_decision_id:
            found = d
            break
    if not found:
        return {"ok": False, "reason_code": "decision_not_found"}
    found.valid_to = _now()
    util.atomic_write(ddir / (found.decision_id.replace(":", "_") + ".json"),
                      found.to_dict())
    r = decide(stage, option_id, approver=approver, reason=reason,
               out_dir=out_dir)
    if r.get("ok"):
        dec = HumanDecision(**r["decision"])
        dec.supersedes = old_decision_id
        util.atomic_write(ddir / (dec.decision_id.replace(":", "_") + ".json"),
                          dec.to_dict())
        util.append_jsonl(dlog, {"ts": _now(), "event": "decision_superseded",
                                "old": old_decision_id, "new": dec.decision_id})
        r["decision"] = dec.to_dict()
    return r


def reinject(*, out_dir=None) -> Dict[str, Any]:
    """生成约束再注入文件：后续每阶段逐字复述当前有效决定。"""
    _, _, _, rfile = _paths(out_dir)
    decs = active_decisions(out_dir=out_dir)
    rows = [{"decision_id": d.decision_id,
             "verbatim_text": d.verbatim_text,
             "applies_to_stages": [s for s in STAGE_IDS
                                   if STAGE_IDS.index(s) >= STAGE_IDS.index(d.stage)]
             if d.stage in STAGE_IDS else [],
             "constraints": {"chosen": d.chosen_option_id, "approver": d.approver}}
            for d in decs]
    payload = {"schema_version": "1.0", "generated_at": _now(),
               "decisions": rows, "n": len(rows),
               "decision_fp": decision_fp(out_dir=out_dir),
               "spec_hash_input": True}
    util.atomic_write(rfile, payload)
    return {"ok": True, "n": len(rows), "decision_fp": payload["decision_fp"]}


def load_reinjection(*, out_dir=None) -> Dict[str, Any]:
    _, _, _, rfile = _paths(out_dir)
    if not rfile.exists():
        return {"decisions": [], "n": 0, "decision_fp": util.sha256_json([]),
                "spec_hash_input": True}
    import json
    return json.loads(rfile.read_text(encoding="utf-8"))


def verbatim_for(stage: str, *, out_dir=None) -> List[str]:
    r = load_reinjection(out_dir=out_dir)
    return [x["verbatim_text"] for x in r.get("decisions", [])
            if stage in x.get("applies_to_stages", [])]
