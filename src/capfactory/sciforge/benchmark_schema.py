"""基准族 Schema 注册表（与 algorithm_schema.py 对称）。

调研依据：
 1. 项目内 21 个非 canonical Benchmark 节点属性覆盖率极低
    （task_family 1/21、metrics 0/21、baselines 0/21）；
 2. PG `kg.result` 已有 280 行 / 20 基准 / 43 指标 / 50 模型，但没挂到节点上；
 3. 分子/蛋白/多肽领域常见基准的知识结构。

每族 = 公共字段 + 专属字段；`metrics` 与 `model_results` 是**必填列表**，
每个基准都要有（无数据时为空列表并显式说明）。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

E = lambda *v: {"type": "enum", "enum": list(v)}  # noqa: E731
S = lambda h="": {"type": "str", "hint": h}       # noqa: E731
L = lambda h="": {"type": "list", "hint": h}      # noqa: E731

COMMON = {
    "name": S("基准/数据集名称"),
    "aliases": L("别名列表"),
    "task_family": E("分子生成", "性质/能量预测", "结构/对接",
                     "多肽/序列设计", "指令/数据集", "反应/合成"),
    "research_object": E("小分子", "蛋白/口袋", "抗体", "多肽",
                         "材料/力场", "反应/合成"),
    "modality": E("3D 结构/坐标", "2D 图", "1D 序列/SMILES",
                  "文本/指令", "性质向量/表格"),
    "input_form": S("输入形式"),
    "output_form": S("输出形式"),
    "n_samples": S("样本规模（数字或 unknown）"),
    "scale": E("小规模 (<1k)", "中规模 (1k–100k)", "大规模 (>100k)",
               "规模未标注"),
    "split_type": S("切分方式"),
    "split_ratio": S("训练/验证/测试比例"),
    "threshold": S("判定阈值"),
    "metrics": L("本基准的测试指标列表（必填，可为空）"),
    "baselines": L("参与对比的模型/基线列表（必填，可为空）"),
    "model_results": L("各模型的测试结果列表（必填，可为空）"),
    "evaluation_tool": S("评测工具"),
    "leakage_risk": S("数据泄漏风险"),
    "provenance": S("数据来源"),
    "evidence": S("判定依据（原文逐字短句）"),
}

FAMILIES: Dict[str, Dict[str, Any]] = {
    "molecule_generation": {
        "label": "分子生成基准", "code": "D1",
        "aliases": ["zinc", "moses", "guacamol", "chembl", "geom",
                    "generated molecules", "unconditional generation",
                    "conditional generation", "glcmal"],
        "description": "评估生成分子的分布质量与性质达标能力",
        "fields": {
            "n_molecules": S("分子数"),
            "generation_budget": S("采样预算，如 5000/10000"),
            "validity_checker": E("RDKit", "largest-component", "无", "unknown"),
            "scaffold_split": E("是", "否", "unknown"),
            "metric_family": L("如 validity/uniqueness/novelty/diversity/FCD"),
            "reference_set": S("参考分布来源"),
            "conditional": E("无条件", "属性条件", "口袋条件", "unknown"),
        }},
    "property_prediction": {
        "label": "分子性质/ADMET 基准", "code": "D2/D4",
        "aliases": ["qm9", "esol", "freesolv", "lipophilicity", "bbbp",
                    "hiv", "tox21", "clintox", "sider", "admet", "tdc",
                    "logp", "pka", "solubility", "toxicity"],
        "description": "监督式分子性质回归/分类",
        "fields": {
            "target_properties": L("预测目标性质列表"),
            "task_type": E("回归", "分类", "多任务分类", "unknown"),
            "split_type": E("scaffold split", "random split", "时间切分",
                            "unknown"),
            "label_source": S("标签来源"),
            "metric_family": L("如 MAE/RMSE/AUC/ROC-AUC"),
            "n_tasks": S("任务数"),
        }},
    "quantum_energy": {
        "label": "量子化学/力场基准", "code": "D10",
        "aliases": ["sapt", "quid", "jsch", "pla15", "crambin",
                    "s22", "ani-", "water", "force field", "energy",
                    "conformer", "pentapeptide"],
        "description": "以高精度量子化学/实验为参考评估能量与力",
        "fields": {
            "n_systems": S("体系数"),
            "n_conformers": S("构象数"),
            "reference_method": E("CCSD(T)", "DFT", "SAPT", "实验测定",
                                  "半经验", "unknown"),
            "energy_unit": E("kcal/mol", "eV", "Hartree", "kJ/mol", "unknown"),
            "force_labels": E("有", "无", "unknown"),
            "basis_set": S("基组"),
            "metric_family": L("如 MAE/RMSE/能量误差/RMSD"),
        }},
    "structure_docking": {
        "label": "结构/对接基准", "code": "D6",
        "aliases": ["dud-e", "dud_e", "pdbbind", "casf", "crossdocked",
                    "torsionnet", "cdrh3", "pocket", "docking",
                    "antibody", "target"],
        "description": "以蛋白口袋/复合物结构评估生成与打分",
        "fields": {
            "n_targets": S("靶点数"),
            "n_complexes": S("复合物数"),
            "pocket_definition": S("口袋定义方式"),
            "rmsd_threshold": S("RMSD 成功阈值（Å）"),
            "docking_tool": E("AutoDock Vina", "Glide", "gnina", "无",
                              "unknown"),
            "decoy_ratio": S("诱饵/活性比例"),
            "metric_family": L("如 QED/diversity/rmsd/命中率"),
        }},
    "peptide_sequence": {
        "label": "多肽/序列设计基准", "code": "D5",
        "aliases": ["amp", "peptide", "uniprot", "dbaasp", "camp",
                    "macrel", "scanner", "sequence database", "mic"],
        "description": "抗菌肽/蛋白序列的生成与活性评估",
        "fields": {
            "n_sequences": S("序列数"),
            "length_range": S("序列长度范围"),
            "activity_label": E("AMP 活性", "MIC 实测", "无标签", "unknown"),
            "predictor_ensemble": L("用于筛选的预测器列表"),
            "negative_set": S("负样本来源"),
            "mic_measurement": S("MIC 测定方式/单位"),
            "metric_family": L("如 validity/uniqueness/novelty/命中率/MIC"),
        }},
    "instruction_dataset": {
        "label": "指令/多模态数据集", "code": "D8",
        "aliases": ["instruction", "mol-instructions", "chebi",
                    "caption", "text", "prompt", "corpus"],
        "description": "以自然语言指令驱动分子/蛋白任务",
        "fields": {
            "n_tasks": S("任务数"),
            "n_instructions": S("指令条数"),
            "modalities": L("模态列表"),
            "source_db": S("底层数据来源"),
            "evaluation_tasks": L("评测任务列表"),
            "metric_family": L("如 BLEU/ROUGE/Exact Match/validity"),
        }},
    "reaction_synthesis": {
        "label": "反应/合成基准", "code": "D3",
        "aliases": ["uspto", "pistachio", "reaction", "retrosynthesis",
                    "synthesis", "reactant"],
        "description": "反应预测与逆合成评估",
        "fields": {
            "n_reactions": S("反应数"),
            "reaction_type": E("正向反应预测", "逆合成", "产率预测", "unknown"),
            "atom_mapping": E("有", "无", "unknown"),
            "split_type": E("random split", "时间切分", "模板切分", "unknown"),
            "metric_family": L("如 top-k accuracy/round-trip accuracy"),
        }},
}

FAMILY_IDS = list(FAMILIES)
LABEL_TO_ID = {v["label"]: k for k, v in FAMILIES.items()}
PRIORITY = {
    "peptide_sequence": 95, "instruction_dataset": 92,
    "reaction_synthesis": 90, "structure_docking": 85,
    "quantum_energy": 80, "property_prediction": 75,
    "molecule_generation": 60,
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


def classify_rule(name: str, context: str = "") -> Optional[str]:
    """确定性族判定：只用名称，context 会污染（仅给 LLM 用）。"""
    blob = name.lower()
    best, score = None, -1.0
    for fid, f in FAMILIES.items():
        hits = sum(1 for a in f["aliases"] if a in blob)
        if not hits:
            continue
        sc = hits + PRIORITY.get(fid, 0) / 100
        if sc > score:
            best, score = fid, sc
    return best
