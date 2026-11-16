"""S1 增量 6a：`semantic/extraction/vocab.observe()` → `KnowledgeSignal` 桥接。

**不改 vocab.py 的任何行为**。提供两个入口：

1. `observe_and_signal(name, value, ...)` —— 上游抽取遇到 `other/proposed_new` 时
   调用它替代直接调 `vocab.observe()`：原函数照常累计/自动扩表，同时把
   「词表外新概念」这件事变成一等 KnowledgeSignal 节点（I3 全谱留痕）。
2. `bridge_existing(...)` —— 把已有 `vocab.json` 里的 `candidates` / `promoted`
   批量镜像成信号，用于补历史、启动自检与 v2 迁移。

信号幂等键 = sha256(kind, value, paper_id, stage)；重复出现只累加 count。
`promoted=True` 时额外写一条 `vocab_promoted` 信号，便于审计扩表何时发生。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from capfactory.semantic.extraction import vocab as _vocab

from . import config, signals, util


def _read_vocab(mod) -> Dict[str, Any]:
    """只读消费 vocab 的内部状态；优先用模块自己的 _load()（尊重 mock.patch）。"""
    try:
        return mod._load()
    except Exception:  # noqa: BLE001
        p = Path(getattr(mod, "VOCAB_FILE", config.NODE_CACHE / "vocab.json"))
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
    return {"promoted": {}, "candidates": {}}


def observe_and_signal(name: str, value: str, *, stage: str = "",
                       paper_id: str = "", run_id: str = "", out_dir=None,
                       vocab_module=None) -> Dict[str, Any]:
    """替代直接调用 vocab.observe()：一次调用同时完成扩表计数与信号捕捉。"""
    mod = vocab_module or _vocab
    res = mod.observe(name, value)
    if not res.get("observed"):
        return {"ok": True, "action": "ignored", "reason_code": res.get("observed", False)
                and "ok" or "not_out_of_vocab", "vocab": res, "signal_id": ""}
    sig = signals.observe_event(
        "vocab_out_of_list", res.get("value", str(value)),
        stage=stage, paper_id=paper_id, run_id=run_id,
        source=f"vocab.{name}", out_dir=out_dir)
    if res.get("promoted"):
        signals.observe_event(
            "vocab_out_of_list", f"PROMOTED::{name}::{res['value']}",
            stage=stage, paper_id=paper_id, run_id=run_id,
            source=f"vocab.{name}.promote", out_dir=out_dir)
    return {"ok": True, "action": "bridged", "reason_code": "ok",
            "vocab": res, "signal_id": sig.get("signal_id", ""),
            "promoted": bool(res.get("promoted"))}


def bridge_existing(*, stage: str = "migration", paper_id: str = "",
                    run_id: str = "", out_dir=None,
                    vocab_module=None) -> Dict[str, Any]:
    """把 vocab.json 里已有的候选与已扩表值批量镜像成信号（幂等）。"""
    mod = vocab_module or _vocab
    d = _read_vocab(mod)
    n_cand = n_prom = 0
    for name, cands in (d.get("candidates") or {}).items():
        for value, _count in (cands or {}).items():
            r = signals.observe_event(
                "vocab_out_of_list", str(value), stage=stage,
                paper_id=paper_id, run_id=run_id,
                source=f"vocab.{name}.candidate", out_dir=out_dir)
            n_cand += int(r.get("ok", False))
    for name, vals in (d.get("promoted") or {}).items():
        for value in vals or []:
            r = signals.observe_event(
                "vocab_out_of_list", f"PROMOTED::{name}::{value}",
                stage=stage, paper_id=paper_id, run_id=run_id,
                source=f"vocab.{name}.promoted", out_dir=out_dir)
            n_prom += int(r.get("ok", False))
    stats = signals.signal_stats(out_dir=out_dir)
    config.ensure_dirs()
    p = Path(out_dir) / "VOCAB_BRIDGE.json" if out_dir else \
        config.NODE_CACHE / "VOCAB_BRIDGE.json"
    util.atomic_write(p, {"n_candidates": n_cand, "n_promoted": n_prom,
                          "vocab_stats": mod.stats(), "signal_stats": stats,
                          "version": "v2-s1-6a"})
    return {"ok": True, "action": "bridged_existing",
            "reason_code": "ok", "n_candidates": n_cand,
            "n_promoted": n_prom, "signal_stats": stats}
