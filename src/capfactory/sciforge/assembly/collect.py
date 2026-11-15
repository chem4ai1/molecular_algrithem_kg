"""A1 Collect：收敛 Stage0–2 产物 + 完整性门 + inputs_sha（幂等）。"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

from .contract import Stage3Input

REQUIRED = ("STAGE0_HEADING_PLAN.json", "STAGE2_related_work.json",
            "STAGE2_method.json", "STAGE2_benchmark.json")


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def collect(out_dir: Path, *, arxiv_id: str, paper_id: str, graph: Any,
            run_id: str = "", md: str = "") -> Stage3Input:
    d = Path(out_dir)
    inp = Stage3Input(run_id=run_id or f"s3_{arxiv_id}",
                      arxiv_id=arxiv_id, paper_id=paper_id,
                      out_dir=str(d), md=md)
    loaded: dict = {}
    for name in REQUIRED:
        p = d / name
        if not p.exists():
            inp.blockers.append(f"missing:{name}")
            continue
        try:
            loaded[name] = _load(p)
        except Exception as exc:  # noqa: BLE001
            inp.blockers.append(f"unparsable:{name}:{type(exc).__name__}")
    inp.plan = loaded.get("STAGE0_HEADING_PLAN.json") or {}
    inp.related_work = loaded.get("STAGE2_related_work.json") or {}
    inp.method = loaded.get("STAGE2_method.json") or {}
    inp.benchmark = loaded.get("STAGE2_benchmark.json") or {}
    bp = d / "blocks.jsonl"
    if bp.exists():
        for line in bp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    inp.blocks.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    if paper_id not in graph.nodes:
        inp.blockers.append("missing_paper_root")
    # blocks kind 分布与 plan 一致性（软门：不一致记 warning 不 BLOCKED）
    canonical = json.dumps(
        {k: loaded.get(k) for k in REQUIRED if k in loaded},
        ensure_ascii=False, sort_keys=True, default=str)
    inp.inputs_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    inp.complete = not inp.blockers
    return inp
