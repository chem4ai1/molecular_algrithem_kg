"""复现框架契约：只引用图里的 id 与属性快照，关系以链表达（属性/关系分离）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

VERDICTS = ("PASS", "PARTIAL", "BLOCKED")


@dataclass
class GateResult:
    phase: str
    verdict: str = "BLOCKED"
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {"phase": self.phase, "verdict": self.verdict,
                "reasons": self.reasons, "evidence": self.evidence}


@dataclass
class ReproPlan:
    paper_id: str
    arxiv_id: str
    inputs_sha: str = ""
    research_problem: str = ""
    domain: str = ""
    algorithm_family: str = ""
    methods: List[Dict[str, Any]] = field(default_factory=list)
    code: List[Dict[str, Any]] = field(default_factory=list)
    data: List[Dict[str, Any]] = field(default_factory=list)
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    sota_baselines: Dict[str, Any] = field(default_factory=dict)
    chains: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class RunState:
    """RUNSTATE 是 events 的派生快照（SciForge 风格）。"""
    run_id: str
    paper_id: str
    phase: str = "R0"
    status: str = "pending"
    next_action: str = "R0"
    verdicts: Dict[str, str] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return dict(self.__dict__)
