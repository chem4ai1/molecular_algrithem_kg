"""复现应用层：规格编译工作目录（GGR / P0-1 ~ P0-4）。

与 ``capfactory/sciforge/repro/`` 的分工：

==============================  =======================================
本目录 (reprospec)              sciforge/repro
==============================  =======================================
**规格层**：关系真相源、         **执行层**：R0–R6 DAG、门、事件重放
ReproSpec / SAU 契约、编译器、
运行时应用节点、逐 SAU 判定
只读图、确定性、零 LLM          运行时状态机
==============================  =======================================

设计依据：``capfactory/md/REPRODUCTION_APPLICATION_BLUEPRINT.md`` §3–§6。

    from capfactory.reprospec import compile_reprospec, evaluate_sau

    spec = compile_reprospec(arxiv_id="2411.06608")
    report = evaluate_sau(spec, graph)          # dry 也能判静态证据
    report.sau_score, report.coverage, report.drift_rate
"""

from .contract import SAU, SAU_KINDS, ReproSpec
from .compiler import compile_reprospec
from .relations import (ALL_CANONICAL, APP_RELATIONS, LEGACY_ALIASES,
                        REPRO_APP_RELATIONS, SEMANTIC_RELATIONS,
                        canonicalize_reads, resolve_relation,
                        validate_phasegraph)
from .verdict import (SAUReport, evaluate_sau, sau_drift_acceptable)
from .application import (EFFECTIVE_CLASSES, EFFECTIVE_RELATIONS,
                          REPRO_APP_CLASSES, materialize_runtime_nodes,
                          reserved_status, snapshot as application_snapshot,
                          validate_repro_edge)
from .executor import ExecutionResult, execute_repro, build_repro_script
from .ladder import LadderResult, decide, run_ladder
from .probe import (lineage_enrich, lineage_evidence, shape_probe,
                    write_lineage_evidence, write_probes)
from .scoring import (FinalEvaluation, align_rubric, claim_anchors,
                      finalize, perf_gap)
from .normalize import (GROUNDING_RULES, NormalizationResult,
                        grounding_snapshot, normalize_for_repro)
from .minibatch import (build_minibatch_script, resolve_forms,
                        write_runtime_probe)
from .train import (build_train_plan, probe_environment,
                    write_train_feasibility)

__all__ = [
    # P0-1
    "SEMANTIC_RELATIONS", "APP_RELATIONS", "REPRO_APP_RELATIONS",
    "ALL_CANONICAL", "LEGACY_ALIASES", "resolve_relation",
    "canonicalize_reads", "validate_phasegraph",
    # P0-2
    "compile_reprospec", "ReproSpec", "SAU", "SAU_KINDS",
    # P0-3
    "REPRO_APP_CLASSES", "EFFECTIVE_CLASSES", "EFFECTIVE_RELATIONS",
    "materialize_runtime_nodes", "validate_repro_edge",
    "reserved_status", "application_snapshot",
    # P0-4
    "evaluate_sau", "SAUReport", "sau_drift_acceptable",
    # P1-5 / P1-6 / P1-7
    "execute_repro", "ExecutionResult", "build_repro_script",
    "run_ladder", "decide", "LadderResult",
    "shape_probe", "lineage_enrich", "write_probes",
    # P2-8
    "finalize", "FinalEvaluation", "claim_anchors", "align_rubric", "perf_gap",
    # P3-1 / P3-2 / P3-3 / full
    "normalize_for_repro", "NormalizationResult", "GROUNDING_RULES",
    "grounding_snapshot", "write_runtime_probe", "build_minibatch_script",
    "resolve_forms", "lineage_evidence", "write_lineage_evidence",
    "probe_environment", "build_train_plan", "write_train_feasibility",
]
