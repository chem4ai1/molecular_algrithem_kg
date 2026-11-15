"""V3 本体扩展：以 Algorithm / Benchmark 为第二类根的抽取型本体。

替换点（依据 docs/MANUAL_ALIGNMENT_MOLMINER.md 的人工对应）：
* C3 从「能力主张」改为**论文声明的假设/观点** → 新类 Hypothesis
* C8 从「因果图/grounding」改为**算法怎么被用于解决问题**
  → 问题→算法→应用→结果→回证假设；grounding 降级为 Algorithm 链的一环
* Algorithm 拆到「步骤 + 模块 + 公式 + 工具」→ 新类 Formula / Tool
* Benchmark 除评测值外必须有**数据特征契约** → 新类 DataContract
"""
from __future__ import annotations
from typing import Any, Dict, Tuple

from .model import ConceptV2, F

# ---- 4 个新类（每个至少 1 个 must_have）----
V3_CLASSES: Dict[str, ConceptV2] = {
    "Hypothesis": ConceptV2("Hypothesis", "problem",
        "论文声明的假设、观点或立场（不是能力宣称）", (
            F("statement", "extracted", "must_have"),
            F("kind", "extracted", "should_have"),
            F("polarity", "derived"), F("paper_id", "derived"),
            F("section_id", "derived"), F("quote", "extracted"))),
    "Formula": ConceptV2("Formula", "method",
        "算法步骤里的公式/方程（可与代码对齐的机制证据）", (
            F("latex", "extracted", "must_have"),
            F("equation_no", "extracted"), F("variables", "extracted"),
            F("section_id", "derived"), F("quote", "extracted"))),
    "Tool": ConceptV2("Tool", "method",
        "算法步骤用的工具、库、力场或求解器", (
            F("name", "extracted", "must_have"),
            F("kind", "extracted", "should_have"),
            F("version", "extracted"), F("role", "extracted"))),
    "SourcePaper": ConceptV2("SourcePaper", "literature",
        "算法或基准的出处论文节点；库内命中可 RESOLVED_TO，未命中待扩充", (
            F("root_type", "extracted", "must_have"),
            F("root_id", "extracted", "must_have"),
            F("source_kind", "extracted", "must_have"),
            F("tree_relation", "derived"), F("evidence", "extracted"),
            F("ref_no", "extracted", "must_have"),
            F("needs_expansion", "derived"),
            F("resolved_paper_id", "derived"),
            F("match_kind", "derived"), F("match_score", "derived"))),
    "MetricObservation": ConceptV2("MetricObservation", "evaluation",
        "榜单观测（Observation 的别名子类；TBox 内按别名归一）", (
            F("value", "extracted", "must_have"),
            F("metric", "extracted", "should_have"),
            F("unit"), F("subject"), F("paper_id", "derived"),
        )),
    "DataContract": ConceptV2("DataContract", "evaluation",
        "基准的输入输出形式/对象、切分、采样预算、阈值、指标族与基线", (
            F("input_form", "extracted", "must_have"),
            F("output_form", "extracted", "should_have"),
            F("input_object", "extracted", "should_have"),
            F("output_object", "extracted", "should_have"),
            F("split_type", "extracted"), F("sample_budget", "extracted"),
            F("threshold", "extracted"), F("metric_family", "extracted"),
            F("baseline_methods", "extracted"),
            F("evaluation_tool", "derived"), F("leakage_risk", "derived"))),
}

