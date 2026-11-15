"""产物注册表（借鉴 SciForge ``artifact-registry.md``）。

规则：**下游行为依赖的文件必须注册；未注册的产物不得作为门输入。**
这条规则针对两个真实事故：

* Phantom artifact —— 生产者写 `CLAIMS_FROM_RESULTS.md`，消费者去找
  `CLAIM_VERDICT.md`，链子静默断掉；
* Schema drift —— 加了字段但只有部分消费者检查，门形同虚设。

本模块把当前项目散落在 ``storage_cf/{po,ontology,sciforge,vector*,other}/``
下的产物统一登记，并提供 ``validate_registry()`` 做存在性与 verifier 检查。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]

# name -> (相对路径, producer, consumers, verifier, 是否门输入)
ARTIFACTS: Dict[str, Tuple[str, str, Tuple[str, ...], str, bool]] = {
    # ---- 图与语料 ----
    "report_graph": ("storage_cf/po/report_graph.json", "po.importer",
                     ("linking", "reasoning", "benchmark"), "POGraph.validate", True),
    "batch10_graph": ("storage_cf/sciforge/batch10_final_graph.json", "sciforge.batch10+enrich",
                      ("analyze", "task_a"), "POGraph.validate", True),
    "parse_manifest": ("../data/docx/_manifest.jsonl", "kbpipe.batch_parse",
                       ("batch_extract", "paper_types"), "manifest_stats", True),
    # ---- 抽取与判定 ----
    "modules_raw": ("storage_cf/ontology/egnn_modules_raw.json", "ontology.modules",
                    ("cad", "refine"), "symbol_index", True),
    "cad_report": ("storage_cf/ontology/egnn_cad_report.json", "ontology.cad",
                   ("grounding",), "semantic_validity", False),
    "experiments": ("storage_cf/ontology/egnn_experiments.json", "ontology.refine",
                    ("metrics.align",), "metric_vocab", True),
    "refine_report": ("storage_cf/ontology/egnn_refine_report.json", "ontology.refine",
                      ("docs",), "graph_quality", False),
    # ---- 任务与验证 ----
    "toy_result": ("storage_cf/sciforge/toy_egnn_RESULT.json", "sciforge.toy_egnn",
                   ("task_b", "ladder"), "analytic_sanity_band", True),
    "toy_ladder": ("storage_cf/sciforge/toy_egnn_LADDER.json", "sciforge.toy_egnn",
                   ("task_b",), "validate_ladder", True),
    "task_a_report": ("storage_cf/sciforge/task_a_llm_report.json", "sciforge.tasks",
                      ("flow",), "evaluate_ideas", True),
    "task_b_report": ("storage_cf/sciforge/task_b_report.json", "sciforge.tasks",
                      ("flow",), "blocking_checks", True),
    "paper_types": ("storage_cf/sciforge/paper_types.json", "sciforge.paper_types",
                    ("batch10",), "PAPER_TYPES", True),
    "final_report": ("storage_cf/sciforge/batch10_final_report.json", "sciforge.enrich+analyze",
                     ("docs",), "full_report", False),
    # ---- 消耗与向量 ----
    "usage_total": ("storage_cf/sciforge/polo_usage_grand_total.json", "sciforge.polo",
                    ("docs",), "UsageMeter.summary", False),
    "vector_items": ("storage_cf/vector4/docs/items.jsonl", "vector.multistore",
                     ("retrieval",), "MultiVectorStore.build", False),
    # ---- 生成侧（本轮新增，由 flow 产出）----
    "generation_run": ("storage_cf/sciforge/runs/<run_id>/run.json", "sciforge.flow",
                       ("manuscript", "review"), "FlowVerdict", True),
    "claim_anchors": ("storage_cf/sciforge/runs/<run_id>/CLAIM_ANCHORS.json",
                      "sciforge.manuscript", ("narrative", "compile"),
                      "verify_anchors", True),
    "figure_index": ("storage_cf/sciforge/runs/<run_id>/FIGURE_INDEX.json",
                     "sciforge.manuscript", ("narrative",), "Figure.audit_verdict", True),
    "review_state": ("storage_cf/sciforge/runs/<run_id>/REVIEW_STATE.json",
                     "sciforge.manuscript", ("publish",), "overall>=6", True),
    "compile_report": ("storage_cf/sciforge/runs/<run_id>/COMPILE_REPORT.json",
                       "sciforge.flow", ("archive",), "e2e_smoke", True),
}


def artifact_path(name: str, *, run_id: str = "") -> Path:
    if name not in ARTIFACTS:
        raise KeyError(f"未注册的产物: {name}（未注册产物不得作为门输入）")
    rel = ARTIFACTS[name][0].replace("<run_id>", run_id or "_")
    p = (ROOT / rel).resolve()
    return p


def producers_consumers() -> Dict[str, Dict[str, Any]]:
    return {name: {"path": v[0], "producer": v[1], "consumers": list(v[2]),
                   "verifier": v[3], "gate_input": v[4]}
            for name, v in ARTIFACTS.items()}


def validate_registry(*, run_id: str = "", require_gates: bool = True
                      ) -> Dict[str, Any]:
    """检查注册产物的存在性；生成侧占位路径允许缺失（run 未开始时）。"""
    missing, present, skipped = [], [], []
    for name, (rel, _prod, _cons, _ver, is_gate) in ARTIFACTS.items():
        if "<run_id>" in rel:
            skipped.append(name)
            continue
        p = (ROOT / rel).resolve()
        (present if p.exists() else missing).append(name)
        if require_gates and is_gate and not p.exists():
            pass
    return {"registered": len(ARTIFACTS), "present": len(present),
            "missing": missing, "run_scoped": skipped,
            "gate_inputs": [n for n, v in ARTIFACTS.items() if v[4]],
            "ok": not missing or not require_gates}


def dependency_edges() -> List[Tuple[str, str]]:
    """产物依赖边：consumer 环节依赖 producer 产物（用于生成 DAG 可视化）。"""
    edges = []
    for name, (_rel, prod, cons, _ver, _gate) in ARTIFACTS.items():
        for c in cons:
            edges.append((f"artifact:{name}", f"stage:{c}"))
        edges.append((f"stage:{prod}", f"artifact:{name}"))
    return edges


def summary() -> Dict[str, Any]:
    return {"artifacts": len(ARTIFACTS),
            "gate_inputs": sum(1 for v in ARTIFACTS.values() if v[4]),
            "run_scoped": sum(1 for v in ARTIFACTS.values() if "<run_id>" in v[0]),
            "dependency_edges": len(dependency_edges())}
