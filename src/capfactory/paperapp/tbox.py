"""SciForge 26 阶段 → 应用类/关系映射（静态声明）。

阶段顺序显式给出，禁止 sorted()（'4broad' 在 '2' 之前）。
本模块不写图，只提供声明与校验。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .config import STAGE_IDS

# v2：4 个核心应用类 + 6 个探索/人类介入类
PAPERAPP_CLASS_VOCAB = (
    "DomainProfile", "ResearchGap", "IdeaNode", "GateVerdict",
    "KnowledgeSignal", "SignalCluster", "MiningCoverage",
    "ExplorationFrontier", "ChoicePoint", "HumanDecision",
    "HumanHypothesis", "MethodAlternative", "HumanIntent", "HumanOverride",
)

PAPERAPP_RELATION_VOCAB = (
    "ANCHORS", "SUPPORTED_BY", "SUGGESTS", "CHOOSES", "REJECTS",
    "CONSTRAINS", "OVERRIDES", "APPROVES", "SUPERSEDES", "REINJECTS",
    "AGGREGATES_TO", "PROMOTED_TO", "DERIVED_FROM", "GENERATED_BY",
)

_GATES = {
    "0": "inv_g1", "1": "rep_plan_present", "1a": "hint_only",
    "1b": "learning_confidence", "4broad": "gap_gate",
    "2": "type_a+gap_anchor+mcts>=4", "2.5": "falsifiable",
    "2.5b": "eg_dimensions", "3": "novelty_converge",
    "4targeted": "collision_precheck", "5": "hash_lock",
    "6": "routing_decided", "6a": "sympy_steps", "6b": "toy_gate",
    "6c": "full_gate", "7": "type_i_iv", "8": "logic_zero_fatal",
    "9": "inv_g1_recheck", "10": "claim_fidelity", "11": "figure_budget",
    "12": "leakage_scrub", "13": "compile_clean", "14": "review_score",
    "15": "citation_audit", "15.5": "publishability", "16": "verdicts_complete",
}

_MODES = {"3": "MUST+HUMAN", "5": "MUST+HUMAN", "6b": "MUST+HUMAN",
          "14": "MUST+HUMAN"}
_OPTIONAL = {"1a"}


def stage_defs() -> List[Dict[str, Any]]:
    out = []
    for i, sid in enumerate(STAGE_IDS):
        out.append({
            "id": sid, "name": sid, "mode": _MODES.get(sid, "MUST"),
            "optional": sid in _OPTIONAL, "gate": _GATES[sid],
            "next": [STAGE_IDS[i + 1]] if i + 1 < len(STAGE_IDS) else [],
            "reads": [], "produces": [], "enabled": True,
        })
    return out


# 14 个 ChoicePoint（v2 §4.4）：gate / option / advisory
CHOICEPOINTS: Dict[str, Dict[str, Any]] = {
    "1b": {"mode": "option", "options": ["formal", "empirical", "interpretive", "design"], "default": "empirical"},
    "4broad": {"mode": "option", "options": ["method_family", "dataset", "year_slice"], "default": "method_family"},
    "2": {"mode": "option", "options": ["balanced", "theoretical", "computational", "empirical"], "default": "balanced"},
    "2.5": {"mode": "option", "options": ["domain_failure", "numeric_counterexample", "literature_counterexample"], "default": "domain_failure"},
    "3": {"mode": "gate", "options": ["survivor_1", "survivor_2", "survivor_3"], "default": None},
    "4targeted": {"mode": "advisory", "options": [], "default": None},
    "5": {"mode": "gate", "options": ["approve_registry", "revise_registry"], "default": None},
    "6": {"mode": "option", "options": ["experiment-first", "theory-only", "hybrid"], "default": "experiment-first"},
    "6b": {"mode": "gate", "options": ["pivot", "kill"], "default": None},
    "10": {"mode": "option", "options": ["symbolic", "numerical", "qualitative"], "default": "numerical"},
    "11": {"mode": "option", "options": ["schematic-led", "quantitative-grid"], "default": "schematic-led"},
    "12": {"mode": "option", "options": ["theory", "experiment", "computational", "survey", "hybrid"], "default": "experiment"},
    "14": {"mode": "gate", "options": ["kill_argument_holds", "reject_kill_argument"], "default": None},
    "15.5": {"mode": "option", "options": ["supplement", "accept"], "default": "accept"},
}

GATE_STAGES = tuple(k for k, v in CHOICEPOINTS.items() if v["mode"] == "gate")


def validate_phasegraph(defs=None) -> List[str]:
    """返回问题列表，[] 表示通过。"""
    defs = defs if defs is not None else stage_defs()
    problems: List[str] = []
    ids = [d["id"] for d in defs]
    if len(ids) != 26 or len(set(ids)) != 26:
        problems.append("stage_count_or_duplicate")
    if ids != list(STAGE_IDS):
        problems.append("stage_order_mismatch")
    for d in defs:
        for nxt in d.get("next", []):
            if nxt not in ids:
                problems.append(f"dangling_next:{d['id']}->{nxt}")
        if d["id"] not in _GATES:
            problems.append(f"missing_gate:{d['id']}")
    # 无环：next 只能指向后续阶段
    pos = {s: i for i, s in enumerate(ids)}
    for d in defs:
        for nxt in d.get("next", []):
            if nxt in pos and pos[nxt] <= pos[d["id"]]:
                problems.append(f"cycle:{d['id']}->{nxt}")
    return problems
