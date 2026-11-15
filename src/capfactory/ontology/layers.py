"""跨层关系、算法组合与代码层（V2 扩展）。

回答三个问题：

1. **不同层之间怎么连**：四层（文献/问题/方法/评测）+ 代码层，关系分「层内/跨层/横切」，
   枢纽是 ``MethodApplication``——「某算法作用于什么数据、产出什么、被什么指标评分」；
2. **一篇论文多个算法怎么建模**：``AlgorithmComposition`` + ``AlgorithmStep``，
   用 ``role`` 区分主干/编码器/采样器/基线，用 ``FLOWS_TO`` 描述组合拓扑；
3. **代码层**：基于 ``ref/code-anlysis.pdf``（Causal Algorithm Design）的
   七类因果本体 / 训练-推理双图 / micro-meso-macro 三级 / paper↔code grounding，
   并复用 ``capfactory.algograph.schema`` 已有的 13 类源码结构节点。

设计原则：所有「多元对应关系」都用一个**枢纽节点**承载，而不是往边上塞属性。
边属性无法被图查询、无法被校验、也无法被第二个算法共享。
"""

from __future__ import annotations

from typing import Dict, Tuple

from .model import ConceptV2, F

# ---------------------------------------------------------------------------
# 词表：算法在组合里的角色、数据形式、因果节点类型
# ---------------------------------------------------------------------------
ALGORITHM_ROLES = (
    "backbone", "encoder", "decoder", "generator", "sampler", "optimizer",
    "scorer", "filter", "loss", "preprocessing", "postprocessing",
    "evaluator", "baseline", "retriever", "tool", "surrogate", "oracle",
)
DATA_FORMS = (
    "1d_sequence", "2d_graph", "3d_structure", "3d_coordinates", "text",
    "image", "table", "scalar", "distribution", "embedding", "smiles",
    "pocket", "conformer", "latent", "mixed",
)
# CAD §3.2 七类因果本体（与 algograph.schema.CAUSAL_TYPES 同源）
CAUSAL_TYPES = ("input", "parameter", "mechanism", "state",
                "aggregation", "decision", "output")
PHASES = ("training", "inference", "init", "operational")
ABSTRACTIONS = ("micro", "meso", "macro")
CAD_LEVEL_BUDGET = {"micro": (12, 25), "meso": (7, 10), "macro": (4, 7)}
GAP_TYPES = ("none", "conceptual", "implementation")
# 模块级机制：论文里的「做了什么」，与代码函数名解耦
MECHANISMS = (
    "message_compute", "coordinate_update", "feature_update", "aggregation",
    "edge_inference", "normalization", "attention", "readout", "pooling",
    "encoding", "decoding", "sampling", "loss", "scoring", "filtering",
    "initialization", "other",
)
GROUNDING_STATUS = ("matched", "partial", "conceptual_gap",
                    "implementation_gap", "unresolved")
AGREEMENT = ("high", "partial", "low")


