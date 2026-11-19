"""阶段 → 分类维度 → skill/协议/门控 的路由。

按 TAXONOMY_FOR_STAGES.md 的 6 个正交维度决定每阶段调什么。
"""
from __future__ import annotations
from typing import Any, Dict, List

# D1 方法流派 → skills / 工具链 / 门控
BY_METHOD_FAMILY: Dict[str, Dict[str, Any]] = {
    "edit_sequence": {"skills": ["method-registry", "leakage-audit"],
                      "tools": ["rdkit-edit", "syncraft-style"],
                      "gate": "edit_validity"},
    "gflownet": {"skills": ["experiment-ladder", "result-to-claim"],
                 "tools": ["gflownet-trainer"],
                 "gate": "sampling_coverage"},
    "diffusion_flow": {"skills": ["experiment-execution"],
                       "tools": ["flow-solver"], "gate": "reversibility"},
    "llm_agent": {"skills": ["invariant-check", "quality-gate"],
                  "tools": ["tool-registry"], "gate": "tool_call_success"},
    "retro_search": {"skills": ["ablation-planner", "logic-verification"],
                     "tools": ["retrosynthesis-engine"], "gate": "route_feasibility"},
    "rule_symbolic": {"skills": ["theory-derivation", "logic-verification"],
                      "tools": ["reasoner"], "gate": "soundness_completeness"},
    "llm_finetuned": {"skills": ["method-registry"], "tools": ["trainer"],
                      "gate": "finetune_reproducibility"},
    "benchmark_eval": {"skills": ["publishability-score", "quality-gate"],
                       "tools": ["eval-harness"], "gate": "benchmark_coverage"},
}

# D2 证据范式 → 保真度/必需实验/措辞上限
BY_EVIDENCE: Dict[str, Dict[str, Any]] = {
    "experimental": {"min_fidelity": "numerical",
                     "required": ["baseline", "multi_seed", "ablation"],
                     "max_claim": "proven",
                     "skills": ["result-to-claim", "leakage-audit"]},
    "simulational": {"min_fidelity": "numerical",
                     "required": ["oracle_budget", "repeat"],
                     "max_claim": "supported",
                     "skills": ["experiment-ladder"]},
    "derivational": {"min_fidelity": "symbolic",
                     "required": ["proof"],
                     "max_claim": "proven",
                     "skills": ["theory-derivation", "logic-verification"]},
    "interpretive": {"min_fidelity": "qualitative",
                     "required": ["case", "counterexample"],
                     "max_claim": "suggests",
                     "skills": ["adversarial-falsification", "kill-argument"]},
}

# D3 研究范式 → 主张结构
BY_PARADIGM: Dict[str, Dict[str, Any]] = {
    "formal": {"claim_form": "theorem", "falsify_by": "counterexample",
               "skills": ["theory-derivation"]},
    "empirical": {"claim_form": "numeric_hypothesis", "falsify_by": "significance",
                  "skills": ["result-to-claim"]},
    "design": {"claim_form": "system_effectiveness", "falsify_by": "ablation",
               "skills": ["ablation-planner"]},
    "interpretive": {"claim_form": "perspective", "falsify_by": "strongest_opposition",
                     "skills": ["kill-argument"]},
}

# D5 venue → 章节/引用/图表/门槛
BY_VENUE: Dict[str, Dict[str, Any]] = {
    "ml_conference": {"sections": ["intro", "method", "exp", "ablation", "related"],
                      "citation": "author-year", "figure_budget": "strict",
                      "skills": ["paper-writing", "unified-plotting"]},
    "nature_family": {"sections": ["abstract", "main", "methods_back"],
                      "citation": "numeric", "figure_budget": "minimal",
                      "skills": ["paper-writing", "publishability-score"]},
    "domain_venue": {"sections": ["system", "evaluation", "case"],
                     "citation": "mixed", "figure_budget": "demo",
                     "skills": ["paper-writing", "auto-review-loop"]},
    "survey": {"sections": ["taxonomy", "comparison", "trends"],
               "citation": "author-year", "figure_budget": "table-heavy",
               "skills": ["citation-audit"]},
}


def venue_bucket(venue: str) -> str:
    v = (venue or "").lower()
    if any(k in v for k in ("neurips", "iclr", "icml", "acl", "cvpr")):
        return "ml_conference"
    if any(k in v for k in ("nature", "science", "cell")):
        return "nature_family"
    if any(k in v for k in ("survey", "review")):
        return "survey"
    return "domain_venue"


def route(phase: int, profile: Dict[str, Any]) -> Dict[str, Any]:
    """按阶段读取不同分类维度，返回 skills/tools/gate/协议。"""
    out: Dict[str, Any] = {"phase": phase, "skills": [], "gate": None}
    if phase in (2, 3, 5):
        r = BY_METHOD_FAMILY.get(profile.get("method_family") or "", {})
        out.update({"skills": list(r.get("skills", [])),
                    "tools": list(r.get("tools", [])),
                    "gate": r.get("gate")})
    if phase == 4:
        e = BY_EVIDENCE.get(profile.get("evidence_type") or "", {})
        p = BY_PARADIGM.get(profile.get("paradigm") or "", {})
        out["skills"] = list(dict.fromkeys(
            e.get("skills", []) + p.get("skills", [])))
        out["claim_contract"] = {"min_fidelity": e.get("min_fidelity"),
                                 "required": list(e.get("required", [])),
                                 "max_claim": e.get("max_claim"),
                                 "claim_form": p.get("claim_form"),
                                 "falsify_by": p.get("falsify_by")}
        out["gate"] = "claim_locked"
    if phase in (8, 9, 10):
        b = BY_VENUE.get(venue_bucket(profile.get("venue") or ""), {})
        out["skills"] = list(b.get("skills", []))
        out["writing_contract"] = {"sections": list(b.get("sections", [])),
                                   "citation": b.get("citation"),
                                   "figure_budget": b.get("figure_budget")}
        out["gate"] = "venue_compliance"
    out["skills"] = list(dict.fromkeys(out["skills"]))
    return out
