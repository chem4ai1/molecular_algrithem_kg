"""语义层 TBox v4：只保留「客观可抽取的事实」，砍掉派生/应用类。

分层依据（参考 semantica-main 的 ontology → reasoning/decisions 分层）：
    语义层 semantic   ：论文、算法、模块、代码、基准 —— 直接从原文/代码/AST 抽取
    应用层 application：问题、问题类别、局限、榜单行、指标定义、出处论文、数据契约、证据
                      —— 从语义层挖掘派生，不直接抽

v4.1 再精简：删 Section（图内 0 节点、证据靠字段溯源）与 Observation
（81 个里有 73 个与 Benchmark.model_results 完全重复，数值统一由该属性承载）。

v4 与 v3.2(46 类/105 关系) 的变化：
  改名  AlgorithmStep → AlgorithmModule
  删类  DataContract / Evidence / LeaderboardEntry / Limitation /
        MetricDefinition / SourcePaper / ResearchQuestion / ProblemCategory
        Section（v4.1，图内 0 节点）/ Observation（v4.1，与 model_results 重复）
  降属性 ResearchQuestion→Paper.research_question；ProblemCategory→Paper.problem_category
        MetricDefinition→Benchmark.metrics[]；LeaderboardEntry→Benchmark.model_results[]
        DataContract→Benchmark 契约字段；Evidence→溯源字段
        Limitation/SourcePaper → 仅应用层
  属性精简 AlgorithmModule 只留 name/mechanism/formula/inputs/outputs
           CodeFunction 改为 purpose/comment/params/returns/func_type
"""
from __future__ import annotations
from typing import Any, Dict, Tuple

SEMANTIC_VERSION = "v4.1-semantic"

SEMANTIC_CLASSES: Dict[str, Tuple[str, Tuple[Tuple[str, str, str], ...]]] = {
    "Paper": ("论文（客观实体）", (
        ("title", "must", "标题"),
        ("arxiv_id", "should", "arXiv 标识"),
        ("doi", "optional", "DOI"),
        ("year", "optional", "年份"),
        ("venue", "optional", "发表场所"),
        ("research_question", "should", "研究什么问题（吸收 ResearchQuestion 节点）"),
        ("problem_category", "should", "问题类别（吸收 ProblemCategory 节点）"),
        ("domain", "should", "所属领域"),
        ("flow_family", "should", "算法族（和什么方向的方法比较）"),
        ("why_hard", "optional", "现有方法瓶颈"),
        ("keywords", "optional", "关键词"),
        ("relation_hints", "optional", "关系线索"),
        # --- S1：写作方法论属性（来自 docs/new/01-09）---
        ("paradigm", "should", "研究范式 formal/empirical/design/interpretive"),
        ("evidence_type", "should", "证据类型 causal_inference/derivational/"
         "experimental/simulational/correlational/interpretive"),
        ("evidence_norm", "optional", "该领域认可的指标与证据规范"),
        ("figures", "optional", "图表清单[{label,caption,kind,for_contribution}]"),
        ("section_map", "optional", "章节→论断映射[{section,claims[]}]"),
        ("gaps", "optional", "论文指出的研究空白[{gap_type,statement,evidence}]"),
        # 可复用输入（供阶段03 检索 / 07 素材 / 12 引用校验）
        ("authors", "should", "作者列表（检索元数据）"),
        ("abstract", "should", "摘要原文（向量索引召回用）"),
        ("claims", "optional", "论文提出的主张[{statement,evidence}]（写作参考）"),
        ("references", "optional", "参考文献标识列表（补足 RELATED_TO）"),
        # 从别的论文解析出的「前沿/失败/协议/写作惯例」事实（阶段02/04/05/06/08）
        ("open_problems", "optional", "别人明确陈述的开放问题[{statement,evidence}]"),
        ("delta_claims", "optional", "别人声称的增量[{statement,baseline,evidence}]"),
        ("negative_results", "optional", "别人报告的阴性结果/失败尝试[]"),
        ("protocol_disclosure", "optional", "别人披露的实验协议声明[]"),
        # P2/P4/P6 支撑字段（规则可抽，零 LLM 成本）
        ("data_sources", "optional", "论文使用的数据源[]（ZINC/ChEMBL/...）"),
        ("dedup_rule", "optional", "去泄漏规则（如 Tanimoto>=0.6）"),
        ("split_spec", "optional", "训练/验证/测试划分"),
        ("hyperparams", "optional", "关键超参[{param,value,context}]"),
        ("result_tables", "optional", "结果表[{label,columns,rows}]"),
        ("citation_style", "optional", "author-year|numeric|other"),
        ("writing_style", "optional", "章节与措辞惯例（从同类论文归纳）"),
    )),
    "Algorithm": ("算法（论文提出的方法）", (
        ("name", "must", "算法名"),
        ("task_type", "should", "任务类型（12 类枚举）"),
        ("flow_family", "should", "算法族（18 族枚举）"),
        ("problems_solved", "should", "能解决什么问题"),
        ("mechanism", "should", "机理"),
        ("why_it_works", "optional", "为什么有效"),
        ("applicable_to", "optional", "适用场景"),
        ("limitations", "optional", "局限（文本，不建节点）"),
        ("assumptions", "optional", "方法成立的前提[]（Type II 泄露检查用）"),
        ("novelty_basis", "optional", "新颖性依据[]：technical_constraint/"
         "theoretical_blind_spot/data_availability"),
    )),
    "AlgorithmModule": ("算法模块（原 AlgorithmStep）", (
        ("name", "must", "模块名"),
        ("mechanism", "should", "该模块机理"),
        ("formula", "optional", "公式/方程（文本，不建节点）"),
        ("inputs", "should", "输入"),
        ("outputs", "should", "输出"),
        ("is_novel_component", "optional", "是否论文声称的创新组件（消融规划用）"),
        ("component_role", "optional", "backbone/encoder/decoder/loss/sampler/other"),
    )),
    "CodeRepository": ("代码仓库", (
        ("repo_name", "must", "仓库名"),
        ("repo_url", "should", "仓库地址"),
        ("local_path", "optional", "本地路径"),
        ("license", "optional", "许可证"),
        ("is_original_repo", "should", "是否作者原仓库"),
    )),
    "CodeFunction": ("代码函数（模块的实现证据）", (
        ("name", "must", "函数名"),
        ("purpose", "should", "作用"),
        ("comment", "optional", "注释/文档"),
        ("params", "optional", "参数"),
        ("returns", "optional", "返回值"),
        ("func_type", "should", "函数类型（generator/forward/loss/transform/io…）"),
    )),
    "Benchmark": ("评测基准/数据集", (
        ("name", "must", "基准名"),
        ("input_form", "should", "输入数据形式"),
        ("output_form", "should", "输出数据形式"),
        ("n_samples", "should", "样本量"),
        ("scale", "optional", "规模档位"),
        ("modality", "optional", "数据模态"),
        ("research_object", "optional", "研究对象"),
        ("metrics", "should", "指标列表[{name,unit,direction,sota_model,sota_value}]"),
        ("model_results", "should", "各模型结果[{model,metric,value,unit,is_sota}]"),
        ("sota_by_metric", "optional", "动态 SOTA"),
        ("is_evaluation", "should", "是否评测基准"),
        ("protocol", "optional", "实验协议{seeds,split,eval_script,epochs,hardware}"),
        ("failure_modes", "optional", "适用本基准的失败模式 id[]"),
    )),
}

