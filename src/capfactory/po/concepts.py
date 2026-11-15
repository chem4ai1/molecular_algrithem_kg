"""问题导向概念层：34 类概念的字段契约与维度归属.

报告 §5.1 给出每类的「职责/边界」与「建议核心字段」，SHACL 给出结构约束。
本模块把它们变成**可执行的字段契约**：每类声明所属维度、必填字段、
受控词表绑定与推荐字段；``Concept.validate()`` 做归一与缺失检查。

与「统一大表」相比，这样做保留了报告强调的边界：
CapabilityClaim 不是 Algorithm 的布尔属性；MetricDefinition 不是 MetricObservation；
Dataset 不是 DatasetSplit；Paper 不是 PaperVersion；CodeArtifact/WeightArtifact/DataArtifact 三轴独立。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .vocab import default_registry

DIMENSIONS = {
    "problem": "问题维度：可检验的问题树与背景",
    "knowledge": "知识维度：主张、局限、证据、版本与归属",
    "algorithm_data": "算法数据维度：任务、方法、流程、数据集与切分",
    "code": "代码维度：源码/权重/数据的多轴开放性",
    "metric": "指标维度：定义、评测、观测、条件、终点",
    "taxonomy": "分类维度：应用领域 D0–D10 与算法族 A01–A18",
    "supporting": "支撑维度：分子、靶标、漏斗、负结果、目标、物种、断言",
}

# 关系 → (允许的 domain, 允许的 range)，来自 ontology_relations.csv
RELATION_DOMAIN_RANGE: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "HAS_VERSION": (("Paper",), ("PaperVersion",)),
    "FORMULATES": (("Paper",), ("ResearchQuestion",)),
    "MOTIVATED_BY": (("ResearchQuestion",), ("ProblemContext",)),
    "OPERATIONALIZED_AS": (("ResearchQuestion",), ("Task",)),
    "ADDRESSED_BY": (("Task",), ("Algorithm",)),
    "IMPLEMENTS": (("Workflow",), ("Algorithm",)),
    "PROPOSES_WORKFLOW": (("Paper",), ("Workflow",)),
    "ABOUT_METHOD": (("CapabilityClaim",), ("Workflow", "Algorithm")),
    "HAS_CLAIM": (("Paper",), ("CapabilityClaim",)),
    "EVALUATED_IN": (("CapabilityClaim",), ("EvaluationRun",)),
    "SUPPORTED_BY": (("CapabilityClaim", "MetricObservation", "Limitation", "NegativeOutcome"), ("Evidence",)),
    "EXTRACTED_FROM": (("Evidence",), ("PaperVersion",)),
    "USES_METRIC": (("EvaluationRun", "Benchmark"), ("MetricDefinition",)),
    "PRODUCES_OBSERVATION": (("EvaluationRun",), ("MetricObservation",)),
    "OF_METRIC": (("MetricObservation",), ("MetricDefinition",)),
    "HAS_CONDITION": (("EvaluationRun", "MetricObservation"), ("ExperimentalCondition",)),
    "HAS_ASSAY": (("EvaluationRun",), ("Assay",)),
    "MEASURES_ENDPOINT": (("Assay",), ("Endpoint",)),
    "ABOUT_SUBJECT": (("MetricObservation",), ("Molecule", "CandidateSet", "Algorithm")),
    "FOR_TARGET": (("MetricObservation",), ("Target",)),
    "USES_DATASET": (("Workflow", "EvaluationRun", "Benchmark"), ("Dataset",)),
    "HAS_SPLIT": (("Dataset",), ("DatasetSplit",)),
    "QUALIFIES": (("Limitation",), ("CapabilityClaim",)),
    "BROADER": (("ResearchProblem",), ("ProblemCategory",)),
    "ADDRESSES": (("Paper",), ("ResearchProblem",)),
    "EXPOSES_LIMITATION": (("Paper",), ("ResearchProblem",)),
    "ANALYST_RELEVANT_TO": (("Paper",), ("ResearchProblem",)),
    "HAS_CODE": (("Paper", "Workflow", "Algorithm"), ("CodeArtifact",)),
    "HAS_WEIGHTS": (("Paper", "Workflow", "Algorithm"), ("WeightArtifact",)),
    "HAS_DATA": (("Paper", "Workflow", "Algorithm"), ("DataArtifact",)),
    "MEMBER_OF": (("Paper",), ("EvidenceFamily",)),
    "REPORTS_CAMPAIGN": (("Paper",), ("DesignCampaign",)),
    "HAS_STAGE": (("DesignCampaign",), ("SelectionStage",)),
    "HAS_NEGATIVE_OUTCOME": (("DesignCampaign",), ("NegativeOutcome",)),
    "HAS_OBJECTIVE": (("Workflow", "DesignCampaign"), ("Objective",)),
    "HAS_STATE": (("Molecule",), ("MoleculeState",)),
    "ON_ORGANISM": (("EvaluationRun", "Target"), ("Organism",)),
    "CORRECTED_BY": (("PaperVersion",), ("PaperVersion",)),
    # 基准与排行榜（SOTA）
    "EVALUATED_ON": (("Paper", "CodeArtifact", "Algorithm", "Workflow"), ("Benchmark",)),
    "BENCHMARK_FOR": (("Benchmark",), ("ResearchProblem",)),
    "HAS_LEADERBOARD": (("Benchmark",), ("LeaderboardEntry",)),
    "REPORTED_BY": (("LeaderboardEntry",), ("Paper", "CodeArtifact")),
    "FROM_OBSERVATION": (("LeaderboardEntry",), ("MetricObservation",)),
    # 领域 / 算法族分类（多对多：一篇论文可属多个领域、使用多个算法族）
    "IN_DOMAIN": (("Paper", "Algorithm", "Workflow", "CapabilityClaim", "Task"),
                  ("Domain",)),
    "USES_ALGO_FAMILY": (("Paper", "Algorithm", "Workflow", "CapabilityClaim"),
                         ("AlgorithmFamily",)),
}


@dataclass(frozen=True)
class ConceptSpec:
    """一类概念的字段契约。"""

    name: str
    dimension: str
    definition: str
    required: Tuple[str, ...] = ()
    vocab: Dict[str, str] = field(default_factory=dict)      # field -> vocabulary name
    recommended: Tuple[str, ...] = ()


def S(name: str, dimension: str, definition: str, required=(),
      vocab: Optional[Dict[str, str]] = None, recommended=()) -> ConceptSpec:
    return ConceptSpec(name, dimension, definition, tuple(required), dict(vocab or {}),
                       tuple(recommended))


CONCEPT_SPECS: Dict[str, ConceptSpec] = {
    s.name: s for s in (
        # ---------------- 问题 ----------------
        S("ProblemCategory", "problem", "分析者构建的可层级问题分类；不是领域穷尽清单",
          ("label",), {"attribution": "attribution"}, ("scope", "background", "category")),
        S("ResearchProblem", "problem", "可检验的失败点/尚未满足需求，P01a–P11b",
          ("label", "question"), {"status": "problem_status", "attribution": "attribution"},
          ("scope", "suggested_solution", "parent", "related_papers")),
        S("ResearchQuestion", "problem", "针对一篇论文把研究目的转成问题",
          ("question",), {"attribution": "attribution"}, ("paper_id",)),
        S("ProblemContext", "problem", "疾病、生物学与技术动机",
          (), {}, ("background", "system", "assumptions")),
        # ---------------- 知识 ----------------
        S("Paper", "knowledge", "work-level 文献身份；一个 DOI 不代表一个实验或算法",
          ("title",), {}, ("doi", "year", "venue", "reading_coverage", "coverage_gap")),
        S("PaperVersion", "knowledge", "期刊版/作者稿/更正版本；证据严格绑定到版本",
          ("paper_id",), {"source_kind": "source_kind", "coverage_level": "coverage_level"},
          ("source_url", "version_date", "version_status", "sha256")),
        S("CapabilityClaim", "knowledge", "主体+能力+适用条件+证据；不表示无限泛化",
          ("statement", "scope"), {"evidence_level": "evidence_level", "attribution": "attribution"},
          ("method_id", "limitations", "evidence_ids")),
        S("Limitation", "knowledge", "作者明确局限或分析者推断，必须区分归属",
          ("statement",), {"attribution": "attribution"}, ("scope", "next_research_question")),
        S("Evidence", "knowledge", "原文版本+节/页/图表+原始文件 hash",
          ("paper_version_id", "locator"), {"attribution": "attribution"},
          ("section", "source_url", "extraction_file_sha256", "quote", "read_date")),
        S("EvidenceFamily", "knowledge", "共享平台/数据/队伍；不等于独立复现",
          ("label",), {"independence_status": "independence_status"}, ("basis", "member_paper_ids")),
        S("Assertion", "knowledge", "属性图边的 RDF reification；保留推断归属",
          ("subject", "predicate", "object"),
          {"attribution": "attribution", "predicate": "relation_type"},
          ("evidence_ids",)),
        # ---------------- 算法数据 ----------------
        S("Task", "algorithm_data", "定义输入/输出/前置条件；不是宽泛能力",
          ("task_family",), {"task_family": "task_family"},
          ("input_output", "input_condition", "sample_budget", "top_k")),
        S("Algorithm", "algorithm_data", "方法身份；共享平台不重复计独立算法",
          ("name",), {"architecture": "algorithm_architecture"},
          ("version_status", "platform", "paper_ids")),
        S("Workflow", "algorithm_data", "生成→过滤→人工选择→实验等步骤组成的流程",
          ("steps",), {}, ("human_contribution", "scope", "algorithm_ids")),
        S("Dataset", "algorithm_data", "数据来源身份及版本；不等于具体切分",
          ("name",), {}, ("version", "origin", "license_status", "size", "source_evidence_ids")),
        S("DatasetSplit", "algorithm_data", "train/val/test、时间/同源/口袋规则",
          ("rule",), {"overlap_risk": "overlap_risk", "split_type": "split_type"},
          ("subset", "size", "leakage_audit")),
        S("Benchmark", "algorithm_data",
          "可复现评测基准 = 数据 + 切分 + 指标 + 协议；不等于原始数据集",
          ("name",),
          {"task_family": "task_family", "split_type": "split_type",
           "license_status": "license"},
          ("input_schema", "output_schema", "research_object", "version",
           "metric_ids", "problem_ids", "size", "url", "dataset_id",
           "source_evidence_ids")),
        S("Objective", "algorithm_data", "优化目标/约束；方向依疾病与组织目标而定",
          ("label",), {"direction": "objective_direction"}, ("scope",)),
        # ---------------- 代码 ----------------
        S("CodeArtifact", "code", "源码资源；核心与辅助分开描述",
          ("availability", "license"),
          {"availability": "availability", "license": "license", "artifact_kind": "artifact_kind",
           "scope": "artifact_scope"},
          ("url", "checked_date", "evidence_basis", "sha256", "language")),
        S("WeightArtifact", "code", "权重取得与使用许可（与源码条款可能不同）",
          ("availability", "license"), {"availability": "availability", "license": "license"},
          ("url", "checked_date", "missing_reason")),
        S("DataArtifact", "code", "论文共享数据可用性与许可",
          ("availability", "license"), {"availability": "availability", "license": "license"},
          ("url", "checked_date", "missing_reason")),
        # ---------------- 指标 ----------------
        S("EvaluationRun", "metric", "特定模型/任务/条件下作者报告的实验；本项目未重跑",
          ("evaluation_kind",), {"evaluation_kind": "evaluation_kind",
                                  "modality": "evidence_modality"},
          ("protocol", "budget", "scope", "source_paper")),
        S("MetricDefinition", "metric", "稳定语义、公式/方向、单位和局限",
          ("name", "direction"),
          {"direction": "metric_direction", "unit_scale": "unit_scale", "value_type": "value_type"},
          ("definition", "interpretation", "formula")),
        S("MetricObservation", "metric", "一次报告值；不与跨条件结果平均混合",
          ("metric_definition_id", "unit", "evidence_ids"),
          {"missing_state": "missing_state", "aggregation": "aggregation", "unit": "unit",
           "modality": "evidence_modality", "stage": "stage"},
          ("value", "subject", "target", "condition", "numerator", "denominator",
           "threshold", "top_k", "sample_budget", "split", "source_version", "missing_reasons")),
        S("ExperimentalCondition", "metric", "计算和实验共有的条件对象",
          (), {}, ("pH", "substrate", "system", "dose", "time", "threshold",
                   "sample_budget", "top_k", "n_biological", "split", "stage")),
        S("Assay", "metric", "生化 assay 或计算 benchmark protocol",
          ("name",), {"modality": "evidence_modality", "assay_kind": "assay_kind"},
          ("protocol", "readout", "protocol_completion")),
        S("Endpoint", "metric", "实际测量/估计对象，与指标格式区分",
          ("label",), {"modality": "evidence_modality", "endpoint_type": "endpoint_type"},
          ("interpretation",)),
        S("LeaderboardEntry", "metric",
          "某基准某指标上的一条可比成绩；SOTA 是同可比键下按方向的极值",
          ("benchmark_id", "metric_id", "value"),
          {"missing_state": "missing_state"},
          ("direction", "rank", "is_sota", "subject", "paper_id", "code_id",
           "comparability_key", "protocol_signature", "source_observation")),
        # ---------------- 分类（领域 / 算法族） ----------------
        S("Domain", "taxonomy", "应用领域 D0–D10；一篇论文/能力可属多个领域",
          ("label",), {"code": "domain_code"}, ("definition", "scope", "paper_count")),
        S("AlgorithmFamily", "taxonomy", "算法族 A01–A18；方法身份，与 Algorithm.architecture 互补",
          ("label",), {"code": "algo_code"},
          ("description", "representative_methods", "paper_count")),
        # ---------------- 支撑 ----------------
        S("Molecule", "supporting", "有化学身份的化合物/肽；不能用一个候选集合冒充单分子",
          ("label",), {"identifier_status": "identifier_status"},
          ("sequence_or_smiles", "external_id")),
        S("CandidateSet", "supporting", "生成/提名/入测的样本群；保留选择逻辑",
          ("label",), {}, ("selection", "sample_size", "stage")),
        S("MoleculeState", "supporting", "构象、质子化、立体化学及复合状态",
          (), {}, ("state_type", "coordinates", "conditions")),
        S("Target", "supporting", "蛋白/靶标构建体；不把数据集名当靶点",
          ("name",), {"external_id_status": "identifier_status"},
          ("species", "construct", "external_id")),
        S("Organism", "supporting", "物种/菌株；本地身份直到外部 ID 可核验",
          ("label",), {}, ("taxonomy_status", "strain")),
        S("DesignCampaign", "supporting", "靶标与目标产品属性下的一轮或多轮研发",
          ("objective",), {}, ("scope", "round", "target_id")),
        S("SelectionStage", "supporting", "生成→提名→合成→测定；计数有明确阶段",
          ("stage_type",), {"stage_type": "stage_type", "stage": "stage"},
          ("count", "unit", "selection_rule", "denominator")),
        S("NegativeOutcome", "supporting", "测到阴性、合成失败与未测是不同状态",
          ("outcome_type",), {"outcome_type": "outcome_type", "missing_state": "missing_state"},
          ("count", "reason", "evidence_ids")),
    )
}

CONCEPT_CLASSES = tuple(CONCEPT_SPECS)


def concept_class_fields(name: str) -> Dict[str, Any]:
    """供 API/文档生成器使用的字段契约。"""
    s = CONCEPT_SPECS.get(name)
    if not s:
        return {}
    return {"name": s.name, "dimension": s.dimension, "definition": s.definition,
            "required": list(s.required), "recommended": list(s.recommended),
            "vocab_bindings": dict(s.vocab)}


@dataclass
class Concept:
    """一个 PO 概念实例。"""

    id: str
    type: str
    label: str = ""
    attrs: Dict[str, Any] = field(default_factory=dict)
    attribution: str = "analyst_synthesis"
    evidence_ids: List[str] = field(default_factory=list)
    source_version: str = ""
    missing_states: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Concept":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def validate(self, registry=None) -> List[str]:
        """字段契约校验：必填、词表归一、value/missing_state 互斥。"""
        reg = registry or default_registry
        spec = CONCEPT_SPECS.get(self.type)
        problems: List[str] = []
        if not spec:
            return [f"未知概念类 {self.type!r}"]
        for fld in spec.required:
            if fld == "evidence_ids":
                if not (self.evidence_ids or self.attrs.get("evidence_ids")):
                    problems.append(f"{self.type}.{fld} 为空（观测必须绑定证据）")
            elif fld not in self.attrs or self.attrs[fld] in (None, "", []):
                problems.append(f"{self.type} 缺少必填字段 {fld}")
        for fld, vocab in spec.vocab.items():
            if fld in self.attrs and self.attrs[fld] not in (None, ""):
                canonical, ok = reg.normalize(vocab, self.attrs[fld])
                if ok and canonical:
                    self.attrs[fld] = canonical
                else:
                    problems.extend(f"{self.type}.{fld}: {p}" for p in reg.validate(vocab, self.attrs[fld]))
        canonical, ok = reg.normalize("attribution", self.attribution)
        if ok and canonical:
            self.attribution = canonical
        else:
            problems.extend(f"{self.type}.attribution: {p}"
                            for p in reg.validate("attribution", self.attribution))
        if self.type == "MetricObservation":
            has_value = self.attrs.get("value") is not None
            # SHACL xone 约束的是「观测级」missingState；
            # missing_states 是「字段级」缺失说明（如 CI 未抽取），两者不可混为一谈。
            has_missing = bool(self.attrs.get("missing_state"))
            if has_value == has_missing:
                problems.append("MetricObservation 违反 SHACL xone：value 与 missing_state "
                                "必须恰好有一个（缺失不是 0/false）")
            if has_value and not isinstance(self.attrs.get("value"), (int, float)):
                problems.append("MetricObservation.value 必须是数值")
            for k, v in self.missing_states.items():
                _, ok = reg.normalize("missing_state", v)
                if not ok:
                    problems.append(f"missing_states.{k}={v!r} 非法")
        return problems
