"""复现执行器：按 phasegraph 走 7 阶段门，events 记录，可恢复。

模式
----
* ``dry``（默认）：只装配与静态判定；R6 因无实跑值诚实 BLOCKED。
  **该行为被 ``tests/test_p1_repro.py:150`` 锁定，不得放宽。**
* ``lite`` / ``full``：P1-5 起真跑 ``REPRO_SCRIPT.py``（子进程隔离、
  EDIT 定点修复、events 重放），产出实跑数值后 R6 才可能非 BLOCKED。

产物（run 目录）
--------------
dry : REPRO_PLAN / REPRO_SPEC / SAU_LIST / SAU_VERDICTS /
      app_repro_runtime / REPRO_VERDICTS / REPRO_REPORT / RUNSTATE
lite: 上述 + REPRO_SCRIPT / raw_results / RESULTS_FOR_GATES /
      S2_LADDER / SHAPE_PROBE / LINEAGE / ALIGN_RUBRIC /
      CLAIM_ANCHORS / FINAL_EVALUATION / EDIT_LOG（有修复时）
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .contract import RunState
from .planner import build_plan
from .gates import GATES
from .state import EventLog, replay, save_state

PHASEGRAPH = Path(__file__).parent / "phasegraph.json"


def _prepare_spec(graph: Any, paper_id: str) -> Any:
    """编译 ReproSpec 并落盘（dry/lite 都会做，规格层无副作用）。"""
    from capfactory.reprospec import compile_reprospec
    spec = compile_reprospec(graph, paper_id=paper_id)
    return spec


def _auxiliary(graph: Any, paper_id: str, d: Path, run_id: str,
               effort: str, results: Optional[Dict], spec: Any,
               sau_report: Any, ex: Any, ladder: Any) -> Dict[str, Any]:
    """P0-3/P0-4 + P1-7 + P2-8：写运行时图、探针、锚、最终评估。"""
    from capfactory.reprospec.application import materialize_runtime_nodes
    from capfactory.reprospec.probe import write_probes
    from capfactory.reprospec.scoring import (claim_anchors, finalize)
    try:
        sau_report.save(d)
        runtime = materialize_runtime_nodes(
            spec, sau_report, run_id=run_id, graph=graph, out_dir=d,
            results=results)
        probes = write_probes(spec, graph, d)
        # P3-2 / P3-3：真实 mini-batch 实测与 lineage 证据分级。
        # 独立 try，探针失败不得拖垮主门链或伪造成 overall 通过。
        mb: Dict[str, Any] = {}
        lin: Dict[str, Any] = {}
        if effort != "dry":
            try:
                from capfactory.reprospec.minibatch import write_runtime_probe
                from capfactory.reprospec.probe import write_lineage_evidence
                mb = write_runtime_probe(spec, d)
                lin = write_lineage_evidence(spec, graph, d)
            except Exception as exc:  # noqa: BLE001
                mb = {"ok": False, "warnings": [f"{type(exc).__name__}: {exc}"]}
        # 只有真跑成功才允许生成锚与最终评估：执行失败时不得产出
        # 「anchor_integrity=True」这类误导性证据（防作弊条款 §5-2）
        exec_ok = bool(ex is not None and getattr(ex, "ok", False))
        anchors = claim_anchors(spec, ex, d) if exec_ok else {}
        fe = finalize(spec, sau_report, ex, ladder, anchors,
                      results or {}, effort=effort, out_dir=d) \
            if exec_ok else None
        return {
            "available": True,
            "n_sau": sau_report.n_total,
            "n_decidable": sau_report.n_decidable,
            "sau_score": sau_report.sau_score,
            "coverage": sau_report.coverage,
            "drift_rate": sau_report.drift_rate,
            "by_drift": sau_report.by_drift,
            "spec_hash": spec.spec_hash,
            "runtime_classes": runtime["by_type"],
            "n_relations": runtime["n_assertions"],
            "probes": probes,
            "mini_batch": {k: mb.get(k) for k in
                           ("ok", "n_probes", "n_runtime_verified",
                            "n_inherited_forms", "n_unknown_remaining",
                            "warnings")},
            "lineage_evidence": lin,
            "anchors": {"code_sha": anchors.get("code_sha", ""),
                        "outputs_sha": anchors.get("outputs_sha", ""),
                        "double_run_equal": anchors.get("double_run_equal")},
            "evaluation": fe.to_dict() if fe else None,
            "files": ["SAU_VERDICTS.json", "app_repro_runtime.json",
                      "SHAPE_PROBE.json", "LINEAGE.json",
                      "MINIBATCH_PROBE.json", "LINEAGE_EVIDENCE.json"],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False,
                "error": f"{type(exc).__name__}: {exc}",
                "note": "规格层异常不影响主门链"}


def run_repro(graph: Any, paper_id: str, *, ws: Any = None,
              effort: str = "dry", results: Optional[Dict] = None
              ) -> Dict[str, Any]:
    base = Path("storage_cf/sciforge/repro_runs")
    d = Path(ws) if ws else (base / paper_id.split(":")[-1])
    d.mkdir(parents=True, exist_ok=True)
    phases = json.loads(PHASEGRAPH.read_text(encoding="utf-8"))
    limits = phases["effort_limits"].get(effort,
                                         phases["effort_limits"]["dry"])
    plan = build_plan(graph, paper_id)
    (d / "REPRO_PLAN.json").write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    log, state = EventLog(d), RunState(
        run_id=("repro_" + plan.arxiv_id), paper_id=paper_id,
        budget=limits)
    log.append({"type": "start", "paper_id": paper_id,
                "inputs_sha": plan.inputs_sha, "effort": effort})

    # ---- 规格层（只读图、零 LLM）--------------------------------------
    spec = None
    try:
        spec = _prepare_spec(graph, paper_id)
        spec.save(d)
    except Exception as exc:  # noqa: BLE001
        log.append({"type": "spec_error", "error": str(exc)})

    # ---- P1-5：lite/full 真跑 ------------------------------------------
    ex, ladder = None, None
    if effort != "dry" and limits.get("allow_execution") and spec is not None:
        from capfactory.reprospec.executor import execute_repro
        from capfactory.reprospec.ladder import run_ladder
        ex = execute_repro(spec, graph, out_dir=d, effort=effort,
                           event_log=log)
        ladder = run_ladder(ex, out_dir=d)
        if ex.ok and results is None:
            results = ex.results
        log.append({"type": "execution", "ok": ex.ok,
                    "status": ex.status, "debug_tries": ex.debug_tries,
                    "ladder": ladder.verdict})

    # ---- P0-4：逐 SAU 判定（lite 用实跑值回填 numeric）----------------
    sau_report = None
    if spec is not None:
        from capfactory.reprospec.verdict import evaluate_sau
        sau_report = evaluate_sau(spec, graph, results=results,
                                  effort=effort)

    # ---- 7 阶段门 -------------------------------------------------------
    verdicts: Dict[str, Any] = {}
    for p in phases["phases"]:
        pid, gate_name = p["id"], p["gate"]
        fn = GATES.get(gate_name)
        if fn is None:
            verdicts[pid] = {"verdict": "BLOCKED",
                             "reasons": [f"unknown_gate:{gate_name}"]}
            continue
        if pid == "R5":
            r = fn(state)
            if ex is not None and not ex.ok:
                r.verdict = "BLOCKED"
                r.reasons.append("lite 执行失败或调试耗尽")
            elif ladder is not None and ladder.verdict == "BLOCKED":
                r.verdict = "BLOCKED"
                r.reasons.append("S2 ladder BLOCKED")
        elif pid == "R6":
            r = fn(results)
            # P2-9：语义门只在真跑成功时参与，dry 不碰
            if (r.verdict == "PASS" and ex is not None and ex.ok
                    and sau_report is not None):
                from capfactory.reprospec.verdict import sau_drift_acceptable
                sem = sau_drift_acceptable(sau_report)
                if sem["verdict"] != "PASS":
                    r.verdict = "PARTIAL"
                    r.reasons.extend(sem["reasons"])
        else:
            r = fn(plan)
        verdicts[pid] = r.to_dict()
        state.verdicts[pid] = r.verdict
        state.phase = pid
        state.next_action = p.get("next") or "done"
        log.append({"type": "phase_done", "phase": pid,
                    "verdict": r.verdict, "next": state.next_action,
                    "gate": gate_name, "reasons": r.reasons})

    sau = _auxiliary(graph, paper_id, d, state.run_id, effort, results,
                     spec, sau_report, ex, ladder) \
        if (spec is not None and sau_report is not None) else \
        {"available": False, "error": "spec_or_sau_report_missing"}

    blocked = [k for k, v in verdicts.items() if v["verdict"] == "BLOCKED"]
    partial = [k for k, v in verdicts.items() if v["verdict"] == "PARTIAL"]
    overall = "BLOCKED" if blocked else ("PARTIAL" if partial else "PASS")
    state.status = "done" if overall != "BLOCKED" else "blocked"
    save_state(d, state)
    rep = {"paper_id": paper_id, "arxiv_id": plan.arxiv_id,
           "inputs_sha": plan.inputs_sha, "effort": effort,
           "overall": overall, "verdicts": verdicts,
           "blocked": blocked, "partial": partial,
           "n_methods": len(plan.methods), "n_code": len(plan.code),
           "n_data": len(plan.data), "n_metrics": len(plan.metrics),
           "gaps": plan.gaps, "warnings": plan.warnings,
           "sau": sau,
           "execution": {"ok": bool(ex and ex.ok),
                         "status": ex.status if ex else "dry_skipped",
                         "debug_tries": ex.debug_tries if ex else 0,
                         "duration_s": ex.duration_s if ex else 0.0,
                         "n_rows": len((ex.results.get("rows") if ex else None)
                                       or [])} if ex else None,
           "ladder": ladder.to_dict() if ladder else None,
           "workspace": str(d)}
    (d / "REPRO_VERDICTS.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")

    lines = [
        "# 代码复现报告 · " + plan.arxiv_id, "",
        "- 研究问题：" + plan.research_problem[:120],
        "- 领域：" + plan.domain + " / 算法族：" + plan.algorithm_family,
        "- 模式：" + effort + "　overall: **" + overall + "**",
        "- 方法 " + str(len(plan.methods)) + " / 代码 " +
        str(len(plan.code)) + " / 数据 " + str(len(plan.data)) +
        " / 指标 " + str(len(plan.metrics)),
    ]
    if sau.get("available"):
        lines.append(
            "- SAU 判定：" + f"{sau['n_sau']} 条，score {sau['sau_score']}，"
            f"coverage {sau['coverage']}，drift {sau['drift_rate']}")
        if sau.get("evaluation"):
            e = sau["evaluation"]
            lines.append(
                "- 最终评估：**" + e["overall"] + "**　Exec Rate "
                + str(e["exec_rate"]) + " / Perf Gap " + str(e["perf_gap"])
                + " / Align_mixed " + str(e["align_mixed"]))
            for reason in e["reasons"]:
                lines.append("  - 降级原因：" + reason)
            lines.append("- 未验证范围：" + "；".join(e["out_of_scope"]))
    else:
        lines.append("- SAU 判定：不可用（" + str(sau.get("error")) + "）")
    if ex is not None:
        lines.append(
            "- 执行：REPRO_SCRIPT.py " + ("成功" if ex.ok else "失败") +
            f" / debug_tries {ex.debug_tries} / {ex.duration_s}s" +
            (" / ladder " + ladder.verdict if ladder else ""))
    lines += ["", "| 阶段 | verdict | 原因 |", "|---|---|---|"]
    lines += ["| " + k + " | " + v["verdict"] + " | " +
              "; ".join(v["reasons"])[:80] + " |"
              for k, v in verdicts.items()]
    lines += ["", "dry 模式不执行训练；R6 无实跑值时为 BLOCKED 属预期。"]
    (d / "REPRO_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return rep


def resume_repro(ws: Any) -> Dict[str, Any]:
    """崩溃恢复：events.ndjson 是 durable truth，重放得到 RUNSTATE。"""
    d = Path(ws)
    st = RunState(run_id=d.name, paper_id="")
    if (d / "RUNSTATE.json").exists():
        raw = json.loads((d / "RUNSTATE.json").read_text(encoding="utf-8"))
        st = RunState(**{k: v for k, v in raw.items()
                         if k in RunState.__dataclass_fields__})
    st = replay(EventLog(d), st)
    save_state(d, st)
    return {"resumed": True, "phase": st.phase,
            "next_action": st.next_action, "status": st.status,
            "verdicts": st.verdicts}