# 语义层关系：(关系, domain, range, 说明)
SEMANTIC_RELATIONS: Dict[str, Tuple[str, str, str]] = {
    "PROPOSES_METHOD": ("Paper", "Algorithm", "论文提出算法"),
    "HAS_CODE": ("Paper", "CodeRepository", "论文关联代码仓库"),
    "EVALUATED_ON": ("Paper|Algorithm", "Benchmark", "在哪个基准上评测"),
    "HAS_MODULE": ("Algorithm", "AlgorithmModule", "算法由哪些模块构成"),
    "MODULE_IMPLEMENTED_BY": ("AlgorithmModule", "CodeFunction", "模块由哪个函数实现"),
    "HAS_FUNCTION": ("CodeRepository", "CodeFunction", "仓库包含函数"),
    "BELONGS_TO_MODULE": ("CodeFunction", "AlgorithmModule", "函数所属模块（反向）"),
    "RELATED_TO": ("Paper", "Paper|Algorithm", "相关文献/方法"),
    "SUBCLASS_OF": ("Algorithm", "Algorithm", "算法继承/改进关系"),
}

# 被删类 → 语义层落点 / 应用层承接
REMOVED_CLASS_MAP: Dict[str, Tuple[str, str]] = {
    "ResearchQuestion": ("Paper.research_question", "AppResearchQuestion"),
    "ProblemCategory": ("Paper.problem_category", "AppProblemCategory"),
    "MetricDefinition": ("Benchmark.metrics[]", "AppMetricDefinition"),
    "LeaderboardEntry": ("Benchmark.model_results[]", "AppLeaderboardEntry"),
    "DataContract": ("Benchmark 的 input/output/规模字段", "AppDataContract"),
    "Evidence": ("observation/paper 的溯源字段", "AppEvidence"),
    "Limitation": ("Algorithm.limitations（文本）", "AppLimitation"),
    "SourcePaper": ("不建节点，用 Paper-RELATED_TO->Paper", "AppSourcePaper"),
    "AlgorithmStep": ("语义层 AlgorithmModule（改名）", "—"),
}

# 属性级别 → 归一（must/should/optional 与旧 must_have 兼容）
LEVEL_ALIAS = {"must": "must_have", "should": "should_have",
               "optional": "optional"}


def snapshot() -> Dict[str, Any]:
    return {"version": SEMANTIC_VERSION,
            "n_classes": len(SEMANTIC_CLASSES),
            "n_relations": len(SEMANTIC_RELATIONS),
            "classes": sorted(SEMANTIC_CLASSES),
            "relations": sorted(SEMANTIC_RELATIONS),
            "removed": sorted(REMOVED_CLASS_MAP)}


def check_domain_range(src: str, rel: str, dst: str) -> bool:
    r = SEMANTIC_RELATIONS.get(rel)
    if not r:
        return False

    def ok(spec: str, actual: str) -> bool:
        return actual in [x.strip() for x in str(spec).split("|")]
    return ok(r[0], src) and ok(r[1], dst)


def class_snapshot() -> Dict[str, Any]:
    return {name: {"definition": d,
                   "fields": [{"name": f, "level": LEVEL_ALIAS[lv],
                               "note": note}
                              for f, lv, note in fields]}
            for name, (d, fields) in SEMANTIC_CLASSES.items()}


def field_names(cls: str) -> Tuple[str, ...]:
    return tuple(f for f, _lv, _n in SEMANTIC_CLASSES[cls][1])
