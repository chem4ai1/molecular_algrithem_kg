"""P0-P11 真实科研流程的路由（v2，替代抽象 12 阶段路由）。

每个阶段读不同的分类维度，返回：skills / 工具链 / 章节模板 / 门控。
"""
from __future__ import annotations
from typing import Any, Dict, List

# D7 数据模态（新增，P2 必需）
DATA_MODALITY = ("smiles", "graph", "3d", "sequence", "text", "table")

# P1：流派 → 模块模板 + why_not_other 必答项 + 架构图要素
ROUTE_TEMPLATE: Dict[str, Dict[str, Any]] = {
    "edit_sequence": {
        "modules": ["edit_generator", "edit_executor"],
        "why_not": "为什么不直接端到端生成 SMILES",
        "arch_elems": ["初始分子", "编辑动作", "执行器", "输出分子"],
        "key_challenge": "编辑动作的可执行性与可解释性"},
    "gflownet": {
        "modules": ["forward_policy", "backward_policy", "reward"],
        "why_not": "为什么不用 RL/VAE",
        "arch_elems": ["状态空间", "前向动作", "后向策略", "奖励"],
        "key_challenge": "后向路径生成与状态空间规模"},
    "llm_agent": {
        "modules": ["planner", "tool_executor", "memory"],
        "why_not": "为什么不端到端训练",
        "arch_elems": ["规划器", "工具集", "记忆", "反馈"],
        "key_challenge": "零样本可靠性与工具调用成功率"},
    "retro_search": {
        "modules": ["expansion_policy", "value_network", "route_ranker"],
        "why_not": "为什么不用单步模板匹配",
        "arch_elems": ["目标分子", "反应模板", "搜索树", "路线"],
        "key_challenge": "搜索空间与路线可合成性"},
    "rule_symbolic": {
        "modules": ["constraint_compiler", "inference_engine", "validator"],
        "why_not": "为什么不用端到端学习",
        "arch_elems": ["本体", "约束", "推理规则", "验证结果"],
        "key_challenge": "形式语义的完整性与推理效率"},
    "diffusion_flow": {
        "modules": ["encoder", "flow_solver", "decoder"],
        "why_not": "为什么不用自回归",
        "arch_elems": ["噪声/先验", "流场", "采样轨迹", "样本"],
        "key_challenge": "离散状态的流匹配与可逆性"},
}

# P2：模态 → 数据工具 + 去泄漏手段
MODALITY_TOOLS: Dict[str, Dict[str, Any]] = {
    "smiles": {"tools": ["rdkit", "rdchiral"], "dedup": "canonical SMILES + Tanimoto<0.6"},
    "graph": {"tools": ["rdkit", "torch-geometric"], "dedup": "graph hash + scaffold split"},
    "3d": {"tools": ["rdkit", "openbabel", "pymol"], "dedup": "conformer RMSD + scaffold split"},
    "sequence": {"tools": ["biopython"], "dedup": "sequence identity <30%"},
    "text": {"tools": ["spacy"], "dedup": "n-gram overlap"},
    "table": {"tools": ["pandas"], "dedup": "row hash"},
}

# P9：venue × 流派 → 章节模板（从 4 篇真实论文反推）
SECTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "ml_conference": {
        "edit_sequence": ["intro", "related", "method.problem_formulation",
                          "method.framework", "method.data", "method.training",
                          "method.benchmark", "exp.setup", "exp.main",
                          "exp.improvement", "exp.case_study", "conclusion"],
        "gflownet": ["intro", "background", "method.mdp", "method.challenges",
                     "method.scaling", "results.mdp_design", "results.sampler",
                     "results.baseline", "results.rediscovery", "conclusion"],
        "llm_agent": ["intro", "methodology", "evaluation",
                      "ablation.component", "ablation.hyperparam", "conclusion"],
    },
    "nature_family": {
        "_default": ["abstract", "results", "discussion", "methods",
                     "data_availability", "code_availability"],
    },
}

