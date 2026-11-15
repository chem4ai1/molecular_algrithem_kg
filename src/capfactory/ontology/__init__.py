"""本体单一入口（V2 定义 + V1 兼容导出）。

新代码统一从这里导入，不再直接引用分散在 ``po/`` 下的 4 个定义文件::

    from capfactory.ontology import V2_CLASSES, Field, CONCEPT_SPECS, default_registry

* ``V2_CLASSES`` / ``V2_RELATIONS`` / ``Field``：精简后的 17 类新 schema（定义源）；
* ``CONCEPT_SPECS`` / ``RELATION_DOMAIN_RANGE`` / ``default_registry``：现有 38 类图
  的兼容导出，**行为完全不变**，用于读取已有 ``storage_cf/po/*.json``。
"""

from __future__ import annotations

from .modules import MECHANISM_HINTS
from .schema_v3 import (V3_CLASSES, V3_RELATIONS, ROOT_FAMILIES)
from .chains import (GROUPS, CHAINS, TENTACLE_SPECS, STAGES, Chain, ChainStep,
                     project_chains, render_chain_bundle,
                     extractable_classes, chains_summary)
from .generation import (
    GENERATION_CLASSES, DECISION_LINKS, REPRO_LINKS, NARRATIVE_LINKS,
    GENERATION_PHASES, RUBRIC_AXES, FIDELITY, POLARITY, ALLOWED_WORDING,
    relation_matrix as generation_relations,
    summary as generation_summary,
)
from .model import (
    V2_CLASSES, V2_RELATIONS, ConceptV2, Field, LAYERS, LEVEL, SOURCE,
    F, summary,
)
from .layers import (
    LAYER_CLASSES, INTRA_LAYER, CROSS_LAYER, APPLICATION_LINKS, CODE_LINKS,
    ALGORITHM_ROLES, DATA_FORMS, CAUSAL_TYPES, PHASES, ABSTRACTIONS,
    CAD_LEVEL_BUDGET, GAP_TYPES, AGREEMENT, MECHANISMS, GROUNDING_STATUS,
    EXTRACTION_PROTOCOL,
    ALGOGRAPH_NODE_TYPES, ALGOGRAPH_MAP, relation_matrix,
    summary as layers_summary,
)

# ---- V1 兼容导出（不改变任何现有行为）----
from ..po.concepts import CONCEPT_SPECS, DIMENSIONS, RELATION_DOMAIN_RANGE
from ..po.vocab import default_registry
from ..po.keywords import ALGO_KEYWORDS, DOMAIN_KEYWORDS, keyword_stats
from ..po.semantics import (
    CONCEPT_SEMANTICS, RELATION_SEMANTICS, INFERENCE_RULES, TASK_PROTOCOLS,
    build_bundle, bundle_summary, context_pack,
)
from ..po.taxonomy import DOMAIN_NAMES, ALGO_NAMES, classify, classify_with_evidence

__all__ = [
    # V2
    "V2_CLASSES", "V2_RELATIONS", "ConceptV2", "Field", "F",
    "LAYERS", "LEVEL", "SOURCE", "summary",
    "LAYER_CLASSES", "INTRA_LAYER", "CROSS_LAYER", "APPLICATION_LINKS",
    "CODE_LINKS", "ALGORITHM_ROLES", "DATA_FORMS", "CAUSAL_TYPES",
    "PHASES", "ABSTRACTIONS", "CAD_LEVEL_BUDGET", "GAP_TYPES", "AGREEMENT",
    "MECHANISMS", "GROUNDING_STATUS", "MECHANISM_HINTS",
    "EXTRACTION_PROTOCOL", "ALGOGRAPH_NODE_TYPES", "ALGOGRAPH_MAP",
    "relation_matrix", "layers_summary",
    "GENERATION_CLASSES", "DECISION_LINKS", "REPRO_LINKS", "NARRATIVE_LINKS",
    "GENERATION_PHASES", "RUBRIC_AXES", "FIDELITY", "POLARITY", "ALLOWED_WORDING",
    "generation_relations", "generation_summary",
    "GROUPS", "CHAINS", "TENTACLE_SPECS", "STAGES", "Chain", "ChainStep",
    "project_chains", "render_chain_bundle", "extractable_classes",
    "chains_summary", "V3_CLASSES", "V3_RELATIONS", "ROOT_FAMILIES",
    # V1 兼容
    "CONCEPT_SPECS", "DIMENSIONS", "RELATION_DOMAIN_RANGE", "default_registry",
    "ALGO_KEYWORDS", "DOMAIN_KEYWORDS", "keyword_stats",
    "CONCEPT_SEMANTICS", "RELATION_SEMANTICS", "INFERENCE_RULES", "TASK_PROTOCOLS",
    "build_bundle", "bundle_summary", "context_pack",
    "DOMAIN_NAMES", "ALGO_NAMES", "classify", "classify_with_evidence",
]
