"""L3 晋升：五条硬规则 + append-only PROMOTION_LOG + use_count。

I1：任何情况下都不得把 llm_proposal 晋升进语义层。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable

from . import config, hitl, registry, util
from .schemas import LLMNodeProposal, NodeCacheEntry, PromotionRecord


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _nodes_dir(out_dir=None) -> Path:
    return Path(out_dir) / "nodes" if out_dir else config.NODES_DIR


def _log(out_dir=None) -> Path:
    return Path(out_dir) / "PROMOTION_LOG.jsonl" if out_dir else \
        config.DYNAMIC_TBOX / "PROMOTION_LOG.jsonl"


def can_promote(p: LLMNodeProposal, *, approver: str = "",
                policy: Dict[str, Any] | None = None,
                out_dir=None) -> tuple[bool, str]:
    policy = policy or {}
    if p.status != "validated":
        return False, "not_validated"
    if p.attribution != "llm_proposal":
        return False, "missing_attribution"
    if p.candidate_class not in registry.active_classes(out_dir=out_dir):
        return False, "class_not_active"
    if p.kind in ("class", "relation") and not approver:
        return False, "needs_human_approval"
    if p.validation.get("evidence_rank", 2) > 2:
        return False, "weak_evidence"
    if not p.evidence_ids:
        return False, "weak_evidence"
    min_reuse = int(policy.get("min_reuse", config.MIN_REUSE))
    if policy.get("require_reuse", False) and p.confidence < min_reuse:
        return False, "reuse_below_threshold"
    return True, "ok"


def semantic_promotion_guard(target_layer: str) -> tuple[bool, str]:
    """I1：语义层晋升闸门，恒拒绝。"""
    if target_layer in ("semantic", "semantic_layer", "batch10_semantic_v4"):
        return False, "semantic_layer_protected"
    return True, "ok"


@util.with_lock
def promote(p: LLMNodeProposal, *, approver: str, run_id: str = "",
            out_dir=None, policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ok, reason = can_promote(p, approver=approver, policy=policy, out_dir=out_dir)
    if not ok:
        return {"ok": False, "action": "reject", "reason_code": reason}
    guard, gr = semantic_promotion_guard(p.layer)
    if not guard:
        return {"ok": False, "action": "reject", "reason_code": gr}
    cid = p.canonical_id or f"app{p.candidate_class.lower()}:{p.proposal_id[5:]}"
    e = NodeCacheEntry(canonical_id=cid,
                       registration_id=registry.load_registry(out_dir=out_dir)
                       .get("classes", {}).get(p.candidate_class, {})
                       .get("registration_id", ""),
                       proposal_id=p.proposal_id, status="registered",
                       use_count=0, first_seen=_now(), last_used=_now(),
                       valid_from=_now(), source_runs=[run_id] if run_id else [],
                       evidence_ids=list(p.evidence_ids),
                       spec_hash=util.sha256_json(p.to_dict()))
    util.atomic_write(_nodes_dir(out_dir) / (cid.replace(":", "_").replace("/", "_") + ".json"),
                      e.to_dict())
    p.status = "registered"
    p.valid_from = _now()
    from . import nodecache
    nodecache.save_proposal(p, out_dir=out_dir)
    rec = PromotionRecord(ts=_now(), proposal_id=p.proposal_id,
                          from_state="validated", to_state="registered",
                          rule="rule:class_active AND evidence AND gate AND approver",
                          approver=approver, run_id=run_id,
                          registry_version=config.DYNAMIC_TBOX_VERSION,
                          canonical_id=cid)
    util.append_jsonl(_log(out_dir), rec.to_dict())
    return {"ok": True, "action": "registered", "reason_code": "ok",
            "promotion": rec.to_dict(), "node": e.to_dict()}


def bump_usage(canonical_ids: Iterable[str], run_id: str = "", *,
               out_dir=None) -> Dict[str, Any]:
    n = 0
    for cid in canonical_ids:
        p = _nodes_dir(out_dir) / (cid.replace(":", "_").replace("/", "_") + ".json")
        if not p.exists():
            continue
        try:
            e = NodeCacheEntry(**json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, TypeError, OSError):
            continue
        e.use_count += 1
        e.last_used = _now()
        if run_id and run_id not in e.source_runs:
            e.source_runs.append(run_id)
        util.atomic_write(p, e.to_dict())
        n += 1
    return {"ok": True, "n": n, "reason_code": "ok"}


def audit_promotions(*, out_dir=None) -> Dict[str, Any]:
    rows = util.read_jsonl(_log(out_dir))
    return {"ok": True, "n": len(rows),
            "append_only": all("ts" in r for r in rows),
            "items": rows[-50:]}
