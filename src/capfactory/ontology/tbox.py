"""TBox 单一权威入口（标准化后的唯一判定口径）。

历史上 TBox 有 4 套口径（V2 17/17、V3 5/30、layers、generation 合并后 102 关系），
各处自行实现 domain/range 判定导致不一致。此后**所有运行时判定只走本模块**：
  - ``authoritative_relations()``  = ``library._all_relations()``（当前 102）
  - ``authoritative_classes()``    = ``default_library().classes``
  - ``check_domain_range()``       = 统一的复合 domain（``A|B``）判定
  - ``snapshot()``                 = 版本/计数/指纹，写进 Stage3 Manifest

兼容：``model.V2_*`` / ``schema_v3.V3_*`` / ``layers.layer_relations()`` 等定义源
仍保留，供历史代码读取；但**不得再自行实现 TBox 判定**。
"""
from __future__ import annotations
import hashlib, json
from typing import Any, Dict, Optional, Tuple

TBOX_VERSION = "v3.2-105"

# ---- 第二档：reserved 分组（不删定义，仅标记「当前不产生实例」）----
# 数据来源：capfactory/md/TBOX_INVENTORY.md 实测（零节点类 30 / 零使用关系 87）
RESERVED_CLASSES = frozenset([
    "AlgorithmComposition",
    "AlgorithmFamily",
    "CapabilityClaim",
    "CausalGraph",
    "CausalNode",
    "ClaimAnchor",
    "CodeGenerationTask",
    "CodeModule",
    "CompileReport",
    "DataForm",
    "Domain",
    "EvaluationRun",
    "EvaluationTool",
    "ExperimentNode",
    "Figure",
    "Formula",
    "GroundingAlignment",
    "Hypothesis",
    "ManuscriptSection",
    "MethodApplication",
    "MethodLock",
    "NarrativeConstraint",
    "Proposal",
    "ReproductionResult",
    "ResearchObject",
    "ReviewVerdict",
    "RunPhase",
    "Section",
    "StaticCheck",
    "Tool"
])
RESERVED_RELATIONS = frozenset([
    "ABOUT_METHOD",
    "ABOUT_SUBJECT",
    "ADDRESSED_BY",
    "ALIGNED_BY",
    "ANCHORED_TO",
    "ANCHORS_GAP",
    "APPLIED_ON",
    "APPLIES_TO",
    "ASSERTS",
    "BELONGS_TO",
    "BENCHMARK_FOR",
    "BINDS_BENCHMARK",
    "BINDS_EVAL_TOOL",
    "BINDS_TOOL",
    "CALLS",
    "CAUSES",
    "CHECKED_BY",
    "CONSTRAINED_BY",
    "CONSUMES",
    "CONTAINS_MODULE",
    "CORRECTED_BY",
    "CORROBORATES",
    "DECLARES_HYPOTHESIS",
    "DEFINES_FUNCTION",
    "DELTA",
    "DERIVED_FROM",
    "EMBEDS",
    "EMITS",
    "EVALUATES_METHOD",
    "FLOWS_DATA_TO",
    "FLOWS_TO",
    "GATED_BY",
    "GENERATES",
    "GENERATES_MODULE",
    "GOVERNS",
    "GROUNDS",
    "GROUNDS_TO",
    "HAS_BLOCK",
    "HAS_CAUSAL_GRAPH",
    "HAS_CAUSAL_NODE",
    "HAS_COMPOSITION",
    "HAS_FORMULA",
    "HAS_INPUT_FORM",
    "HAS_INPUT_OBJECT",
    "HAS_INPUT_SCHEMA",
    "HAS_MODULE_IMPL",
    "HAS_OUTPUT_FORM",
    "HAS_OUTPUT_OBJECT",
    "HAS_OUTPUT_SCHEMA",
    "HAS_PHASE",
    "HAS_PROPOSAL",
    "HAS_SECTION",
    "HAS_STEP",
    "IMPLEMENTS_ALGORITHM",
    "IMPLEMENTS_METRIC",
    "IMPLEMENTS_STEP",
    "IMPROVED_BY",
    "IN_COMPOSITION",
    "IN_DOMAIN",
    "LEADS_TO",
    "LOCKED_BY",
    "LOOPS_BACK_TO",
    "ON_METRIC",
    "PARENT_OF",
    "PARTICIPATES_IN",
    "PRODUCED_BY",
    "PRODUCES",
    "PRODUCES_OBSERVATION",
    "REALIZED_BY",
    "REALIZES",
    "REFERS_TO",
    "REPLACED_BY",
    "REPLACES",
    "REPORTS_ON",
    "REPORTS_VALUE",
    "RESOLVED_TO",
    "REVIEWS",
    "RUNS_IN",
    "RUNS_ON",
    "SCORED_BY",
    "SITUATED_IN",
    "SOURCED_FROM",
    "SUPPORTS_HYPOTHESIS",
    "TESTS_HYPOTHESIS",
    "USES_ALGO_FAMILY",
    "USES_FIGURE",
    "USES_TOOL"
])


def _lib():
    from .library import default_library, _all_relations
    return default_library(), _all_relations


def authoritative_relations() -> Dict[str, Tuple[str, str, str]]:
    """当前生效的全部关系：{name: (domain, range, source)}。"""
    return _lib()[1]()


def authoritative_classes():
    """当前生效的全部类。"""
    return _lib()[0].classes