# ---- 新关系（domain, range, 说明）----
V3_RELATIONS: Dict[str, Tuple[str, str, str]] = {
    "DECLARES_HYPOTHESIS": ("Paper", "Hypothesis", "论文声明假设/观点"),
    "TESTS_HYPOTHESIS": ("Benchmark", "Hypothesis", "该基准检验哪条假设"),
    "SUPPORTS_HYPOTHESIS": ("Observation", "Hypothesis", "结果回证假设"),
    "HAS_FORMULA": ("AlgorithmStep", "Formula", "步骤对应的公式"),
    "USES_TOOL": ("AlgorithmStep", "Tool", "步骤用的 RDKit/力场等工具"),
    "HAS_DATA_CONTRACT": ("Benchmark", "DataContract", "基准的数据特征契约"),
    "HAS_INPUT_FORM": ("Benchmark", "DataForm", "输入形式（向量/SMILES/3D…）"),
    "HAS_OUTPUT_FORM": ("Benchmark", "DataForm", "输出形式"),
    "HAS_INPUT_OBJECT": ("Benchmark", "ResearchObject", "输入对象（分子/口袋/性质向量…）"),
    "HAS_OUTPUT_OBJECT": ("Benchmark", "ResearchObject", "输出对象"),
    "EVALUATES_METHOD": ("Benchmark", "Algorithm", "基准评了哪些方法（含基线）"),
    "REPORTS_VALUE": ("Benchmark", "Observation", "基准上各方法的评测值"),
    "BINDS_EVAL_TOOL": ("Benchmark", "EvaluationTool", "基准用哪个评测脚本"),
    "ADDRESSED_BY": ("ResearchQuestion", "Algorithm", "问题由哪个算法解决"),
    "APPLIES_TO": ("MethodApplication", "ResearchQuestion", "算法这次具体用在哪"),
    "LEADS_TO": ("MethodApplication", "Observation", "应用产出的结果"),
    "REALIZED_BY": ("AlgorithmStep", "CodeFunction", "步骤由哪个函数实现"),
    "HAS_MODULE_IMPL": ("AlgorithmStep", "CodeModule", "步骤落在哪个代码模块"),
    # ---- 出处层：只做「相关论文/算法/benchmark」三类，不为全部参考文献建条目 ----
    "SOURCED_FROM": ("Paper|Algorithm|Benchmark", "SourcePaper",
                     "三类根对象各自的出处论文"),
    "RESOLVED_TO": ("SourcePaper", "Paper", "出处论文已在当前图/库中"),
    "SITUATED_IN": ("Paper", "SourcePaper", "相关论文标出本文在科技树中的位置"),
    "IMPROVED_BY": ("SourcePaper", "SourcePaper", "同维度改进链"),
    "REPLACED_BY": ("SourcePaper", "SourcePaper", "换机制的替代链"),
    "REPLACES": ("SourcePaper", "SourcePaper", "换机制的替代链（样式2用词）"),
    "BELONGS_TO": ("SourcePaper", "SourcePaper", "方法家族归类链"),
    "COMPARES_WITH": ("SourcePaper", "SourcePaper", "对比链"),
    "HAS_LIMITATION": ("SourcePaper", "Limitation", "科技树瓶颈：局限短语"),
    "ON_METRIC": ("SourcePaper", "MetricDefinition", "对比链所用指标"),
    "DELTA": ("SourcePaper", "Observation", "数值提升量（数值挂边属性）"),
    "REFERS_TO": ("SourcePaper", "Paper", "出处对应的库内论文"),
    # ---- 精简第一档补齐：图里大量在用但此前未定义 ----
    "REPORTS": ("Paper", "Observation", "论文报告观测（表格数值）"),
    "OF_METRIC": ("Observation", "MetricDefinition", "观测所用指标"),
    "RELATED_TO": ("Paper", "Paper|Algorithm", "相关文献/方法（关系层主链）"),
}

# ---- 三类根族：触手就是「根节点换成 Algorithm / Benchmark」时的延伸 ----
ROOT_FAMILIES: Dict[str, Dict[str, Any]] = {
    "Paper": {"stage": 1, "label": "文献根",
              "chains": ["P1_structure", "P2_problem", "P3_hypothesis",
                         "P8_solution"],
              "tentacles": ["paper.hypothesis", "paper.solution_use"]},
    "Algorithm": {"stage": 2, "label": "算法-代码根",
                  "chains": ["A1_decompose", "A2_code_grounding", "A3_source_paper"],
                  "tentacles": ["algorithm.step_decomposition",
                                "algorithm.code_grounding",
                                "algorithm.source_paper"]},
    "Benchmark": {"stage": 3, "label": "基准根",
                  "chains": ["B1_values", "B2_data_profile", "B3_source_paper"],
                  "tentacles": ["benchmark.evaluation_values",
                                "benchmark.data_profile",
                                "benchmark.source_paper"]},
}
