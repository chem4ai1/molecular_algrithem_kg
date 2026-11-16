"""PaperSpec：零 LLM、幂等编译（H6 / H15）。

spec_hash 纳入 semantic_sha + rules + decisions，人的决定改变即重算。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, coverage, hitl, miners, registry, signals, util


@dataclass
class PaperSpec:
    paper_id: str
    arxiv_id: str
    semantic_sha: str
    dynamic_tbox_version: str
    decision_fp: str
    stage_order: List[str]
    domain_profile: Dict[str, Any] = field(default_factory=dict)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    ideas: List[Dict[str, Any]] = field(default_factory=list)
    frontier: List[Dict[str, Any]] = field(default_factory=list)
    human_decisions: List[Dict[str, Any]] = field(default_factory=list)
    mining_coverage: Dict[str, Any] = field(default_factory=dict)
    signals_summary: Dict[str, Any] = field(default_factory=dict)
    derived: Dict[str, Any] = field(default_factory=dict)
    verdicts: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    spec_hash: str = ""

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("spec_hash", None)
        return util.sha256_json(d)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, out_dir: str | Path) -> str:
        p = Path(out_dir) / "PAPER_SPEC.json"
        util.atomic_write(p, self.to_dict())
        return str(p)

    @classmethod
    def load(cls, path: str | Path) -> "PaperSpec":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def compile_paperspec(graph=None, paper_id: str = "", *, out_dir=None,
                      decisions=None, include_derived: bool = True) -> PaperSpec:
    """纯确定性：只读图 + 注册表 + 决定日志；绝不调用 LLM。"""
    if graph is None:
        graph = util.load_graph()
    g = getattr(graph, "nodes", {}) or {}
    arxiv = paper_id.split(":")[-1] if paper_id else ""
    d = registry.load_registry(out_dir=out_dir)
    decs = [x.to_dict() for x in
            (decisions if decisions is not None else hitl.active_decisions(out_dir=out_dir))]
    fp = hitl.decision_fp(out_dir=out_dir) if decisions is None else \
        util.sha256_json(sorted((x.get("decision_id", ""), x.get("chosen_option_id", ""))
                                for x in decs))
    gaps = []
    ideas = []
    for nid, n in sorted(g.items()):
        t = str(getattr(n, "type", ""))
        a = dict(getattr(n, "attrs", {}) or {})
        if t == "ResearchGap" or a.get("gap_id"):
            gaps.append({"id": nid, **a})
        if t == "IdeaNode" or a.get("falsifiable_claim"):
            ideas.append({"id": nid, **a})
    derived = miners.run_derived(graph) if include_derived else {"derived": {}, "n_miners": 0}
    cov = {"coverage_ratio": None, "n_gap_candidates": 0}
    p = Path(out_dir) / "MINING_COVERAGE.json" if out_dir else \
        config.NODE_CACHE / "MINING_COVERAGE.json"
    if p.exists():
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            cov = {"coverage_ratio": c.get("coverage_ratio"),
                   "n_gap_candidates": c.get("n_gap_candidates", 0)}
        except (ValueError, OSError):
            pass
    warnings = []
    if not gaps:
        warnings.append("no_gap_nodes_in_graph")
    if not ideas:
        warnings.append("no_idea_nodes_in_graph")
    spec = PaperSpec(
        paper_id=paper_id, arxiv_id=arxiv,
        semantic_sha=util.sha256_file(config.SEMANTIC_GRAPH),
        dynamic_tbox_version=d.get("version", config.DYNAMIC_TBOX_VERSION),
        decision_fp=fp, stage_order=list(config.STAGE_IDS),
        domain_profile={}, gaps=gaps[:200], ideas=ideas[:200],
        frontier=derived["derived"].get("D3", {}).get("frontier_nodes", [])[:50],
        human_decisions=decs, mining_coverage=cov,
        signals_summary=signals.signal_stats(out_dir=out_dir),
        derived={k: {"n": v.get("n", v.get("n_edges", v.get("n_cells", 0))),
                     "miner": v.get("miner", k)}
                 for k, v in derived["derived"].items()},
        verdicts={}, warnings=warnings)
    spec.spec_hash = spec.compute_hash()
    return spec