# ---------------------------------------------------------------------------
# 新增概念（8 类）
# ---------------------------------------------------------------------------
LAYER_CLASSES: Dict[str, ConceptV2] = {c.name: c for c in (

    ConceptV2("DataForm", "crosscut",
              "算法一步的输入/输出数据形式（模态 + 结构 + 形状），不是数据集本身", (
        F("form", "extracted", "must_have"),      # DATA_FORMS
        F("schema", "extracted", "should_have"),  # 字段/张量形状/单位
        F("shape"), F("unit"), F("source_section", "derived"),
    )),

    ConceptV2("MethodApplication", "method",
              "某个算法在某一阶段的一次具体应用：吃 X、产 Y、被 M 评分", (
        F("algorithm_id", "derived", "must_have"),
        F("phase", "extracted", "should_have"),   # PHASES
        F("input_form_id", "derived"), F("output_form_id", "derived"),
        F("metric_ids", "derived"), F("benchmark_ids", "derived"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
    )),

    ConceptV2("AlgorithmComposition", "method",
              "一篇论文的方法栈：多个算法按角色与顺序组合", (
        F("name", "extracted", "must_have"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
        F("n_steps", "derived"), F("algo_codes", "derived"),
        F("step_ids", "derived"),
    )),

    ConceptV2("AlgorithmStep", "method",
              "★ 模块节点：方法栈里的一个具体模块/组件，不是算法名。\n"
              "论文侧按机制与输入输出建，代码侧按函数/类建，两者靠 grounding 对齐", (
        F("module_name", "extracted", "must_have"),   # 论文里的叫法（EGCL / φ_e）
        F("mechanism", "extracted", "should_have"),   # MECHANISMS
        F("causal_role", "extracted", "should_have"), # CAD 七类
        F("inputs", "extracted", "should_have"),      # 张量/字段，不是 DataForm id
        F("outputs", "extracted", "should_have"),
        F("parameters", "extracted"),                 # 可学习参数 / 子网络
        F("equation_ref", "extracted"),               # Eq.3 / Alg.1 line 4
        F("order", "extracted", "should_have"),
        F("role", "extracted"),                       # ALGORITHM_ROLES
        F("phase"),
        # 精简：原 must_have 但 31/31 全空；实际用 paper_id 关联，降级
        F("algorithm_id", "derived", "optional"),
        F("paper_id", "derived", "should_have"),
        F("input_form_id", "derived"), F("output_form_id", "derived"),
        F("is_baseline", "derived"),
        F("code_symbols", "derived"),                 # grounding 回填的代码符号
        F("grounding_status", "derived", "should_have"),
        F("composition_id", "inherited", "should_have",
          "AlgorithmComposition.id"),
    )),

    ConceptV2("CodeModule", "code", "代码文件/模块（AST 解析产出）", (
        F("path", "derived", "must_have"),
        F("repository_id", "inherited", "should_have", "CodeRepository.id"),
        F("n_functions", "derived"), F("language", "derived"),
        F("top_symbols", "derived"),
    )),

    ConceptV2("CodeFunction", "code",
              "代码里的函数/类：带签名与因果角色，用于与论文模块对齐", (
        F("name", "derived", "must_have"),
        F("signature", "derived", "should_have"),
        F("owner_class", "derived"),
        F("causal_role", "derived", "should_have"),   # 由 mechanism/签名推断
        F("docstring", "derived"), F("lineno", "derived"),
        F("module_path", "inherited", "should_have", "CodeModule.path"),
        F("matched_step_ids", "derived"),             # grounding 结果
    )),

    ConceptV2("CausalGraph", "code",
              "CAD 因果图：一个算法在某一 phase、某一抽象层级的一张图", (
        F("algorithm_id", "derived", "must_have"),
        F("phase", "extracted", "should_have"),       # PHASES
        F("abstraction", "extracted", "should_have"), # ABSTRACTIONS
        F("source", "extracted", "should_have"),      # paper | code
        F("n_nodes", "derived"), F("mermaid", "extracted"),
    )),

    ConceptV2("CausalNode", "code",
              "CAD 七类因果节点（input/parameter/mechanism/state/aggregation/decision/output）", (
        F("causal_type", "extracted", "must_have"),
        F("label", "extracted", "must_have"),
        F("graph_id", "inherited", "should_have", "CausalGraph.id"),
        F("implementation_hint", "derived"),
    )),

    ConceptV2("EvaluationTool", "code",
              "仓库里真正计算指标的评测脚本 / 评测入口", (
        F("path", "derived", "must_have"),
        F("entry_point", "derived", "should_have"),
        F("metric_ids", "derived"), F("benchmark_ids", "derived"),
        F("repository_id", "inherited", "should_have", "CodeRepository.id"),
        F("produces", "derived"),
    )),

    ConceptV2("GroundingAlignment", "code",
              "CAD grounding：code 因果节点 ↔ paper 因果节点的对齐与缺口", (
        F("code_node_id", "derived", "must_have"),
        F("paper_node_id", "derived", "should_have"),
        F("agreement", "extracted", "should_have"),  # AGREEMENT
        F("paper_too_abstract", "extracted"),
        F("gap_type", "extracted", "should_have"),   # GAP_TYPES
        F("algorithm_id", "inherited", "should_have", "Algorithm.id"),
    )),
)}


# ---------------------------------------------------------------------------
# 关系：分「层内 / 跨层 / 代码层」
# ---------------------------------------------------------------------------
INTRA_LAYER: Dict[str, Tuple[str, str, str]] = {
    # L0
    "HAS_SECTION": ("Paper", "Section", "论文的小节，证据定位锚点"),
    "CORRECTED_BY": ("Paper", "Paper", "更正通知 / 版本关系"),
    # L1
    "BROADER": ("ResearchQuestion", "ProblemCategory", "具体问题归入 P01–P11"),
    "PARENT_OF": ("ResearchQuestion", "ResearchQuestion", "问题树层级"),
    # L2
    "HAS_STEP": ("AlgorithmComposition", "AlgorithmStep", "方法栈的一步"),
    "FLOWS_TO": ("AlgorithmStep", "AlgorithmStep", "步骤拓扑（A 的输出进 B）"),
    "USES_ALGO_FAMILY": ("Algorithm", "AlgorithmFamily", "算法族标签"),
    # L3
    "HAS_LEADERBOARD": ("Benchmark", "LeaderboardEntry", "基准下的成绩"),
    "FROM_OBSERVATION": ("LeaderboardEntry", "Observation", "成绩来自原子观测"),
    "PRODUCES_OBSERVATION": ("EvaluationRun", "Observation", "评测产生观测"),
}

CROSS_LAYER: Dict[str, Tuple[str, str, str]] = {
    "ADDRESSES": ("Paper", "ResearchQuestion", "论文要回答的问题"),
    "BENCHMARK_FOR": ("Benchmark", "ResearchQuestion", "基准对应的问题"),
    "PROPOSES_METHOD": ("Paper", "Algorithm", "论文提出的方法"),
    "HAS_COMPOSITION": ("Paper", "AlgorithmComposition", "论文的方法栈"),
    "ABOUT_METHOD": ("CapabilityClaim", "Algorithm", "主张针对的方法"),
    "SUPPORTED_BY": ("CapabilityClaim|Limitation|Observation|Benchmark|"
                     "Algorithm|AlgorithmStep|CodeFunction",
                     "Evidence|Section", "证据绑定"),
    "HAS_CODE": ("Paper", "CodeRepository", "论文的代码仓库"),
    "EVALUATED_ON": ("Paper|Algorithm|CodeRepository", "Benchmark", "谁在该基准上评测"),
    "USES_METRIC": ("Benchmark|EvaluationRun", "MetricDefinition", "基准用什么指标"),
    "REPORTED_BY": ("LeaderboardEntry", "Paper|CodeRepository", "成绩由谁报告"),
    "ABOUT_SUBJECT": ("Observation", "ResearchObject", "观测的研究对象"),
    "IN_DOMAIN": ("Paper|Algorithm|Benchmark", "Domain", "领域标签"),
}

# ★ 算法-数据-指标三元对应：以 MethodApplication 为枢纽
APPLICATION_LINKS: Dict[str, Tuple[str, str, str]] = {
    "PARTICIPATES_IN": ("Algorithm", "MethodApplication", "算法的一次应用"),
    "IN_COMPOSITION": ("MethodApplication", "AlgorithmComposition", "该应用属于哪个方法栈"),
    "CONSUMES": ("MethodApplication|AlgorithmStep", "DataForm", "输入数据形式"),
    "PRODUCES": ("MethodApplication|AlgorithmStep", "DataForm", "输出数据形式"),
    "SCORED_BY": ("MethodApplication", "MetricDefinition", "被哪个指标评分"),
    "APPLIED_ON": ("MethodApplication", "Benchmark", "在哪类基准上运行"),
    "HAS_INPUT_SCHEMA": ("Benchmark", "DataForm", "基准的输入契约"),
    "HAS_OUTPUT_SCHEMA": ("Benchmark", "DataForm", "基准的输出契约"),
}

# 代码层：CAD + algograph
CODE_LINKS: Dict[str, Tuple[str, str, str]] = {
    "CONTAINS_MODULE": ("CodeRepository", "CodeModule", "仓库包含模块/文件"),
    "DEFINES_FUNCTION": ("CodeModule", "CodeFunction", "模块定义函数"),
    "HAS_BLOCK": ("CodeFunction", "CodeBlock", "函数内的语法块"),
    "CALLS": ("CodeFunction", "CodeFunction", "调用关系"),
    "FLOWS_DATA_TO": ("CodeBlock", "CodeBlock", "数据流"),
    "REALIZES": ("CodeFunction|CodeModule", "AlgorithmStep", "代码函数实现了哪个**模块**"),
    "IMPLEMENTS_MODULE": ("CodeFunction", "AlgorithmStep", "模块级 grounding 命中"),
    "HAS_MODULE_DETAIL": ("Algorithm|Paper", "AlgorithmStep",
                          "整体方法由哪些模块构成（论文级装配也用它连步骤）"),
    "IMPLEMENTS_ALGORITHM": ("CodeRepository", "Algorithm", "仓库实现了哪个算法"),
    "HAS_CAUSAL_GRAPH": ("Algorithm|CodeRepository", "CausalGraph", "CAD 因果图"),
    "HAS_CAUSAL_NODE": ("CausalGraph", "CausalNode", "因果图节点"),
    "CAUSES": ("CausalNode", "CausalNode", "因果依赖（非共现）"),
    "GROUNDS_TO": ("CausalNode", "CausalNode", "code 节点 ↔ paper 节点对齐"),
    "ALIGNED_BY": ("GroundingAlignment", "CausalNode", "对齐涉及的节点"),
    "BINDS_TOOL": ("CodeRepository", "EvaluationTool", "仓库里的评测脚本"),
    "IMPLEMENTS_METRIC": ("EvaluationTool", "MetricDefinition", "脚本实现了哪个指标"),
    "RUNS_ON": ("EvaluationTool", "Benchmark", "脚本跑在哪个基准上"),
    "EMITS": ("EvaluationTool", "Observation", "脚本产出观测"),
}

# algograph 已有节点类型（不重复定义，只登记映射）
ALGOGRAPH_NODE_TYPES = (
    "module", "class_unit", "func_name", "implementation", "code_block",
    "external_symbol", "unresolved_site", "data_artifact", "causal_node",
    "paper_module", "test_case", "metric_binding", "capability_version",
)
ALGOGRAPH_MAP = {
    "CodeModule": "module",
    "CodeFunction": "func_name",
    "CodeBlock": "code_block",
    "CausalNode": "causal_node",
    "EvaluationTool": "metric_binding",
    "GroundingAlignment": "paper_module",
}


# ---------------------------------------------------------------------------
# 抽取协议：哪条关系从论文哪里来、靠什么信号、谁来填
# ---------------------------------------------------------------------------
EXTRACTION_PROTOCOL: Dict[str, Dict[str, str]] = {
    "HAS_SECTION": {"source": "derived", "where": "Markdown 标题",
                    "signal": "# / ## 层级", "note": "规则解析，不让 LLM 造 section id"},
    "ADDRESSES": {"source": "extracted", "where": "Abstract / Introduction",
                  "signal": "we ask / whether / aim to / our goal", "note": "转写成可检验问句"},
    "PROPOSES_METHOD": {"source": "extracted", "where": "Method",
                        "signal": "we propose / we introduce / our method",
                        "note": "只抽本文方法；基线标 baseline"},
    "HAS_COMPOSITION": {"source": "extracted", "where": "Method 前两段 + 流程图标题",
                        "signal": "pipeline / consists of / first…then…finally",
                        "note": "多方法论文必抽"},
    "IMPLEMENTS_MODULE": {"source": "extracted+derived",
                          "where": "论文 Method + 仓库 AST 结构",
                          "signal": "mechanism + inputs/outputs ↔ 函数签名",
                          "note": "模块级对齐，不靠名字字符串"},
    "HAS_STEP": {"source": "extracted", "where": "Method",
                 "signal": "顺序副词 / 模块名 / 箭头", "note": "给 role 与 order"},
    "FLOWS_TO": {"source": "extracted", "where": "Method + Figure caption",
                 "signal": "→ / then / fed into / passed to", "note": "步骤拓扑"},
    "CONSUMES": {"source": "extracted", "where": "Method 的输入段落",
                 "signal": "given / takes as input / conditioned on / input is",
                 "note": "抽 DataForm.form 与 schema，不是抽数据集名"},
    "PRODUCES": {"source": "extracted", "where": "Method / Results",
                 "signal": "outputs / generates / returns / yields",
                 "note": "抽 DataForm.form 与 schema"},
    "SCORED_BY": {"source": "extracted+derived", "where": "Experiments / Results",
                  "signal": "指标名 + 数值句", "note": "指标名过 MetricDefinition 词表，命中才建边"},
    "APPLIED_ON": {"source": "derived", "where": "Experiments",
                   "signal": "数据集/基准名", "note": "链到 Benchmark，不新建 Dataset"},
    "USES_METRIC": {"source": "derived", "where": "Benchmark 协议",
                    "signal": "EvaluationRun / Results", "note": "由 SCORED_BY 汇聚"},
    "HAS_CODE": {"source": "derived", "where": "Code Availability / repos.csv",
                 "signal": "github.com / zenodo", "note": "从清单回填，不让 LLM 猜 URL"},
    "REALIZES": {"source": "derived", "where": "代码 AST",
                 "signal": "函数名 ↔ 方法步名 / CAD grounding",
                 "note": "代码解析 + 对齐，不靠论文文本"},
    "HAS_CAUSAL_GRAPH": {"source": "extracted", "where": "PDF 全文 或 Python 源文件",
                         "signal": "CAD 三档 prompt",
                         "note": "同算法出 paper/code 两套 × training/inference × micro/meso/macro"},
    "GROUNDS_TO": {"source": "extracted", "where": "CAD grounding 表",
                   "signal": "code 推理图 ↔ paper 推理图节点匹配",
                   "note": "未匹配标 conceptual/implementation gap"},
    "IMPLEMENTS_METRIC": {"source": "derived", "where": "metrics.py / evaluate.py",
                          "signal": "函数名含 metric 名",
                          "note": "与 MetricDefinition 词表对齐"},
}


def relation_matrix() -> Dict[str, Dict[str, Tuple[str, str, str]]]:
    return {"intra_layer": INTRA_LAYER, "cross_layer": CROSS_LAYER,
            "application": APPLICATION_LINKS, "code": CODE_LINKS}


def summary() -> Dict[str, object]:
    return {
        "new_classes": len(LAYER_CLASSES),
        "relations": sum(len(x) for x in relation_matrix().values()),
        "by_group": {k: len(v) for k, v in relation_matrix().items()},
        "algorithm_roles": len(ALGORITHM_ROLES),
        "data_forms": len(DATA_FORMS),
        "causal_types": len(CAUSAL_TYPES),
        "extraction_rules": len(EXTRACTION_PROTOCOL),
        "algograph_reuse": len(ALGOGRAPH_MAP),
    }
