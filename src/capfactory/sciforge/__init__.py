"""SciForge 桥接层：把「门即代码」的判定与两类研究任务接入知识图谱。

来源：``/home/zengshuxin/xKG-main/SciForge-OSS-master``
复制了 7 个纯 Markdown 契约到 ``skills/``，并把 kernel 的确定性判定逻辑
适配到 ``contracts.py``（纯标准库，零第三方依赖）。

用法::

    from capfactory.sciforge import task_a, task_b, run_golden
    run_golden()                       # 18 项好坏双路回归
    task_a(graph)                      # 图谱缺口 → 新算法方向
    task_b(md_path=..., code_dir=...)  # 缺代码论文 → 拆解 + 复现验证骨架
"""

from __future__ import annotations

from .contracts import (
    VERDICT_STATES, verdict, validate_verdict,
    LADDER_STATES, decide, relative_gain, is_improvement, validate_ladder,
    gap_gate, method_code_parity, claimed_tokens,
    record_node, verify_anchors, sha256_file, sha256_text,
)
from .golden import run_golden, GOOD_GAP, BAD_GAP
from .tasks import (task_a, task_b, graph_gaps, gap_report_text,
                    propose_directions, propose_directions_llm, evaluate_ideas,
                    intake_census, method_registry)
from .polo import PoloClient, UsageMeter, CallRecord, load_config
from .toy_egnn import run_toy, run_toy_ladder
from .paper_types import (PAPER_TYPES, TYPE_FOCUS, classify_paper_type,
                          focus_prompt_block)
from .analyze import (query_templates, reasoning_capabilities,
                      da_distribution, full_report)
from .enrich import (canonicalize_benchmarks, anchor_evidence,
                     problem_layer_report)
from .registry import ARTIFACTS, validate_registry, artifact_path, producers_consumers
from .manuscript import (claim_anchor, verify_claim_anchors, fidelity_gate,
                         figure_spec, figure_audit, blind_review, e2e_smoke,
                         leakage_scrub)
from .flow import GenerationFlow, FlowState
from .reprogen import (INVARIANTS, pick_invariant, generate_code, audit_repo,
                       unsafe_imports)
from .reproflow import ReproductionFlow
from .tentacle import run_tentacles
from .blocks import (screen_headings, rule_screen, build_blocks, BlockStore,
                     build_main_chain)
# 旧抽取实现（deepdive / stage_extract / paper_core）不再从包级导出。
# 它们只作为历史测试与旧 /extraction 页面的兼容层保留；
# 新链路唯一入口：capfactory.semantic.extraction.runner.run_extraction
# （或 capfactory.sciforge.core 的 run_extraction / apply_all / refresh_all）。
from .sources import (build_sources, resolve_sources, CSV_PATHS as SOURCE_CSV_PATHS)
from .pipeline import run_pipeline
from .llm_router import (LLMRouter, output_budget, count_tokens,
                         STAGE_CAPS, MAX_MODEL_LEN)
from .multistep_codegen import (build_source as multistep_source,
                                normalize_steps, generate_multistep_code)
from .repro_readiness import (assess as assess_repro_readiness,
                              load_extraction, to_modules, symbol_coverage)
from .citations import (parse_references, find_root_refs, PaperIndex,
                        load_paper_index, build_citation_layer,
                        resolve_pending_sources, deep_dive_targets,
                        CSV_OUT as UNKNOWN_CITATIONS_CSV)
from .intake import (TBoxManifest, ABoxCensus, IntakeReport,
                     compile_tbox, census_abox, reasoning_readiness,
                     downstream_budget, run_intake, render_intake)

__all__ = [
    "VERDICT_STATES", "verdict", "validate_verdict",
    "LADDER_STATES", "decide", "relative_gain", "is_improvement", "validate_ladder",
    "gap_gate", "method_code_parity", "claimed_tokens",
    "record_node", "verify_anchors", "sha256_file", "sha256_text",
    "run_golden", "GOOD_GAP", "BAD_GAP",
    "task_a", "task_b", "graph_gaps", "gap_report_text",
    "propose_directions", "propose_directions_llm", "evaluate_ideas",
    "intake_census", "method_registry",
    "PoloClient", "UsageMeter", "CallRecord", "load_config",
    "run_toy", "run_toy_ladder",
    "PAPER_TYPES", "TYPE_FOCUS", "classify_paper_type", "focus_prompt_block",
    "query_templates", "reasoning_capabilities", "da_distribution", "full_report",
    "canonicalize_benchmarks", "anchor_evidence", "problem_layer_report",
    "ARTIFACTS", "validate_registry", "artifact_path", "producers_consumers",
    "claim_anchor", "verify_claim_anchors", "fidelity_gate", "figure_spec",
    "figure_audit", "blind_review", "e2e_smoke", "leakage_scrub",
    "GenerationFlow", "FlowState",
    "INVARIANTS", "pick_invariant", "generate_code", "audit_repo",
    "unsafe_imports", "ReproductionFlow",
    "TBoxManifest", "ABoxCensus", "IntakeReport", "compile_tbox",
    "census_abox", "reasoning_readiness", "downstream_budget",
    "run_intake", "render_intake", "run_tentacles",
    "parse_references", "find_root_refs", "PaperIndex", "load_paper_index",
    "build_citation_layer", "resolve_pending_sources", "deep_dive_targets",
    "UNKNOWN_CITATIONS_CSV",
    "screen_headings", "rule_screen", "build_blocks", "BlockStore",
    "build_main_chain", "build_sources", "resolve_sources", "SOURCE_CSV_PATHS",
    "run_pipeline", "LLMRouter", "output_budget", "count_tokens",
    "STAGE_CAPS", "MAX_MODEL_LEN", "assess_repro_readiness",
    "load_extraction", "to_modules", "symbol_coverage",
    "multistep_source", "normalize_steps", "generate_multistep_code",
]
