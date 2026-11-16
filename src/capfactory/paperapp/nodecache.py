"""L1 请求级幂等缓存 + L2 提案缓存（v2：cache_identity 含 decision_fp）。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from . import config, hitl, signals, util
from .schemas import LLMNodeProposal, RequestCacheEntry


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def cache_identity(task: str, stage: str, input_nodes, *, effort: str = "balanced",
                   model_id: str = "stub", prompt_version: str = "v1",
                   decision_fp: str = "", semantic_fp: str = "",
                   dynamic_version: str = "") -> Dict[str, Any]:
    ids = sorted(str(x) for x in (input_nodes or []))
    return {
        "task": task, "stage": stage,
        "input_fp": util.sha256_json(ids),
        "semantic_fp": semantic_fp or util.sha256_file(config.SEMANTIC_GRAPH),
        "tbox_version": config.SEMANTIC_TBOX_VERSION + "@" +
                        (dynamic_version or config.DYNAMIC_TBOX_VERSION),
        "prompt_version": prompt_version, "model_id": model_id,
        "effort": effort, "decision_fp": decision_fp,
    }


def request_key(identity: Dict[str, Any]) -> str:
    return "rq:" + util.sha256_json(identity)[7:39]


def _rpath(key: str, out_dir=None) -> Path:
    base = Path(out_dir) / "requests" if out_dir else config.REQUESTS_DIR
    return base / (key.replace(":", "_") + ".json")


def _ppath(pid: str, out_dir=None) -> Path:
    base = Path(out_dir) / "proposals" if out_dir else config.PROPOSALS_DIR
    return base / (pid.replace(":", "_") + ".json")


def get_or_call(identity: Dict[str, Any], call_llm: Callable, *,
                out_dir=None) -> tuple[RequestCacheEntry, bool]:
    """命中 → 不调 LLM；未命中 → 调用、写 L1、返回 hit=False。"""
    key = request_key(identity)
    p = _rpath(key, out_dir)
    if p.exists():
        try:
            e = RequestCacheEntry(**json.loads(p.read_text(encoding="utf-8")))
            e.hit_count += 1
            util.atomic_write(p, e.to_dict())
            return e, True
        except (ValueError, TypeError, OSError):
            pass
    raw = call_llm()
    e = RequestCacheEntry(
        request_key=key, cache_identity=identity, stage=identity.get("stage", ""),
        paper_id=str(identity.get("paper_id", "")), raw_output=raw,
        output_sha=util.sha256_json(raw), prompt_sha=util.sha256_json(
            identity.get("prompt_version", "")),
        input_sha=identity.get("input_fp", ""),
        code_sha=util.sha256_json(config.DYNAMIC_TBOX_VERSION),
        model_id=identity.get("model_id", "stub"),
        prompt_version=identity.get("prompt_version", "v1"),
        decision_fp=identity.get("decision_fp", ""), recorded_at=_now())
    util.atomic_write(p, e.to_dict())
    return e, False


def put_proposal(entry: RequestCacheEntry, raw: Any, *, stage: str = "",
                 paper_id: str = "", run_id: str = "", candidate_class: str = "",
                 canonical_id: str = "", origin: str = "machine",
                 signal_id: str = "", out_dir=None) -> LLMNodeProposal:
    pid = "prop:" + util.sha256_json([entry.request_key, canonical_id, _now(),
                                      stage, origin])[7:23]
    p = LLMNodeProposal(
        proposal_id=pid, request_key=entry.request_key, run_id=run_id,
        paper_id=paper_id, stage=stage,
        candidate_class=candidate_class, canonical_id=canonical_id,
        attrs=raw if isinstance(raw, dict) else {"value": str(raw)},
        attribution="llm_proposal", miner=f"paperapp.s1.{stage}",
        origin=origin, signal_id=signal_id, recorded_at=_now())
    util.atomic_write(_ppath(pid, out_dir), p.to_dict())
    signals.observe_event("align_unmatched", canonical_id or pid, stage=stage,
                          paper_id=paper_id, run_id=run_id,
                          source="nodecache.put_proposal", out_dir=out_dir)
    return p


def load_proposals(run_id: str = "", *, out_dir=None) -> List[LLMNodeProposal]:
    base = Path(out_dir) / "proposals" if out_dir else config.PROPOSALS_DIR
    out = []
    if not base.exists():
        return out
    for p in sorted(base.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if run_id and d.get("run_id") != run_id:
                continue
            out.append(LLMNodeProposal(**d))
        except (ValueError, TypeError, OSError):
            continue
    return out


def save_proposal(p: LLMNodeProposal, *, out_dir=None) -> None:
    util.atomic_write(_ppath(p.proposal_id, out_dir), p.to_dict())


def invalidate(key: str, *, reason: str, out_dir=None) -> Dict[str, Any]:
    """不删除 L1 文件，只写 INVALIDATIONS.jsonl 并标 valid_to。"""
    p = _rpath(key, out_dir)
    base = Path(out_dir) if out_dir else config.NODE_CACHE
    util.append_jsonl(base / "INVALIDATIONS.jsonl",
                      {"ts": _now(), "key": key, "reason": reason,
                       "valid_to": _now(), "existed": p.exists()})
    return {"ok": True, "key": key, "valid_to": _now(), "reason_code": "ok"}


def cache_status(*, out_dir=None) -> Dict[str, Any]:
    base = Path(out_dir) / "requests" if out_dir else config.REQUESTS_DIR
    files = list(base.glob("*.json")) if base.exists() else []
    hits = total = 0
    for f in files:
        try:
            e = RequestCacheEntry(**json.loads(f.read_text(encoding="utf-8")))
            hits += e.hit_count
            total += 1
        except (ValueError, TypeError, OSError):
            continue
    sigs = signals.signal_stats(out_dir=out_dir)
    return {"n_requests": total, "n_hits": hits,
            "cache_hit_rate": round(hits / max(total + hits, 1), 4),
            "n_proposals": len(load_proposals(out_dir=out_dir)),
            "n_signals": sigs["n_signals"],
            "decision_fp": hitl.decision_fp(out_dir=out_dir)}
