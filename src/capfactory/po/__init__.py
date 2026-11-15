"""问题导向本体层（Problem-Oriented Ontology, PO）.

依据 ``问题导向本体与知识图谱架构_20261109/研究报告.md`` 及其 OWL/SHACL/实例数据，
补齐 CapFactory 原先缺失的五个维度：

- **问题**：ProblemCategory(P01–P11) / ResearchProblem / ResearchQuestion / ProblemContext；
- **知识**：CapabilityClaim / Limitation / Evidence / PaperVersion / EvidenceFamily / Assertion；
- **算法数据**：Task / Algorithm / Workflow / Dataset / DatasetSplit / Objective；
- **代码**：CodeArtifact / WeightArtifact / DataArtifact（开放性多轴，非二值开源）；
- **指标**：MetricDefinition / EvaluationRun / MetricObservation / ExperimentalCondition /
  Assay / Endpoint（定义与观测分离、value 与 missingState 互斥）。

设计原则（报告 §5.3）：问题/任务/方法分离；能力主张不是算法布尔属性；
指标定义与观测分离；缺失不是 false；归属（作者/分析者）必须显式；
开放世界与结构校验分离。

本层**不推翻**现有 ``domain`` / ``algograph`` schema，而是提供受控词表、
概念层、校验器、导入器与双向映射，使现有能力可升级到 PO 语义。
"""

from .vocab import Vocabulary, VocabularyRegistry, default_registry, load_report_vocab
from .concepts import (
    CONCEPT_CLASSES, RELATION_DOMAIN_RANGE, Concept, concept_class_fields,
)
from .comparability import ComparabilityKey, comparability_key, compare_observations
from .validation import validate_po_graph
from .store import POGraph, Assertion
from .mapper import (
    capability_to_po, evidence_to_po, metric_profile_to_po, po_to_capability,
)
from .importer import import_report_bundle
from .taxonomy import (
    ALGO_NAMES, DOMAIN_NAMES, PAPER_TAXONOMY, apply_taxonomy, apply_taxonomy_to_kg,
    classify, classify_with_evidence, taxonomy_matrix, taxonomy_spec,
)
from .keywords import DOMAIN_KEYWORDS, ALGO_KEYWORDS, keyword_stats, keyword_table
from .semantics import (
    CONCEPT_SEMANTICS, RELATION_SEMANTICS, INFERENCE_RULES, TASK_PROTOCOLS,
    SemanticBundle, build_bundle, bundle_summary, context_pack,
)
from .reasoning import discover_gaps, infer, stats_report, summarize
from .prompts import build_prompt, prompt_catalog

__all__ = [
    "Vocabulary", "VocabularyRegistry", "default_registry", "load_report_vocab",
    "CONCEPT_CLASSES", "RELATION_DOMAIN_RANGE", "Concept", "concept_class_fields",
    "ComparabilityKey", "comparability_key", "compare_observations",
    "validate_po_graph", "POGraph", "Assertion",
    "capability_to_po", "po_to_capability", "evidence_to_po", "metric_profile_to_po",
    "import_report_bundle",
    "DOMAIN_NAMES", "ALGO_NAMES", "PAPER_TAXONOMY",
    "apply_taxonomy", "apply_taxonomy_to_kg", "classify",
    "classify_with_evidence", "taxonomy_matrix", "taxonomy_spec",
]
