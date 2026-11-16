"""I3 全谱留痕：探索中的未命中/被拒/失败/未尝试方向都成为可查询节点。

捕捉率 100%（H12），晋升率可控。被 dismissed 也写理由，绝不删除。
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from . import config, util

SIGNAL_LOG = config.NODE_CACHE / "SIGNAL_LOG.jsonl"
CLUSTERS_FILE = config.NODE_CACHE / "SignalCluster.json"

# 5 类必须产生信号的事件
SIGNAL_KINDS = (
    "vocab_out_of_list", "align_unmatched", "gate_failed",
    "mining_gap", "human_direction_unadopted",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class KnowledgeSignal:
    signal_id: str
    kind: str
    value: str
    stage: str = ""
    paper_id: str = ""
    run_id: str = ""
    source: str = ""
    count: int = 1
    status: str = "observed"       # observed|clustered|promoted_to_proposal|dismissed
    evidence_ids: List[str] = field(default_factory=list)
    promoted_to: str = ""
    dismiss_reason: str = ""
    first_seen: str = ""
    last_seen: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _signal_id(kind: str, value: str, paper_id: str, stage: str) -> str:
    return "sig:" + util.sha256_json([kind, str(value), paper_id, stage])[7:23]


def _spath(signal_id: str, out_dir=None) -> Path:
    base = Path(out_dir) / "signals" if out_dir else config.SIGNALS_DIR
    return base / (signal_id.replace(":", "_") + ".json")


def _slog(out_dir=None) -> Path:
    return Path(out_dir) / "SIGNAL_LOG.jsonl" if out_dir else SIGNAL_LOG


def _scluster(out_dir=None) -> Path:
    return Path(out_dir) / "SignalCluster.json" if out_dir else CLUSTERS_FILE


def observe_event(kind: str, value: str, *, stage: str = "", paper_id: str = "",
                  run_id: str = "", source: str = "", evidence_ids=None,
                  out_dir=None) -> Dict[str, Any]:
    """幂等：同一 (kind,value,paper,stage) 只累计 count，不重复建节点。"""
    value = str(value or "").strip()
    if not value:
        return {"ok": False, "action": "reject", "reason_code": "empty_value"}
    sid = _signal_id(kind, value, paper_id, stage)
    p = _spath(sid, out_dir)
    if p.exists():
        try:
            import json
            s = KnowledgeSignal(**json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, TypeError, OSError):
            s = None
        if s is not None:
            s.count += 1
            s.last_seen = _now()
            if source and source not in s.source:
                s.source = (s.source + "," + source).strip(",")
            util.atomic_write(p, s.to_dict())
            util.append_jsonl(_slog(out_dir), {"ts": _now(), "event": "signal_seen",
                                              "signal_id": sid, "count": s.count})
            return {"ok": True, "action": "incremented", "signal_id": sid,
                    "count": s.count, "reason_code": "ok"}
    s = KnowledgeSignal(signal_id=sid, kind=kind, value=value, stage=stage,
                        paper_id=paper_id, run_id=run_id, source=source,
                        evidence_ids=list(evidence_ids or []),
                        first_seen=_now(), last_seen=_now())
    util.atomic_write(p, s.to_dict())
    util.append_jsonl(_slog(out_dir), {"ts": _now(), "event": "signal_created",
                                      "signal_id": sid, "kind": kind,
                                      "value": value, "stage": stage,
                                      "paper_id": paper_id, "run_id": run_id})
    return {"ok": True, "action": "created", "signal_id": sid, "count": 1,
            "reason_code": "ok"}


def load_signals(*, out_dir=None) -> List[KnowledgeSignal]:
    base = Path(out_dir) / "signals" if out_dir else config.SIGNALS_DIR
    out: List[KnowledgeSignal] = []
    if not base.exists():
        return out
    for p in sorted(base.glob("*.json")):
        try:
            import json
            out.append(KnowledgeSignal(**json.loads(p.read_text(encoding="utf-8"))))
        except (ValueError, TypeError, OSError):
            continue
    return out


def cluster_signals(*, out_dir=None) -> Dict[str, Any]:
    """按 value 规范化聚类；frequency >= PROMOTE_AFTER 的簇成为扩表/提案候选。"""
    clusters: Dict[str, List[str]] = {}
    for s in load_signals(out_dir=out_dir):
        if s.status == "dismissed":
            continue
        key = str(s.value).strip().lower()
        clusters.setdefault(key, []).append(s.signal_id)
    rows = [{"cluster_id": "cl:" + util.sha256_json(k)[7:19],
             "representative": k, "members": sorted(set(v)),
             "frequency": sum(1 for s in load_signals(out_dir=out_dir)
                              if s.value.strip().lower() == k),
             "promotable": len(v) >= config.PROMOTE_AFTER}
            for k, v in clusters.items()]
    util.atomic_write(_scluster(out_dir), {"clusters": rows, "n": len(rows),
                                          "updated_at": _now()})
    return {"ok": True, "n_clusters": len(rows),
            "n_promotable": sum(1 for r in rows if r["promotable"])}


def dismiss_signal(signal_id: str, *, reason: str, out_dir=None) -> Dict[str, Any]:
    """I3：不删除，只标 dismissed + 理由。"""
    p = _spath(signal_id, out_dir)
    if not p.exists():
        return {"ok": False, "reason_code": "signal_not_found"}
    import json
    s = KnowledgeSignal(**json.loads(p.read_text(encoding="utf-8")))
    s.status = "dismissed"
    s.dismiss_reason = reason
    util.atomic_write(p, s.to_dict())
    util.append_jsonl(_slog(out_dir), {"ts": _now(), "event": "signal_dismissed",
                                      "signal_id": signal_id, "reason": reason})
    return {"ok": True, "action": "dismissed", "reason_code": "ok"}


def signal_stats(*, expected_events: int = 0, out_dir=None) -> Dict[str, Any]:
    sigs = load_signals(out_dir=out_dir)
    captured = len(sigs) + sum(s.count - 1 for s in sigs)
    dismissed = [s for s in sigs if s.status == "dismissed"]
    return {
        "n_signals": len(sigs), "n_events": captured,
        "expected_events": expected_events,
        "signal_capture_rate": 1.0 if expected_events == 0 else
            min(1.0, captured / max(expected_events, 1)),
        "by_kind": {k: sum(1 for s in sigs if s.kind == k) for k in SIGNAL_KINDS},
        "n_dismissed": len(dismissed),
        "dismiss_with_reason_rate": 1.0 if not dismissed else
            sum(1 for s in dismissed if s.dismiss_reason) / len(dismissed),
    }
