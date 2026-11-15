"""Stage3 装配层契约（蓝图 §3.5）。

Stage3 = Assembly：只把 Stage0–2 产物确定性导入图谱，不产生新事实、不调 LLM。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List

FORM_VOCAB = ("SMILES", "3D坐标", "向量", "图", "序列", "分布", "标量", "文本")
TREE_RELS = ("HAS_LIMITATION", "ADDRESSED_BY", "IMPROVED_BY", "REPLACES",
             "REPLACED_BY", "BELONGS_TO", "COMPARES_WITH", "ON_METRIC", "DELTA")


@dataclass
class Stage3Input:
    run_id: str; arxiv_id: str; paper_id: str; out_dir: str
    plan: Dict[str, Any] = field(default_factory=dict)
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    related_work: Dict[str, Any] = field(default_factory=dict)
    method: Dict[str, Any] = field(default_factory=dict)
    benchmark: Dict[str, Any] = field(default_factory=dict)
    md: str = ""
    inputs_sha: str = ""
    complete: bool = False
    blockers: List[str] = field(default_factory=list)


@dataclass
class NormalizedInput:
    forms: Dict[str, Any] = field(default_factory=dict)
    metrics: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    baselines: List[str] = field(default_factory=list)
    code_symbols: List[str] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    benchmarks: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    tree_edges: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    metric_proposals: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LinkPlan:
    paper_root: str = ""
    algorithm_roots: List[str] = field(default_factory=list)
    benchmark_roots: List[str] = field(default_factory=list)
    root_edges: List[Dict[str, str]] = field(default_factory=list)
    source_refs: List[Dict[str, Any]] = field(default_factory=list)
    ast_hits: List[str] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Stage3Manifest:
    run_id: str; arxiv_id: str; paper_id: str
    inputs_sha: str = ""; tbox_hash: str = ""
    a1: Dict[str, Any] = field(default_factory=dict)
    a2: Dict[str, Any] = field(default_factory=dict)
    a3: Dict[str, Any] = field(default_factory=dict)
    a4: Dict[str, Any] = field(default_factory=dict)
    a5: Dict[str, Any] = field(default_factory=dict)
    nodes_added: Dict[str, int] = field(default_factory=dict)
    edges_added: Dict[str, int] = field(default_factory=dict)
    csv_rows: Dict[str, int] = field(default_factory=dict)
    pg_rows: int = 0
    sota_changes: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gate: str = "BLOCKED"
    skipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}
