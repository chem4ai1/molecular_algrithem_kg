"""复现门系统（SciForge 风格）：阶段边界以代码检查，verdict 严格三档。"""
from __future__ import annotations
from typing import Any, Dict

from .contract import GateResult


def paper_core_present(plan, phase="R0"):
    g = GateResult(phase)
    if not plan.research_problem or plan.research_problem.startswith("unknown"):
        g.reasons.append("缺 research_problem")
    if not plan.domain or plan.domain == "unknown":
        g.reasons.append("缺 domain")
    g.evidence = {"paper_id": plan.paper_id, "domain": plan.domain,
                  "algorithm_family": plan.algorithm_family}
    g.verdict = "PASS" if not g.reasons else "BLOCKED"
    return g


def method_grounded(plan, phase="R1"):
    g = GateResult(phase)
    if not plan.methods:
        g.reasons.append("无 PROPOSES_METHOD 关系")
    else:
        for m in plan.methods:
            if not m.get("mechanism") or m["mechanism"] == "unknown":
                g.reasons.append(f"{m['name']} 缺机理")
    g.evidence = {"n_methods": len(plan.methods),
                  "task_types": [m.get("task_type") for m in plan.methods]}
    g.verdict = "PASS" if not g.reasons else ("PARTIAL" if plan.methods
                                              else "BLOCKED")
    return g


def code_located(plan, phase="R2"):
    g = GateResult(phase)
    if not plan.code:
        g.reasons.append("算法→代码关系缺失")
    g.evidence = {"n_code_links": len(plan.code),
                  "sample": [c["target_label"] for c in plan.code[:3]]}
    g.verdict = "PASS" if not g.reasons else "BLOCKED"
    return g


def data_bound(plan, phase="R3"):
    g = GateResult(phase)
    usable = [d for d in plan.data if d.get("is_evaluation", True)]
    if not usable:
        g.reasons.append("无可用评测基准")
    for d in usable:
        if not d.get("input_form") or not d.get("output_form"):
            g.reasons.append(f"{d['name']} 缺输入/输出形式")
    g.evidence = {"n_benchmarks": len(usable),
                  "source_papers": sum(len(d.get("source_papers") or [])
                                       for d in usable)}
    g.verdict = "PASS" if not g.reasons else ("PARTIAL" if usable
                                              else "BLOCKED")
    return g


def metrics_comparable(plan, phase="R4"):
    g = GateResult(phase)
    if not plan.metrics:
        g.reasons.append("无指标")
    for m in plan.metrics:
        if m.get("direction") not in ("min", "max"):
            g.reasons.append(f"{m['name']} 方向未知")
        if m.get("direction_source") == "heuristic":
            if f"metric {m['name']} 方向为启发式，需人工确认" not in g.reasons:
                g.reasons.append(f"metric {m['name']} 方向为启发式，需人工确认")
    hard = [r for r in g.reasons if "启发式" not in r]
    g.evidence = {"n_metrics": len(plan.metrics),
                  "sota_baselines": len(plan.sota_baselines)}
    g.verdict = "BLOCKED" if hard else ("PARTIAL" if g.reasons else "PASS")
    return g


def verdicts_valid(state, phase="R5"):
    g = GateResult(phase)
    bad = [k for k, v in (state.verdicts or {}).items()
           if v not in ("PASS", "PARTIAL", "BLOCKED")]
    if bad:
        g.reasons.append("非法 verdict: " + ",".join(bad))
    g.evidence = {"verdicts": state.verdicts}
    g.verdict = "PASS" if not bad else "BLOCKED"
    return g


def reproduction_close(results, phase="R6"):
    """实跑值 vs 论文 SOTA 基线；无实跑值时诚实标 BLOCKED，不编造通过。"""
    g = GateResult(phase)
    rows = (results or {}).get("rows") or []
    if not rows:
        g.reasons.append("无实跑结果（dry 模式不产生数值）")
        g.evidence = {"n_rows": 0}
        g.verdict = "BLOCKED"
        return g
    dev = []
    for r in rows:
        base, val = r.get("baseline"), r.get("value")
        if base in (None, "") or val is None:
            dev.append(f"{r.get('metric')}:缺基线或值")
            continue
        try:
            delta = abs(float(val) - float(base))
            if delta > 0.05 * max(abs(float(base)), 1e-9):
                dev.append(f"{r.get('metric')}:偏差 {delta:.4g}")
        except (TypeError, ValueError):
            dev.append(f"{r.get('metric')}:非数值")
    g.reasons = dev
    g.evidence = {"n_rows": len(rows), "deviations": dev[:10]}
    g.verdict = "PASS" if not dev else "PARTIAL"
    return g


GATES = {"paper_core_present": paper_core_present,
         "method_grounded": method_grounded,
         "code_located": code_located,
         "data_bound": data_bound,
         "metrics_comparable": metrics_comparable,
         "verdicts_valid": verdicts_valid,
         "reproduction_close": reproduction_close}
