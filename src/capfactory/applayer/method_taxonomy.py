"""面向算法设计的方法流派分类法（method family taxonomy）。

不是按「问题类型」（generation/optimization）分，而是按「用什么机制解决问题」分——
这样才能回答「我该借鉴哪个流派」「跨流派怎么组合」。

参考：
- arXiv:2505.16094 (LLM-centric molecular discovery taxonomy: frozen vs fine-tuned, agentic)
- 52 篇实际论文内容（SynCraft/MECo=编辑序列, SynFlowNet/RGFN/S3-GFN=GFlowNet,
  AgentDrug/MultiMol/MT-MOL=LLM agent, DESP/RetroPlanner=搜索式逆合成 …）
"""
from __future__ import annotations
from typing import Dict, List, Tuple

# 流派定义：(id, 名称, 判别关键词, 对算法设计的意义)
METHOD_FAMILIES: Dict[str, Tuple[str, List[str], str]] = {
    "edit_sequence": ("编辑序列优化", [
        "edit sequence", "atom edit", "molecular editing", "coder as editor",
        "syncraft", "meco", "fragment editing", "graph edit"],
        "把分子看作可逐步修改的结构；适合局部可控优化，增量式设计"),
    "gflownet": ("GFlowNet / 生成流", [
        "gflownet", "generative flow", "flow network", "synflownet", "rgfn",
        "s3-gfn", "reward-conditioned"],
        "按奖励比例采样、天然多样性；适合多目标/可控生成"),
    "diffusion_flow": ("扩散 / 流模型", [
        "diffusion", "flow matching", "discrete flow", "rectified flow",
        "synbridge", "retrogef", "verso", "field-based", "field based",
        "e(3)-equivariant", "equivariant", "chirality"],
        "连续/离散状态演化；适合结构生成与逆合成的状态转移建模"),
    "llm_agent": ("LLM 多智能体 / 工具编排", [
        "multi-agent", "agentic", "llm agent", "tool-grounded", "collaborative expert",
        "agentdrug", "multimol", "mt-mol", "m3os", "tmcs", "maddie", "molevolve",
        "policy optimization", "grpo", "reinforcement learning from", "reasoning",
        "co-scientist", "multi-turn feedback", "dynamic action space",
        "reference-guided", "precedent-guided"],
        "用 LLM 做规划/推理/工具调用；适合自动化流程与跨模块协同"),
    "llm_frozen_incontext": ("LLM 冻结 / 上下文学习", [
        "in-context", "prompt", "frozen llm", "text-guided", "zero-shot", "few-shot"],
        "不改参数，靠提示工程；适合快速试错与低数据场景"),
    "llm_finetuned": ("LLM 微调 / 领域适配", [
        "fine-tun", "sft", "lora", "pretrain", "domain-adapt", "synllama", "stamp", "molecode"],
        "领域数据微调；适合结构化输出与领域语言理解"),
    "retro_search": ("搜索式逆合成", [
        "retrosynthesis", "retroplanning", "mcts", "monte carlo", "search", "askcos",
        "desp", "double-ended", "disconnection", "route expansion",
        "pathway refinement", "chemical space", "synthesizable chemical space",
        "navigating synthesizable"],
        "在反应图上搜索路径；适合可解释的合成路线设计"),
    "rule_symbolic": ("规则 / 符号系统", [
        "shacl", "datalog", "owl", "rule", "symbolic", "logic", "inference",
        "constraint validation", "completeness", "soundness"],
        "形式化约束与推理；适合正确性保证与知识图谱治理"),
    "property_surrogate": ("性质预测 / 代理模型", [
        "property prediction", "qed", "surrogate", "oracle", "classifier", "f1 score",
        "representation", "pretrain"],
        "学习结构-性质映射；适合作为优化目标的代理与筛选器"),
    "benchmark_eval": ("评测 / 验证框架", [
        "benchmark", "evaluation", "audit", "verification", "trace", "safety",
        "molsafeeval", "chemcotbench", "fev", "relation extraction",
        "enzyme chemistry", "dataset", "review of large language"],
        "定义可复算的判定标准；适合作为流程的门与反馈信号"),
}


def classify_by_text(text: str, *, top_k: int = 2) -> List[Tuple[str, float]]:
    """基于关键词的流派打分（确定性，作为 LLM 标注的先验）。"""
    t = (text or "").lower()
    scores = []
    for fid, (name, kws, _) in METHOD_FAMILIES.items():
        hits = sum(1 for k in kws if k in t)
        if hits:
            scores.append((fid, hits / max(len(kws) ** 0.5, 1)))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def family_desc(fid: str) -> str:
    return METHOD_FAMILIES.get(fid, ("未知", [], ""))[2]
