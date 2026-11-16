"""提案验证：字段契约 + 证据优先级 + 门判定。失败也生成信号（H12）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import config, registry, signals
from .schemas import LLMNodeProposal


def validate_proposal(p: LLMNodeProposal, *, spec: Optional[Dict[str, Any]] = None,
                      gate_state: str = "PASS", evidence_rank: int = 2,
                      out_dir=None) -> Dict[str, Any]:
    reasons = []
    if p.candidate_class not in registry.active_classes(out_dir=out_dir):
        reasons.append("class_not_active")
    if not p.attrs:
        reasons.append("empty_attrs")
    if p.attribution != "llm_proposal":
        reasons.append("missing_attribution")
    if not p.evidence_ids or evidence_rank > 3:
        reasons.append("weak_evidence")
    if gate_state not in ("PASS", "WARN"):
        reasons.append("gate_failed")
        signals.observe_event("gate_failed", p.canonical_id or p.proposal_id,
                              stage=p.stage, paper_id=p.paper_id, run_id=p.run_id,
                              source=f"gate.{gate_state}", out_dir=out_dir)
    p.validation = {"field_contract": "PASS" if not reasons else "FAIL",
                    "evidence_rank": evidence_rank, "gates": [gate_state],
                    "conflicts": reasons}
    if reasons:
        return {"ok": False, "action": "hold", "reason_code": reasons[0],
                "reasons": reasons, "proposal": p}
    p.status = "validated"
    p.valid_from = p.valid_from or ""
    from . import nodecache
    nodecache.save_proposal(p, out_dir=out_dir)
    return {"ok": True, "action": "validated", "reason_code": "ok",
            "proposal": p}
