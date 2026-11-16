"""Q2 实体解析：规范化 → 受控词表 → 同域近邻 → 四态 action。

硬性红线：不同 paper_id 之间永不因相似而 reuse（防跨论文假事实）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from . import config, registry, signals, util
from .schemas import LLMNodeProposal, NodeCacheEntry


def normalize(s: str) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("＄", "$").replace("（", "(").replace("）", ")")
    return re.sub(r"[\s_\-/:：,，;；、|]+", "-", s).strip("-")


def canonical_id(cls: str, label: str, *, paper_id: str = "") -> str:
    arxiv = paper_id.split(":")[-1] if paper_id else "global"
    return f"app{normalize(cls)}:{arxiv}:{normalize(label)[:48]}"


def _ngrams(s: str, n: int = 3) -> Dict[str, float]:
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalize(s))
    toks = [s[i:i + n] for i in range(max(len(s) - n + 1, 1))]
    out: Dict[str, float] = {}
    for t in toks:
        out[t] = out.get(t, 0.0) + 1.0
    norm = sum(v * v for v in out.values()) ** 0.5 or 1.0
    return {k: v / norm for k, v in out.items()}


def similarity(a: str, b: str) -> float:
    x, y = _ngrams(a), _ngrams(b)
    if len(x) > len(y):
        x, y = y, x
    return float(sum(v * y.get(k, 0.0) for k, v in x.items()))


def _nodes_dir(out_dir=None) -> Path:
    return Path(out_dir) / "nodes" if out_dir else config.NODES_DIR


def _registered_ids(out_dir=None) -> Dict[str, NodeCacheEntry]:
    d = _nodes_dir(out_dir)
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            e = NodeCacheEntry(**json.loads(p.read_text(encoding="utf-8")))
            out[e.canonical_id] = e
        except (ValueError, TypeError, OSError):
            continue
    return out


def align(proposal: LLMNodeProposal, *, out_dir=None,
          emit_signal: bool = True) -> Dict[str, Any]:
    from .tbox import PAPERAPP_CLASS_VOCAB
    cid = proposal.canonical_id or canonical_id(
        proposal.candidate_class, str(proposal.attrs.get("value", proposal.proposal_id)),
        paper_id=proposal.paper_id)
    reg = _registered_ids(out_dir)
    # 1) 精确命中
    if cid in reg:
        e = reg[cid]
        return {"action": "reuse", "canonical_id": cid,
                "node": e.to_dict(), "conflicts": [],
                "proposal_reason": "exact_hit", "use_count": e.use_count}
    # 2) 受控词表
    if proposal.candidate_class not in PAPERAPP_CLASS_VOCAB:
        _conflict(proposal, cid, "unregistered_class", 0.0, out_dir, emit_signal)
        return {"action": "proposal", "canonical_id": cid,
                "conflicts": ["unregistered_class"],
                "proposal_reason": "class_not_in_vocab"}
    if proposal.candidate_class not in registry.active_classes(out_dir=out_dir):
        _conflict(proposal, cid, "class_not_active", 0.0, out_dir, emit_signal)
        return {"action": "proposal", "canonical_id": cid,
                "conflicts": ["class_not_active"],
                "proposal_reason": "class_not_active"}
    # 3) 同 paper_id + 同 stage 近邻
    text = str(proposal.attrs.get("value", proposal.canonical_id))
    best, best_score = None, 0.0
    from . import nodecache
    for p in nodecache.load_proposals(out_dir=out_dir):
        if p.proposal_id == proposal.proposal_id:
            continue
        if p.paper_id != proposal.paper_id or p.stage != proposal.stage:
            continue          # 跨论文 / 跨阶段绝不复用
        sc = similarity(text, str(p.attrs.get("value", p.canonical_id)))
        if sc > best_score:
            best, best_score = p, sc
    if best is not None and best_score >= config.SIM_REUSE:
        _conflict(proposal, cid, "near_duplicate_resolved", best_score,
                  out_dir, emit_signal)
        return {"action": "reuse", "canonical_id": best.canonical_id or cid,
                "conflicts": [], "proposal_reason": "near_duplicate_same_paper",
                "score": round(best_score, 4)}
    if best is not None and best_score >= config.SIM_AMBIGUOUS:
        _conflict(proposal, cid, "ambiguous_duplicate", best_score,
                  out_dir, emit_signal)
        return {"action": "proposal", "canonical_id": cid,
                "conflicts": ["ambiguous_duplicate"],
                "proposal_reason": "ambiguous_duplicate", "score": round(best_score, 4)}
    if emit_signal:
        signals.observe_event("align_unmatched", cid, stage=proposal.stage,
                              paper_id=proposal.paper_id, run_id=proposal.run_id,
                              source="align", out_dir=out_dir)
    return {"action": "proposal", "canonical_id": cid, "conflicts": [],
            "proposal_reason": "new_candidate"}


def _conflict(p, cid, reason, score, out_dir, emit_signal) -> None:
    import time
    base = Path(out_dir) if out_dir else config.NODE_CACHE
    util.append_jsonl(base / "conflicts" / "CONFLICT_LOG.jsonl",
                      {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "proposal_id": p.proposal_id, "canonical_id": cid,
                       "reason": reason, "score": score,
                       "resolution": "hold_for_human" if reason == "ambiguous_duplicate"
                       else reason})
    if emit_signal:
        signals.observe_event("align_unmatched", cid, stage=p.stage,
                              paper_id=p.paper_id, run_id=p.run_id,
                              source=f"align.{reason}", out_dir=out_dir)
