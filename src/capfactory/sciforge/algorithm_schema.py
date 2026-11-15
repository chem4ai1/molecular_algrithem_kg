"""算法族 Schema 注册表（P1）。

调研依据：
 1. 项目内 34 个算法节点 + `po/vocab.py` 的 A01–A18 词表；
 2. 旧 `facets_v7.ARCH_FAMILY` 只有 8 类，导致 OPLS4/GAFF/CFPS/Prompt/FT/
    Langevin Speculative Dynamics 等 8 个落「未分类」；
 3. 生成式分子/蛋白领域常见机制（自回归、VAE、扩散、流匹配、等变 GNN、
    片段生成、经典力场、RNN、指令微调、推测采样、分类器引导、进化、GAN、
    湿实验基线）。

每族 = 公共字段 + 族专属字段；字段带 type/enum/hint，
供 LLM 生成提示词、供规则层做封闭词表校验。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

COMMON = {
    "name": {"type": "str", "hint": "算法/模型名称"},
    "role": {"type": "enum", "enum": ["本论文方法", "基线", "评测工具"]},
    "object_kind": {"type": "enum",
                    "enum": ["小分子", "蛋白/口袋", "抗体", "多肽",
                             "材料/力场", "反应/合成"]},
    "task_kind": {"type": "enum",
                  "enum": ["生成/设计", "性质/能量预测", "结构/对接",
                           "优化/校准", "指令/LLM", "基准/数据集"]},
    "modality": {"type": "enum",
                 "enum": ["3D 结构/坐标", "2D 图", "1D 序列/SMILES",
                          "文本/指令", "性质向量/表格"]},
    "paper_ids": {"type": "list"},
    "evidence": {"type": "str", "hint": "判定依据（原文逐字短句）"},
}
E = lambda *v: {"type": "enum", "enum": list(v)}  # noqa: E731
S = lambda h="": {"type": "str", "hint": h}       # noqa: E731

FAMILIES: Dict[str, Dict[str, Any]] = {
    "autoregressive": {
        "label": "自回归/Transformer/LLM", "code": "A01",
        "aliases": ["transformer", "gpt", "llm", "decoder only", "bart",
                    "esm", "plm", "instruction", "gru", "rnn"],
        "description": "把分子/蛋白表示为 token 序列，自回归或 seq2seq 生成",
        "fields": {
            "representation": E("SMILES", "SELFIES", "氨基酸序列",
                                "3D 坐标", "图", "文本/指令"),
            "architecture_variant": E("decoder-only", "encoder-decoder",
                                      "bidirectional+autoregressive",
                                      "prefix-tuned", "GRU", "unknown"),
            "tokenizer": S("分词/词表方式"),
            "decoding": E("beam search", "top-k", "nucleus", "greedy",
                          "temperature sampling", "unknown"),
            "pretrain_objective": S("预训练目标，如 MLM/CLM/掩码重建"),
            "context_length": S("最大上下文长度或 unknown"),
            "param_scale": S("参数规模或 unknown"),
        }},
    "vae": {
        "label": "VAE/隐变量", "code": "A02",
        "aliases": ["vae", "variational autoencoder", "chemicalvae", "latent"],
        "description": "编码器→潜空间→解码器，KL 约束先验",
        "fields": {
            "encoder": S("编码器架构"), "decoder": S("解码器架构"),
            "latent_dim": S("潜空间维度"),
            "prior": E("标准正态", "高斯混合", "learned prior", "unknown"),
            "kl_weight": S("KL 项权重 β"),
            "representation": E("SMILES", "SELFIES", "图", "3D 坐标",
                                "junction tree"),
        }},
    "gan": {
        "label": "GAN/对抗", "code": "A03",
        "aliases": ["gan", "adversarial", "discriminator", "wgan"],
        "description": "生成器与判别器对抗训练",
        "fields": {
            "generator": S("生成器架构"), "discriminator": S("判别器架构"),
            "loss": E("WGAN", "hinge", "vanilla", "least-squares", "unknown"),
            "gradient_penalty": E("有", "无", "unknown"),
            "conditioning": S("条件信息"),
        }},
    "diffusion": {
        "label": "扩散/分数模型", "code": "A04",
        "aliases": ["diffusion", "ddpm", "score based", "targetdiff",
                    "denoising", "classifier guidance"],
        "description": "逐步加噪→学习分数/去噪→采样生成",
        "fields": {
            "noise_schedule": E("linear", "cosine", "VP", "VE", "unknown"),
            "diffusion_steps": S("扩散/采样步数"),
            "score_network": S("去噪/分数网络"),
            "sampler": E("DDPM", "DDIM", "ancestral", "SDE", "unknown"),
            "conditioning": E("classifier-free", "classifier guidance",
                              "无条件", "口袋条件", "unknown"),
            "discrete_or_continuous": E("连续坐标扩散", "离散图扩散",
                                        "混合", "unknown"),
        }},
    "flow": {
        "label": "流匹配/连续流", "code": "A05",
        "aliases": ["flow matching", "normalizing flow",
                    "optimal transport", "rectified flow"],
        "description": "学习连续向量场/ODE 从先验映射到目标分布",
        "fields": {
            "vector_field": S("向量场参数化"),
            "solver": E("ODE", "SDE", "Euler", "RK4", "unknown"),
            "time_steps": S("积分步数"),
            "coupling": E("最优传输", "独立耦合", "unknown"),
        }},
    "geometric_gnn": {
        "label": "GNN/几何等变", "code": "A09/A10/A16",
        "aliases": ["schnet", "mace", "aimnet", "uma", "mpnn", "egnn",
                    "so3", "se(3)", "equivariant",
                    "pocket2mol", "krates"],
        "description": "消息传递 + 几何等变性，用于能量/力/结构预测",
        "fields": {
            "message_passing": S("消息传递形式"),
            "equivariance_group": E("SE(3)", "E(n)", "SO(3)", "O(3)",
                                    "不变但不等变", "unknown"),
            "spherical_harmonic_order": S("球谐阶数 l 或 unknown"),
            "radial_basis": S("径向基"),
            "invariant_features": S("不变特征"),
            "prediction_target": E("能量", "力", "能量+力", "结构/坐标",
                                   "序列/残基", "结合亲和力", "unknown"),
        }},
    "fragment": {
        "label": "片段/结构化生成", "code": "A01/A11",
        "aliases": ["fragment", "junction tree", "brics", "motif",
                    "attachment", "molminer"],
        "description": "先把分子分解为片段，再自回归组装",
        "fields": {
            "fragment_vocab": S("片段词表来源与规模"),
            "decomposition_rule": E("BRICS", "junction tree", "环+键切分",
                                    "数据驱动子结构", "unknown"),
            "attachment_points": S("连接点表示方式"),
            "symmetry_handling": E("规范化映射", "顺序固定", "顺序无关",
                                   "无处理", "unknown"),
            "geometry_aware": E("是", "否", "unknown"),
        }},
    "classical_forcefield": {
        "label": "经典力场/经验势", "code": "A18",
        "aliases": ["opls", "gaff", "amber", "charmm",
                    "empirical potential", "mmff"],
        "description": "参数化解析势函数，非机器学习",
        "fields": {
            "potential_form": S("势函数形式"),
            "cutoff_radius": S("非键截断半径（Å）"),
            "parameterization": S("参数来源"),
            "long_range": E("PME", "cutoff", "Ewald", "无", "unknown"),
            "polarizable": E("是", "否", "unknown"),
        }},
    "rnn": {
        "label": "RNN/序列模型", "code": "A01",
        "aliases": ["rnn", "lstm", "gru", "huang et al"],
        "description": "循环网络逐 token 生成或回归",
        "fields": {
            "cell_type": E("LSTM", "GRU", "vanilla RNN", "unknown"),
            "hidden_dim": S("隐藏维度"),
            "bidirectional": E("是", "否", "unknown"),
            "decoding": E("beam search", "sampling", "greedy", "unknown"),
        }},
    "instruction_tuning": {
        "label": "指令微调/提示学习", "code": "A01/A14",
        "aliases": ["prompt", "fine-tuning", "condition token", "prefix",
                    "lora", "distillation"],
        "description": "在预训练 LM 上用提示/条件 token/微调适配任务",
        "fields": {
            "base_model": S("基座模型"),
            "tuning_method": E("全量微调", "prefix/prompt tuning", "LoRA",
                               "condition token", "蒸馏", "unknown"),
            "instruction_source": S("指令数据来源"),
            "conditioning": S("条件信号"),
        }},
    "speculative_sampling": {
        "label": "采样加速/推测解码", "code": "A05/A17",
        "aliases": ["speculative", "langevin", "draft", "acceleration",
                    "proposal"],
        "description": "用廉价提议 + 校验加速生成采样",
        "fields": {
            "draft_model": S("提议/草稿模型"),
            "verification": E("拒绝采样", "Metropolis-Hastings",
                              "精确校验", "unknown"),
            "proposal_kernel": S("提议核"),
            "speedup": S("相对基线的加速比"),
        }},
    "classifier_guidance": {
        "label": "分类器引导/条件生成", "code": "A04/A18",
        "aliases": ["cl ass", "classifier-based", "screening baseline",
                    "classifier guidance"],
        "description": "用判别/分类器筛选或引导生成结果",
        "fields": {
            "classifier": S("分类器类型"),
            "guidance_scale": S("引导强度"),
            "condition_type": E("属性标签", "活性标签", "口袋", "unknown"),
            "screening": S("筛选策略，如 TopK/阈值"),
        }},
    "evolutionary": {
        "label": "进化/遗传/树搜索", "code": "A11",
        "aliases": ["genetic", "evolution", "mcts", "tree search"],
        "description": "种群/搜索空间上做启发式优化",
        "fields": {
            "search_space": S("搜索空间"), "population": S("种群规模"),
            "fitness": S("适应度函数"), "mutation": S("变异/交叉算子"),
            "budget": S("评估预算"),
        }},
    "wetlab": {
        "label": "实验/非计算基线", "code": "—",
        "aliases": ["cfps", "cell-free", "wet lab", "实验合成"],
        "description": "湿实验或数据库筛选基线，不是可训练算法",
        "fields": {
            "wet_lab_method": S("实验方法"),
            "throughput": S("通量"), "measurement": S("测量指标"),
        }},
    "ml_potential": {
        "label": "机器学习势/神经力场", "code": "A10/A16",
        "aliases": ["ml potential", "neural potential", "machine learning force",
                    "mlff", "nequip", "mace", "schnet", "aimnet", "uma",
                    "so3lr", "ani-", "deepmd"],
        "description": "以神经网络拟合势能面，输出能量与原子力",
        "fields": {
            "equivariance_group": E("SE(3)", "E(n)", "SO(3)", "O(3)", "unknown"),
            "training_data": S("训练数据来源与规模"),
            "prediction_target": E("能量", "力", "能量+力", "unknown"),
            "long_range": E("显式长程项", "无", "unknown"),
            "reference_method": E("DFT", "CCSD(T)", "实验", "unknown"),
        }},
    "inverse_folding": {
        "label": "结构基逆折叠/序列设计", "code": "A10/A01",
        "aliases": ["inverse folding", "proteinmpnn", "abmpnn", "esm-if",
                    "antifold", "structure-based sequence"],
        "description": "给定骨架/结构，预测能折叠成该结构的氨基酸序列",
        "fields": {
            "backbone_input": S("骨架表示"),
            "decoding": E("自回归", "一次性预测", "unknown"),
            "numbering_scheme": S("编号体系，如 IMGT"),
            "conditioning": S("结构/几何条件"),
        }},
    "general_lm": {
        "label": "通用语言模型/基座", "code": "A01",
        "aliases": ["llama", "alpaca", "gpt4all", "base language model",
                    "foundation model", "plm"],
        "description": "通用预训练语言模型，作为下游微调的基座",
        "fields": {
            "param_scale": S("参数规模"),
            "pretrain_corpus": S("预训练语料"),
            "tuning_ready": E("是", "否", "unknown"),
            "architecture_variant": E("decoder-only", "encoder-decoder", "unknown"),
        }},
    "peptide_lm": {
        "label": "多肽/蛋白序列语言模型", "code": "A01",
        "aliases": ["amp-gpt", "amp-mic", "peptide language", "protein lm",
                    "amp-designer", "amp-distillation"],
        "description": "在氨基酸序列上预训练/微调的生成或回归模型",
        "fields": {
            "representation": E("氨基酸序列", "SMILES", "unknown"),
            "decoding": E("自回归", "beam search", "unknown"),
            "conditioning": E("属性标签", "prompt", "无", "unknown"),
            "head": E("生成", "回归", "分类", "unknown"),
        }},
}

FAMILY_IDS = list(FAMILIES)
LABEL_TO_ID = {v["label"]: k for k, v in FAMILIES.items()}
# 更具体的族优先于宽泛的 autoregressive/geometric_gnn
PRIORITY = {
    "wetlab": 100, "speculative_sampling": 95, "instruction_tuning": 90,
    "classical_forcefield": 88, "classifier_guidance": 85,
    "rnn": 80, "fragment": 75, "vae": 70, "diffusion": 70,
    "flow": 70, "gan": 70, "evolutionary": 70,
    "geometric_gnn": 50, "autoregressive": 30,
    "ml_potential": 96, "inverse_folding": 94,
    "peptide_lm": 93, "general_lm": 92,
}


def schema_for(family_id: str) -> Dict[str, Any]:
    f = FAMILIES.get(family_id)
    if not f:
        return {}
    return {"family_id": family_id, "label": f["label"], "code": f["code"],
            "description": f["description"], "common": COMMON,
            "fields": f["fields"],
            "all_fields": {**COMMON, **f["fields"]}}


def enum_values(family_id: str) -> Dict[str, list]:
    f = FAMILIES.get(family_id, {})
    return {k: v["enum"] for k, v in
            {**COMMON, **f.get("fields", {})}.items()
            if v.get("type") == "enum"}


def classify_rule(name: str, architecture: str = "",
                  context: str = "") -> Optional[str]:
    """确定性类别判定：别名命中数 + 特异性优先级。"""
    import re as _re
    blob = f"{name} {architecture} {context}".lower()
    if _re.search(r"\bclass\b", blob) and "classifier guidance" not in blob:
        return "classifier_guidance"
    best, score = None, -1.0
    for fid, f in FAMILIES.items():
        hits = sum(1 for a in f["aliases"] if a in blob)
        if not hits:
            continue
        sc = hits + PRIORITY.get(fid, 0) / 100
        if sc > score:
            best, score = fid, sc
    return best
