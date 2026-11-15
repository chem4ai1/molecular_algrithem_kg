"""语义层 v4.1 抽取契约：prompt 输出结构 1:1 对应语义层字段。

设计原则：
  1. 输出里出现的每个字段，必须能在 semantic.tbox_v4.SEMANTIC_CLASSES 里找到；
  2. 语义层不存在的东西（Observation/Section/Hypothesis/DataContract 等）不抽；
  3. 能由规则/AST/表格得到的不让 LLM 抽（domain、flow_family、code_symbols 对齐、
     keywords、repo_url、func_type、model_results 主路径）；
  4. 辅助字段失败归一为空，不阻断核心字段（沿用 paper_core 的教训）。
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

from ..tbox_v4 import SEMANTIC_CLASSES, field_names

# 封闭词表（复用现有权威定义）
FORM_VOCAB = ("SMILES", "3D坐标", "向量", "图", "序列", "分布", "标量", "文本")
DOMAIN_CODES = tuple(f"D{i}" for i in range(11))


def _task_types() -> Tuple[str, ...]:
    try:
        from ...sciforge.algorithm_problem import TASK_TYPES
        return tuple(TASK_TYPES)
    except Exception:  # noqa: BLE001
        return ()


def _families() -> Tuple[str, ...]:
    try:
        from ...sciforge.algorithm_schema import FAMILY_IDS
        return tuple(FAMILY_IDS)
    except Exception:  # noqa: BLE001
        return ()


# 每个 LLM 阶段的输出契约：(必填字段, 可选字段, 说明)
E_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "E1_paper": {
        "target": "Paper",
        "required": ("research_question", "problem_category", "why_hard"),
        "optional": ("relation_hints", "evidence"),
        "fields": ("research_question", "problem_category", "domain_code",
                   "why_hard", "relation_hints", "evidence"),
        "note": "domain/domain_code 由 papers.csv 校准；flow_family 由关系反查，不抽",
    },
    "E2_algorithm": {
        "target": "Algorithm + AlgorithmModule",
        "required": ("name", "mechanism"),
        "optional": ("task_type", "problems_solved", "why_it_works",
                     "applicable_to", "limitations", "modules"),
        "fields": ("name", "task_type", "problems_solved", "mechanism",
                   "why_it_works", "applicable_to", "limitations",
                   "modules"),
        "note": "modules[] 是 AlgorithmModule；code_symbols 只能从 AST 清单选",
    },
    "E3_benchmark": {
        "target": "Benchmark 结构",
        "required": ("name", "input_form", "output_form"),
        "optional": ("n_samples", "scale", "modality", "research_object",
                     "metrics"),
        "fields": ("name", "input_form", "output_form", "n_samples",
                   "scale", "modality", "research_object", "metrics"),
        "note": "禁止输出观测值；数值走 E4",
    },
    "E4_values": {
        "target": "Benchmark.model_results[]",
        "required": ("model", "metric", "value"),
        "optional": ("unit", "benchmark", "source", "evidence"),
        "fields": ("model", "metric", "value", "unit", "benchmark",
                   "source", "evidence"),
        "note": "表格解析为主路径，LLM 只兜底表格外显式数值",
    },
    "E6_lineage": {
        "target": "Algorithm-SUBCLASS_OF->Algorithm（算法-算法改进链）",
        "required": ("from", "to", "kind"),
        "optional": ("evidence",),
        "fields": ("from", "to", "kind", "evidence"),
        "note": "只有 extends/replaces/improves 建边；compared_with 是对比基线，不建",
    },
    "E5_relations": {
        "target": "Module→Tool / Module→Formula（仅这两类允许 LLM）",
        "required": ("module", "kind", "target"),
        "optional": ("evidence",),
        "fields": ("module", "kind", "target", "evidence"),
        "note": "其余关系一律由规则/AST 建；科技树链只在应用层任务时抽",
    },
}

# 由非 LLM 手段填充的字段（防止重复抽）
NON_LLM: Dict[str, Tuple[str, ...]] = {
    "Paper": ("title", "arxiv_id", "doi", "year", "venue", "domain",
              "flow_family", "keywords"),
    "Algorithm": ("flow_family",),
    "AlgorithmModule": (),
    "CodeRepository": ("repo_name", "repo_url", "local_path", "license",
                       "is_original_repo"),
    "CodeFunction": ("name", "purpose", "comment", "params", "returns",
                     "func_type"),
    "Benchmark": ("model_results", "sota_by_metric", "is_evaluation"),
}


STAGE_CLASSES: Dict[str, Tuple[str, ...]] = {
    "E1_paper": ("Paper",),
    "E2_algorithm": ("Algorithm", "AlgorithmModule"),
    "E3_benchmark": ("Benchmark",),
    "E4_values": ("Benchmark",),
    "E5_relations": ("AlgorithmModule",),
    "E6_lineage": ("Algorithm",),
}

STAGE_NOTE: Dict[str, str] = {
    "E1_paper": "research_question 与 problem_category 是 Paper 的字符串属性，不建节点。",
    "E2_algorithm": "code_symbols 只能从【代码符号清单】选；flow_family 由规则判定。",
    "E3_benchmark": "禁止输出任何数值；数值走下一阶段。",
    "E4_values": "数值写 Benchmark.model_results[]，不建 Observation 节点。",
    "E5_relations": "只能输出 tool / formula 两类关系，不输出科技树。",
    "E6_lineage": "只依据明确的谱系措辞；compared_with 是对比基线不建边。",
}


def contract_text(stage: str | None = None) -> str:
    """注入 prompt 的「语义层契约」，替代旧 stage_extract 的矛盾契约块。"""
    # 按阶段裁剪：只列本阶段目标类的 LLM 字段。
    # 不再输出「某类不由 LLM 抽」——模型本来就拿不到这些输出位，说它是纯噪声。
    classes = STAGE_CLASSES.get(stage, tuple(SEMANTIC_CLASSES)) \
        if stage else tuple(SEMANTIC_CLASSES)
    lines = ["【语义层契约 · 只抽下面这些字段，其余一律不要输出】"]
    for cls in classes:
        definition, fields = SEMANTIC_CLASSES[cls]
        llm_fields = [f for f, _lv, _n in fields
                      if f not in NON_LLM.get(cls, ())]
        if llm_fields:
            lines.append("- " + cls + ": " + ", ".join(llm_fields))
        elif not stage:
            # 全量契约（不进 prompt）保留类别清单，供文档与 stage_extract 转发
            lines.append("- " + cls + ": （规则/AST 填充，不输出）")
    if stage:
        lines.append(STAGE_NOTE.get(stage, ""))
    else:
        lines.append("词表以【动态词表】块为准：超出词表时输出 other 并给 "
                     "proposed_new，系统会自动扩充词表。")
    return "\n".join(x for x in lines if x)


def llm_fields_of(cls: str) -> Tuple[str, ...]:
    return tuple(f for f, _lv, _n in SEMANTIC_CLASSES[cls][1]
                 if f not in NON_LLM.get(cls, ()))
