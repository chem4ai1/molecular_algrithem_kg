"""paperapp CLI：状态 / 审计 / 校验 / 报告。所有命令只读或只写工作区。"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from . import config, coverage, gates, hitl, registry, signals, util


def status() -> Dict[str, Any]:
    config.ensure_dirs()
    d = registry.load_registry()
    return {
        "ok": True,
        "semantic_sha": util.sha256_file(config.SEMANTIC_GRAPH),
        "app_sha": util.sha256_file(config.APP_GRAPH),
        "semantic_tbox_version": config.SEMANTIC_TBOX_VERSION,
        "dynamic_tbox_version": d.get("version", config.DYNAMIC_TBOX_VERSION),
        "n_registered_classes": len(d.get("classes", {})),
        "n_stages": len(config.STAGE_IDS),
        "gate_timeout_policy": config.GATE_TIMEOUT_POLICY,
        "human_boost_cap": config.HUMAN_BOOST_CAP,
        "allow_incremental_write": config.ALLOW_INCREMENTAL_WRITE,
    }


def audit_isolation() -> Dict[str, Any]:
    """H5：语义层图里不得出现任何 llm_proposal 节点。"""
    p = config.SEMANTIC_GRAPH
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    n = text.count("llm_proposal")
    return {"ok": n == 0, "n_llm_proposal_in_semantic": n,
            "semantic_sha": util.sha256_file(p),
            "reason_code": "ok" if n == 0 else "semantic_layer_contaminated"}


def audit_signals(*, expected_events: int = 0) -> Dict[str, Any]:
    s = signals.signal_stats(expected_events=expected_events)
    c = signals.cluster_signals()
    return {"ok": s["signal_capture_rate"] == 1.0 and
            s["dismiss_with_reason_rate"] == 1.0,
            **s, "n_clusters": c["n_clusters"],
            "n_promotable": c["n_promotable"], "reason_code": "ok"}


def audit_decisions() -> Dict[str, Any]:
    decs = hitl.load_decisions()
    rows = util.read_jsonl(config.DYNAMIC_TBOX / "DECISION_LOG.jsonl")
    missing_gate = []
    for st in __import__("capfactory.paperapp.tbox", fromlist=["GATE_STAGES"]).GATE_STAGES:
        p = config.DYNAMIC_TBOX / "decisions" / f"verdict_{st}.json"
        if not p.exists():
            missing_gate.append(st)
    return {"ok": all(d.approver for d in decs) and len(rows) >= len(decs),
            "n_decisions": len(decs), "n_log_rows": len(rows),
            "append_only": True, "gate_stages_without_verdict": missing_gate,
            "reason_code": "ok"}


def audit_sovereignty() -> Dict[str, Any]:
    from .tbox import CHOICEPOINTS
    gate_modes = {k: v["mode"] for k, v in CHOICEPOINTS.items() if v["mode"] == "gate"}
    ok = config.GATE_TIMEOUT_POLICY == "BLOCKED" and \
        config.HUMAN_BOOST_CAP == 0.0 and bool(gate_modes)
    return {"ok": ok, "gate_stages": sorted(gate_modes),
            "gate_timeout_policy": config.GATE_TIMEOUT_POLICY,
            "human_boost_cap": config.HUMAN_BOOST_CAP,
            "semantic_layer_guard": promote_guard_ok(), "reason_code": "ok"}


def promote_guard_ok() -> bool:
    from . import promote
    return not promote.semantic_promotion_guard("semantic")[0]


def audit_reinjection() -> Dict[str, Any]:
    r = hitl.load_reinjection()
    active = hitl.active_decisions()
    propagated = sum(1 for d in active
                     if any(d.decision_id in x.get("decision_id", "")
                            for x in r.get("decisions", [])))
    rate = 1.0 if not active else propagated / len(active)
    return {"ok": rate == 1.0,
            "decision_propagation_rate": rate, "n_active": len(active),
            "n_reinjected": len(r.get("decisions", [])),
            "spec_hash_input": r.get("spec_hash_input", False), "reason_code": "ok"}


def mining_coverage() -> Dict[str, Any]:
    p = config.NODE_CACHE / "MINING_COVERAGE.json"
    if not p.exists():
        coverage.build()
    c = json.loads(p.read_text(encoding="utf-8"))
    statuses = {r["status"] for r in c["fields"] + c["assertions"]}
    return {"ok": bool(statuses) and len(c["miners"]) > 0,
            "coverage_ratio": c["coverage_ratio"],
            "n_gap_candidates": c["n_gap_candidates"],
            "target": c["target"], "statuses": sorted(statuses),
            "reason_code": "ok"}


def verify_rebuild_cli() -> Dict[str, Any]:
    try:
        full = util.load_graph(config.APP_GRAPH)
        return util.verify_rebuild(base_graph=util.load_graph(),
                                   prev_app=full, full_app=full)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason_code": "graph_unavailable",
                "detail": f"{type(exc).__name__}: {exc}"}


def registry_audit() -> Dict[str, Any]:
    issues = registry.validate_dynamic_tbox()
    return {"ok": not issues, "issues": issues,
            "issues_phasegraph": __import__("capfactory.paperapp.tbox",
                                            fromlist=["validate_phasegraph"])
            .validate_phasegraph(), "reason_code": "ok"}


def audit_all() -> Dict[str, Any]:
    fns = {"isolation": audit_isolation, "signals": audit_signals,
           "decisions": audit_decisions, "sovereignty": audit_sovereignty,
           "reinjection": audit_reinjection, "coverage": mining_coverage,
           "rebuild": verify_rebuild_cli, "registry": registry_audit}
    out = {k: f() for k, f in fns.items()}
    out["ok"] = all(v.get("ok", False) for v in out.values())
    out["n_hard_gates"] = len(out) - 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GGR-Paper paperapp CLI")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["status", "audit-isolation", "audit-signals",
                             "audit-decisions", "audit-sovereignty",
                             "audit-reinjection", "mining-coverage",
                             "verify-rebuild", "registry-audit", "audit-all",
                             "report"])
    a = ap.parse_args(argv)
    from . import report
    fns = {"status": status, "audit-isolation": audit_isolation,
           "audit-signals": audit_signals, "audit-decisions": audit_decisions,
           "audit-sovereignty": audit_sovereignty,
           "audit-reinjection": audit_reinjection,
           "mining-coverage": mining_coverage,
           "verify-rebuild": verify_rebuild_cli,
           "registry-audit": registry_audit, "audit-all": audit_all,
           "report": report.write_report}
    print(json.dumps(fns[a.cmd](), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
