"""四个核心数据结构（v2：RequestCacheEntry 增加 decision_fp，提案增加 origin/signal_id）。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class RequestCacheEntry:
    request_key: str
    cache_identity: Dict[str, Any]
    stage: str
    paper_id: str
    raw_output: Any
    output_sha: str
    prompt_sha: str = ""
    input_sha: str = ""
    code_sha: str = ""
    model_id: str = "stub"
    prompt_version: str = "v1"
    tokens_in: int = 0
    tokens_out: int = 0
    recorded_at: str = ""
    hit_count: int = 0
    n_proposals: int = 0
    decision_fp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LLMNodeProposal:
    proposal_id: str
    request_key: str
    run_id: str
    paper_id: str = ""
    stage: str = ""
    status: str = "proposed"     # proposed|validated|registered|deprecated|rejected
    kind: str = "instance"       # instance|class|relation
    candidate_class: str = ""
    registration_id: str = ""
    canonical_id: str = ""
    attrs: Dict[str, Any] = field(default_factory=dict)
    relation_candidates: List[Dict[str, str]] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    attribution: str = "llm_proposal"
    layer: str = "application"
    task: str = "generation"
    miner: str = ""
    origin: str = "machine"      # machine|human|signal
    signal_id: str = ""
    confidence: float = 0.0
    validation: Dict[str, Any] = field(default_factory=dict)
    valid_from: str = ""
    valid_to: str = ""
    recorded_at: str = ""
    supersedes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NodeCacheEntry:
    canonical_id: str
    registration_id: str = ""
    proposal_id: str = ""
    status: str = "registered"
    layer: str = "application"
    task: str = "generation"
    use_count: int = 0
    first_seen: str = ""
    last_used: str = ""
    valid_from: str = ""
    valid_to: str = ""
    source_runs: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    spec_hash: str = ""
    supersedes: str = ""
    deprecated_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PromotionRecord:
    ts: str
    proposal_id: str
    from_state: str
    to_state: str
    rule: str
    approver: str
    run_id: str
    registry_version: str
    canonical_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["from"] = d.pop("from_state")
        d["to"] = d.pop("to_state")
        return d