# P6：证据范式 → 指标集（从论文反推）
METRICS_BY_EVIDENCE: Dict[str, List[str]] = {
    "experimental": ["success_rate", "validity", "similarity", "constraint_satisfaction"],
    "simulational": ["sample_quality", "diversity", "oracle_budget", "rediscovery"],
    "derivational": ["soundness", "completeness", "time_complexity"],
    "interpretive": ["case_coverage", "consistency", "expert_agreement"],
}


def route_phase(phase: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """phase 取 'P0'..'P11'；profile 含 method_family/evidence_type/paradigm/venue/artifact_protocol/data_modality。"""
    fam = profile.get("method_family") or ""
    ev = profile.get("evidence_type") or ""
    ven = profile.get("venue") or ""
    mod = profile.get("data_modality") or "smiles"
    out: Dict[str, Any] = {"phase": phase}

    if phase == "P0":                       # 问题形式化
        # 是否有数学形式化取决于流派，不是范式（MECo 是 design 但有 Mo=F(Mi,T)）
        formal_fams = ("edit_sequence", "gflownet", "retro_search", "diffusion_flow")
        out.update({"skills": ["intake-triage"],
                    "form": "math_definition+limits" if fam in formal_fams
                            else "problem_statement+workflow",
                    "gate": "has_formal_def_and_limits" if fam in formal_fams
                            else "has_old_limits"})
    elif phase == "P1":                     # 技术路线与架构
        t = ROUTE_TEMPLATE.get(fam, {})
        out.update({"skills": ["method-registry"], "route_template": t,
                    "gate": "has_why_not_other"})
    elif phase == "P2":                     # 数据构造
        m = MODALITY_TOOLS.get(mod, MODALITY_TOOLS["smiles"])
        out.update({"skills": ["data-construction"], "tools": m["tools"],
                    "dedup": m["dedup"], "gate": "no_test_leakage"})
    elif phase == "P3":                     # 代码实现
        out.update({"skills": ["code-implementation"],
                    "modules": ROUTE_TEMPLATE.get(fam, {}).get("modules", []),
                    "gate": "smoke_test_pass"})
    elif phase == "P4":                     # 训练
        out.update({"skills": ["experiment-execution"],
                    "gate": "converged_or_usable"})
    elif phase == "P5":                     # baseline
        out.update({"skills": ["experiment-execution"],
                    "gate": "same_protocol_baseline"})
    elif phase == "P6":                     # 主实验
        out.update({"skills": ["result-to-claim"],
                    "metrics": METRICS_BY_EVIDENCE.get(ev, []),
                    "gate": "multi_seed_significance"})
    elif phase == "P7":                     # 消融与案例
        out.update({"skills": ["ablation-planner"],
                    "ablation_targets": ROUTE_TEMPLATE.get(fam, {}).get("modules", []),
                    "gate": "every_novel_component_ablated"})
    elif phase == "P8":                     # 图表
        out.update({"skills": ["unified-plotting"],
                    "figure_kinds": ["architecture", "main_result"]
                                    + (["case"] if fam != "gflownet" else []),
                    "gate": "every_figure_has_claim"})
    elif phase == "P9":                     # 写作
        tpl = SECTION_TEMPLATES.get("nature_family" if "nature" in ven.lower() else "ml_conference")
        out.update({"skills": ["paper-writing"],
                    "sections": tpl.get(fam) or tpl.get("_default"),
                    "gate": "claim_evidence_match"})
    elif phase == "P10":                    # 引用核验
        out.update({"skills": ["citation-audit"], "gate": "three_layer_citation"})
    elif phase == "P11":                    # 复现包
        tier = profile.get("artifact_protocol") or "minimal"
        out.update({"skills": ["quality-gate"],
                    "required": {"code+data": ["code", "data", "env", "script"],
                                 "code-only": ["code", "env"],
                                 "benchmark-only": ["data", "env"],
                                 "theory-only": ["proof"],
                                 "minimal": ["readme"]}.get(tier, ["readme"]),
                    "gate": "third_party_reproduces"})
    return out
