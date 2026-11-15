"""V2 概念模型：17 类、四层、字段三态。

设计依据见 ``docs/ARCHITECTURE_V2.md`` 与 ``docs/SCHEMA_AUDIT.md``。

与 V1（``capfactory/po/concepts.py`` 的 38 类）的三个区别：

1. **按论文结构分层**（文献/问题/方法/评测），不按本体维度；
2. **每个字段标 source**：``extracted``(LLM) / ``derived``(规则) / ``inherited``(父节点)；
3. **每个字段标 level**：``must_have`` / ``should_have`` / ``optional``，
   且不存在零 must_have 的类（修掉 V1 的 3 个垃圾桶类）。

本模块只提供**定义**，不替换现有图数据；``ontology/__init__.py`` 同时导出
V1 兼容符号，让新旧代码共存。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

SOURCE = ("extracted", "derived", "inherited")
LEVEL = ("must_have", "should_have", "optional")
LAYERS = ("literature", "problem", "method", "evaluation", "code",
          "generation", "crosscut")


@dataclass(frozen=True)
class Field:
    name: str
    source: str
    level: str = "optional"
    inherit_from: str = ""

    def __post_init__(self) -> None:
        assert self.source in SOURCE, self.source
        assert self.level in LEVEL, self.level
        if self.source == "inherited":
            assert self.inherit_from, f"{self.name} inherited 必须给 inherit_from"


@dataclass(frozen=True)
class ConceptV2:
    name: str
    layer: str
    definition: str
    fields: Tuple[Field, ...]
    absorbs: Tuple[str, ...] = ()      # 吸收的 V1 类

    def __post_init__(self) -> None:
        assert self.layer in LAYERS, self.layer
        assert any(f.level == "must_have" for f in self.fields), \
            f"{self.name} 不允许零 must_have"

    @property
    def extracted(self) -> Tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.source == "extracted")

    @property
    def derived(self) -> Tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.source == "derived")

    @property
    def inherited(self) -> Tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.source == "inherited")


def F(name: str, source: str = "extracted", level: str = "optional",
      inherit_from: str = "") -> Field:
    return Field(name, source, level, inherit_from)


# ---------------------------------------------------------------------------
# 17 类
# ---------------------------------------------------------------------------
V2_CLASSES: Dict[str, ConceptV2] = {c.name: c for c in (

    # ---- L0 文献层：论文里有什么 ----
    ConceptV2("Paper", "literature", "一篇论文（含期刊版与预印本身份）", (
        F("title", level="must_have"), F("arxiv_id"), F("doi"),
        F("year"), F("venue"), F("domain_codes", "derived"),
        F("algo_codes", "derived"), F("versions", "derived"),
        # 精简第一档补齐：论文三核心（实测 36/36 在用）
        F("research_problem", "extracted", "should_have"),
        F("problem_type", "derived", "should_have"),
        F("domain", "derived", "should_have"),
        F("domain_code", "derived", "should_have"),
        F("algorithm_family", "derived", "should_have"),
        F("algorithm_family_id", "derived", "should_have"),
        F("why_hard", "extracted"), F("relation_hints", "derived"),
    ), absorbs=("Paper", "PaperVersion")),

    ConceptV2("Section", "literature", "论文的一个小节，证据的最小可引用单位", (
        F("role", level="must_have"),       # abstract/method/result/discussion/limitation
        F("title"), F("char_span"), F("text"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
    )),

    ConceptV2("Evidence", "literature", "可回溯到 Section 的一条原文证据", (
        F("quote", level="must_have"),
        F("section_id", level="must_have"),
        F("attribution", "derived"), F("paper_id", "inherited", "should_have", "Paper.id"),
        F("section"), F("extraction_method"),
    ), absorbs=("Evidence", "EvidenceFamily", "Assertion")),

    ConceptV2("CodeRepository", "literature", "一个代码仓库（含源码/权重/数据三轴开放性）", (
        F("repo_name", level="must_have"),
        F("availability", level="should_have"), F("license"),
        F("repo_url"), F("local_path"), F("commit"), F("sha256", "derived"),
        F("language"), F("loc", "derived"),
        F("capability_version_id", "derived"), F("module_ids", "derived"),
        F("has_requirements", "derived"), F("entry_point", "derived"),
        F("runnable", "derived"), F("paper_ids", "derived"),
        F("is_original_repo", "derived"), F("repo_provenance"),
    ), absorbs=("CodeArtifact", "WeightArtifact", "DataArtifact")),

    # ---- L1 问题层：为什么做 ----
    ConceptV2("ResearchQuestion", "problem", "论文要回答的可检验问题（可挂父问题）", (
        F("question", level="must_have"),
        F("granularity"),               # category | subproblem | paper_specific
        F("parent"), F("status"), F("paper_ids", "derived"),
    ), absorbs=("ResearchQuestion", "ResearchProblem", "ProblemContext")),

    ConceptV2("ProblemCategory", "problem", "P01–P11 抽象问题类别（标签）", (
        F("code", level="must_have"), F("label"),
        F("n_papers", "derived"), F("n_benchmarks", "derived"),
    )),

    # ---- L2 方法层：怎么做 ----
    ConceptV2("Algorithm", "method", "一个方法/流程/优化目标，用 kind 区分", (
        F("name", level="must_have"),
        F("kind", level="should_have"),   # method | component | baseline | workflow | objective
        F("granularity"), F("architecture"), F("algo_codes", "derived"),
        F("paper_ids", "derived"), F("repository_id", "derived"),
        # 精简第一档补齐：问题/机理核心（实测 34/34 在用）
        F("schema_family", "derived", "should_have"),
        F("task_type", "derived", "should_have"),
        F("task_type_label", "derived"),
        F("problems_solved", "extracted", "should_have"),
        F("mechanism", "extracted", "should_have"),
        F("mechanism_steps", "extracted"), F("why_it_works", "extracted"),
        F("applicable_to", "extracted"), F("limitations", "extracted"),
        F("baseline_group", "derived"), F("search_text", "derived"),
    ), absorbs=("Algorithm", "Workflow", "Objective")),

    ConceptV2("CapabilityClaim", "method", "带适用范围的能力主张", (
        F("statement", level="must_have"),
        F("claim_scope", level="should_have"), F("attribution"),
        F("evidence_level"), F("method_id", "derived"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
        F("problem_ids", "derived"),
    )),

    ConceptV2("Limitation", "method", "局限、阴性结果、未达成目标", (
        F("statement", level="must_have"), F("kind"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
    ), absorbs=("Limitation", "NegativeOutcome")),

    # ---- L3 评测层：怎么算分 ----
    ConceptV2("Benchmark", "evaluation", "单一评测单位 = 数据 + 切分 + 指标 + 协议", (
        F("name", level="must_have"),
        F("aliases"), F("version"), F("data_source"), F("modality"), F("task_type"),
        F("n_samples"), F("n_targets"),
        F("split_type", level="should_have"), F("split_ratio"), F("leakage_risk"),
        F("metric_ids", "derived"), F("top_k"), F("sample_budget"),
        F("threshold"), F("stage"),
        F("research_object"), F("input_schema"), F("output_schema"),
        F("problem_ids", "derived"),
        F("availability"), F("license"), F("url"), F("source_evidence_ids"),
        F("comparability_profile", "derived", "must_have"),
        F("tested_by_papers", "derived"), F("tested_by_codes", "derived"),
        F("n_observations", "derived"),
        # 精简第一档补齐：数据契约与可更新榜单（实测 85/85 在用）
        F("schema_family", "derived", "should_have"),
        F("input_form", "extracted", "should_have"),
        F("output_form", "extracted", "should_have"),
        F("metrics", "derived", "should_have"),
        F("model_results", "derived"), F("sota_by_metric", "derived"),
        F("matrix", "derived"), F("is_evaluation", "derived"),
        F("scale"),
    ), absorbs=("Benchmark", "Dataset", "DatasetSplit")),

    ConceptV2("MetricDefinition", "evaluation", "指标定义（不是一次观测）", (
        F("name", level="must_have"),
        F("direction", level="should_have"), F("unit"), F("value_type"),
        F("aggregation"), F("modality"),
    )),

    ConceptV2("EvaluationRun", "evaluation", "一次评测事件", (
        F("evaluation_kind", level="must_have"),
        F("benchmark_id", "inherited", "should_have", "Benchmark.id"),
        F("paper_id", "inherited", "should_have", "Paper.id"),
    )),

    ConceptV2("Observation", "evaluation", "一次原子观测（含条件/测定/终点）", (
        F("value", level="must_have"), F("metric_id", level="must_have"),
        F("unit", level="should_have"), F("subject"), F("modality"),
        F("condition"), F("aggregation"), F("numerator"), F("denominator"),
        F("stage", "inherited", "should_have", "Benchmark.comparability_profile.stage"),
        F("threshold", "inherited", "should_have", "Benchmark.comparability_profile.threshold"),
        F("top_k", "inherited", "should_have", "Benchmark.comparability_profile.top_k"),
        F("sample_budget", "inherited", "should_have", "Benchmark.comparability_profile.sample_budget"),
        F("split_type", "inherited", "should_have", "Benchmark.split_type"),
        F("missing_state"), F("evidence_ids", "derived"), F("metric"),
        F("comparability_key", "derived"),
    ), absorbs=("MetricObservation", "ExperimentalCondition", "Assay", "Endpoint")),

    ConceptV2("LeaderboardEntry", "evaluation", "某基准某指标上的一条可比成绩", (
        F("benchmark_id", level="must_have"),
        F("metric_id", level="must_have"), F("value", level="must_have"),
        F("group_key", "derived", "must_have"), F("rank", "derived"),
        F("is_sota", "derived"), F("sota_claimable", "derived"),
        F("paper_id", "derived"), F("code_id", "derived"),
        F("unit"), F("subject"),
    )),

    # ---- 横切：分类与研究对象 ----
    ConceptV2("Domain", "crosscut", "D0–D10 应用领域", (
        F("code", level="must_have"), F("label"),
        F("n_papers", "derived"),
    )),

    ConceptV2("AlgorithmFamily", "crosscut", "A01–A18 算法族", (
        F("code", level="must_have"), F("label"),
        F("n_papers", "derived"),
    )),

    ConceptV2("ResearchObject", "crosscut", "研究对象（分子/候选集/构象/靶点/物种）", (
        F("label", level="must_have"),
        F("kind", level="should_have"), F("organism"), F("state_type"),
        F("paper_ids", "derived"),
    ), absorbs=("Molecule", "CandidateSet", "MoleculeState", "Target", "Organism")),
)}


# 多值、需导航的关系一律用边；单值、只展示的用字段。
V2_RELATIONS: Dict[str, Tuple[str, str]] = {
    "HAS_SECTION": ("Paper", "Section"),
    "SUPPORTED_BY": ("CapabilityClaim|Observation|Limitation", "Evidence|Section"),
    "ADDRESSES": ("Paper", "ResearchQuestion"),
    "BROADER": ("ResearchQuestion", "ProblemCategory"),
    "PROPOSES_METHOD": ("Paper", "Algorithm"),
    "ABOUT_METHOD": ("CapabilityClaim", "Algorithm"),
    "HAS_CODE": ("Paper", "CodeRepository"),
    "USES_ALGO_FAMILY": ("Paper|Algorithm", "AlgorithmFamily"),
    "IN_DOMAIN": ("Paper|Algorithm|Benchmark", "Domain"),
    "EVALUATED_ON": ("Paper|CodeRepository|Algorithm", "Benchmark"),
    "BENCHMARK_FOR": ("Benchmark", "ResearchQuestion"),
    "USES_METRIC": ("Benchmark|EvaluationRun", "MetricDefinition"),
    "PRODUCES_OBSERVATION": ("EvaluationRun", "Observation"),
    "HAS_LEADERBOARD": ("Benchmark", "LeaderboardEntry"),
    "FROM_OBSERVATION": ("LeaderboardEntry", "Observation"),
    "REPORTED_BY": ("LeaderboardEntry", "Paper|CodeRepository"),
    "ABOUT_SUBJECT": ("Observation", "ResearchObject"),
}


def summary() -> Dict[str, object]:
    from collections import Counter
    return {
        "n_classes": len(V2_CLASSES),
        "n_relations": len(V2_RELATIONS),
        "by_layer": dict(Counter(c.layer for c in V2_CLASSES.values())),
        "by_source": dict(Counter(f.source for c in V2_CLASSES.values()
                                  for f in c.fields)),
        "absorbed_v1": sum(len(c.absorbs) for c in V2_CLASSES.values()),
        "zero_must_have": [c.name for c in V2_CLASSES.values()
                           if not any(f.level == "must_have" for f in c.fields)],
    }