def resolve_type(t: str) -> str:
    """类型别名归一到 TBox 类（如 MetricObservation → Observation）。"""
    from .chains import TYPE_ALIASES
    return TYPE_ALIASES.get(str(t or ""), str(t or ""))


def check_domain_range(src_type: str, rel: str, dst_type: str) -> bool:
    """统一 domain/range 判定；先做类型别名归一，再比对复合 domain。

    返回 False 的情况：关系不在词表、domain/range 不匹配。
    """
    src_type, dst_type = resolve_type(src_type), resolve_type(dst_type)
    r = authoritative_relations().get(rel)
    if not r:
        return False

    def ok(spec: str, actual: str) -> bool:
        spec = str(spec or "")
        return (spec in (actual, "*", "Entity") or
                actual in [x.strip() for x in spec.split("|")])
    return ok(r[0], src_type) and ok(r[1], dst_type)


def snapshot() -> Dict[str, Any]:
    """可写进 Manifest 的 TBox 指纹（用于判断装配是否基于同一本体）。"""
    lib, _ = _lib()
    rels = authoritative_relations()
    payload = json.dumps({"classes": sorted(lib.classes),
                          "relations": {k: list(v[:2])
                                        for k, v in sorted(rels.items())}},
                         ensure_ascii=False, sort_keys=True)
    return {"version": TBOX_VERSION,
            "n_classes": len(lib.classes),
            "n_relations": len(rels),
            "n_active_classes": len(lib.classes) - len(RESERVED_CLASSES),
            "n_active_relations": len(rels) - len(RESERVED_RELATIONS),
            "n_reserved_classes": len(RESERVED_CLASSES),
            "n_reserved_relations": len(RESERVED_RELATIONS),
            "hash": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
            "sources": ["model.V2", "layers", "generation", "schema_v3.V3"]}


def is_reserved(kind: str, name: str) -> bool:
    """kind: 'class' | 'relation'。reserved 表示当前不产生实例，仅保留定义。"""
    return name in (RESERVED_CLASSES if kind == "class"
                    else RESERVED_RELATIONS)


def active_snapshot() -> Dict[str, Any]:
    """只含在用项（页面与抽取提示词应只引用这个）。"""
    lib, _ = _lib()
    rels = authoritative_relations()
    return {"version": TBOX_VERSION,
            "classes": sorted(c for c in lib.classes
                              if c not in RESERVED_CLASSES),
            "relations": {k: list(v[:2]) for k, v in sorted(rels.items())
                          if k not in RESERVED_RELATIONS}}


# 能力升级清单：reserved 按「能力链」分组，扩哪条链就从这里移出一组
RESERVED_GROUPS: Dict[str, Dict[str, Any]] = {
    "评测链": {"classes": ["EvaluationRun", "EvaluationTool",
                           "ReproductionResult", "ReviewVerdict",
                           "Hypothesis"],
               "enable_when": "需要记录实跑评测事件与复现结果时",
               "unlocks": ["复现 R6 回填", "多模型盲审"]},
    "生成任务链": {"classes": ["Proposal", "CodeGenerationTask",
                               "StaticCheck", "CompileReport", "MethodLock",
                               "RunPhase", "ClaimAnchor"],
                   "enable_when": "要让系统产出代码/提案并自检时",
                   "unlocks": ["代码生成", "静态检查", "运行阶段追踪"]},
    "叙事链": {"classes": ["ManuscriptSection", "Figure",
                           "NarrativeConstraint", "Section"],
               "enable_when": "要生成论文稿件与图表时",
               "unlocks": ["稿件写作", "图表审计"]},
    "因果链": {"classes": ["CausalGraph", "CausalNode", "ExperimentNode"],
               "enable_when": "要做机理因果分析时",
               "unlocks": ["因果图推理"]},
    "方法细化": {"classes": ["MethodApplication", "AlgorithmComposition",
                             "AlgorithmFamily", "DataForm", "ResearchObject",
                             "Domain", "Tool", "Formula", "CodeModule",
                             "GroundingAlignment", "CapabilityClaim"],
                 "enable_when": "需要更细的方法/对象建模时",
                 "unlocks": ["组合算子", "代价模型", "工具链"]},
}


def reserved_snapshot() -> Dict[str, Any]:
    return {"classes": sorted(RESERVED_CLASSES),
            "relations": sorted(RESERVED_RELATIONS)}


def upgrade_plan() -> Dict[str, Any]:
    """把 reserved 当能力升级清单：扩哪条链就把它从 reserved 移出。"""
    covered = {c for g in RESERVED_GROUPS.values() for c in g["classes"]}
    return {"version": TBOX_VERSION,
            "groups": [{"name": k, **v,
                        "n_classes": len(v["classes"]),
                        "currently_reserved": all(
                            c in RESERVED_CLASSES for c in v["classes"])}
                       for k, v in RESERVED_GROUPS.items()],
            "ungrouped": sorted(RESERVED_CLASSES - covered),
            "n_reserved_classes": len(RESERVED_CLASSES),
            "n_reserved_relations": len(RESERVED_RELATIONS)}


def compile_manifest() -> Dict[str, Any]:
    """延迟包装 intake.compile_tbox，避免 ontology → sciforge 循环依赖。"""
    from ..sciforge.intake import compile_tbox
    m = compile_tbox()
    return {"n_classes": m.n_classes, "n_relations": m.n_relations,
            "issues": list(getattr(m, "issues", None) or []),
            "fingerprint": getattr(m, "fingerprint",
                                   getattr(m, "tbox_hash", ""))}
