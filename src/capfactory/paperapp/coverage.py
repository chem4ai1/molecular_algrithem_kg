"""H16 挖掘覆盖率雷达：复用 research/gaps.py 的 covered/partial/gap 三态。

不改语义层；只回答「语义层还有哪些字段/关系从未被任何 miner 消费」，
并把每个 gap 转成 KnowledgeSignal（I3）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from . import config, util
from . import signals

COVERAGE_FILE = config.NODE_CACHE / "MINING_COVERAGE.json"
COVERED_THRESHOLD = 0.52
PARTIAL_THRESHOLD = 0.32

# 语义层 v4.1 可挖掘面（只读清单，不新增类）
SEMANTIC_FIELDS = (
    ("Paper", "research_question", ("questions",)),
    ("Paper", "problem_category", ("categories",)),
    ("Paper", "flow_family", ("D3:lineage_slice",)),
    ("Paper", "why_hard", ()),
    ("Paper", "year", ("D3:lineage_slice",)),
    ("Algorithm", "mechanism", ("D2:method_benchmark_matrix",)),
    ("Algorithm", "limitations", ("limitations",)),
    ("AlgorithmModule", "inputs", ("D1:flow_closure",)),
    ("AlgorithmModule", "outputs", ("D1:flow_closure",)),
    ("AlgorithmModule", "formula", ()),
    ("CodeRepository", "url", ("D4:capability_cooccurrence",)),
    ("CodeFunction", "name", ("D4:capability_cooccurrence",)),
    ("CodeFunction", "purpose", ("D4:capability_cooccurrence",)),
    ("Benchmark", "metrics", ("metrics",)),
    ("Benchmark", "model_results", ("leaderboard",)),
    ("Benchmark", "input_form", ("D2:method_benchmark_matrix",)),
)
SEMANTIC_RELATIONS = (
    ("PROPOSES_METHOD", ("D2:method_benchmark_matrix",)),
    ("HAS_MODULE", ("D1:flow_closure",)),
    ("MODULE_IMPLEMENTED_BY", ("D4:capability_cooccurrence",)),
    ("EVALUATED_ON", ("D2:method_benchmark_matrix",)),
    ("RELATED_TO", ("D3:lineage_slice",)),
    ("HAS_FUNCTION", ("D4:capability_cooccurrence",)),
)
MINERS = ("questions", "categories", "metrics", "leaderboard", "contracts",
          "evidence", "limitations", "source_papers",
          "D1:flow_closure", "D2:method_benchmark_matrix",
          "D3:lineage_slice", "D4:capability_cooccurrence")


def _status(consumers) -> str:
    """复用 gaps.py 的评分口径：relevance × (0.35 + 0.65 × maturity)。"""
    if not consumers:
        return "gap"
    score = 1.0 * (0.35 + 0.65 * min(len(consumers) / 2.0, 1.0))
    if score >= COVERED_THRESHOLD:
        return "covered"
    if score >= PARTIAL_THRESHOLD:
        return "partial"
    return "gap"


def build(*, out_dir=None, emit_signals: bool = True) -> Dict[str, Any]:
    fields = [{"class": c, "name": f, "consumed_by": list(cs),
               "status": _status(cs)} for c, f, cs in SEMANTIC_FIELDS]
    rels = [{"relation": r, "consumed_by": list(cs), "status": _status(cs)}
            for r, cs in SEMANTIC_RELATIONS]
    rows = fields + rels
    covered = sum(1 for r in rows if r["status"] == "covered")
    ratio = covered / max(len(rows), 1)
    gaps = [r for r in rows if r["status"] == "gap"]
    if emit_signals:
        for r in gaps:
            key = r.get("name") or r.get("relation")
            signals.observe_event("mining_gap", key, stage="coverage",
                                  source="MINING_COVERAGE", out_dir=out_dir)
    payload = {
        "semantic_version": config.SEMANTIC_TBOX_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fields": fields, "assertions": rels,
        "miners": [{"name": m, "status": "covered", "n_outputs": 0} for m in MINERS],
        "coverage_ratio": round(ratio, 4),
        "n_gap_candidates": len(gaps),
        "gap_candidates": [{"id": "gap:" + (r.get("name") or r.get("relation")),
                            "reason": "字段/关系从未被任何挖掘器消费"} for r in gaps],
        "target": config.MINING_COVERAGE_TARGET,
    }
    p = Path(out_dir) / "MINING_COVERAGE.json" if out_dir else COVERAGE_FILE
    util.atomic_write(p, payload)
    return payload
