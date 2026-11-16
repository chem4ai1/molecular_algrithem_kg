"""S4 增量回写：唯一的 app_generation.json 写入口。

六步：收集 → align/validate/promote → 构造 delta → verify → 加锁写 → 报告。
DRIFT 时 files_written=[]，绝不写图（H2/H8）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from . import (align, config, hitl, nodecache, promote, registry, signals,
               util, validate)
from .schemas import NodeCacheEntry


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_delta(proposals) -> Dict[str, List[Dict[str, Any]]]:
    nodes, assertions = [], []
    for p in proposals:
        cid = p.canonical_id or f"app{p.candidate_class.lower()}:{p.proposal_id[5:]}"
        nodes.append({
            "id": cid, "type": p.candidate_class,
            "label": str(p.attrs.get("value") or p.attrs.get("label") or cid),
            "attrs": {**p.attrs,
                      "layer": "application", "task": config.TASK,
                      "derived_from": p.derived_from,
                      "miner": p.miner, "run_id": p.run_id,
                      "origin": p.origin},
            "attribution": "llm_proposal",
            "evidence_ids": list(p.evidence_ids),
        })
        for src in (p.derived_from or []):
            assertions.append({
                "id": "assertion:norm:" + util.sha256_json([cid, src])[7:19],
                "source": cid, "target": src, "relation": "DERIVED_FROM",
                "attribution": "llm_proposal", "evidence_ids": list(p.evidence_ids),
                "properties": {"layer": "application", "task": config.TASK,
                               "miner": p.miner},
            })
    return {"nodes": nodes, "assertions": assertions}


def verify(*, app_path=None, out_dir=None) -> Dict[str, Any]:
    """I2 实际判据：语义层投影未被篡改 + 每个应用节点都有注册项。"""
    ap = Path(app_path or config.APP_GRAPH)
    sem = config.SEMANTIC_GRAPH
    if not ap.exists() or not sem.exists():
        return {"ok": False, "reason_code": "graph_missing"}
    app = json.loads(ap.read_text(encoding="utf-8"))
    sd = json.loads(sem.read_text(encoding="utf-8"))
    sem_nodes = {n["id"]: n for n in sd.get("nodes", [])}
    registered = set()
    ndir = Path(out_dir) / "nodes" if out_dir else config.NODES_DIR
    if ndir.exists():
        for p in ndir.glob("*.json"):
            try:
                registered.add(NodeCacheEntry(**json.loads(
                    p.read_text(encoding="utf-8"))).canonical_id)
            except (ValueError, TypeError, OSError):
                continue
    problems = []
    n_sem, n_app = 0, 0
    for n in app.get("nodes", []):
        layer = (n.get("attrs") or {}).get("layer")
        if layer == "semantic" or n["id"] in sem_nodes:
            n_sem += 1
            if n["id"] not in sem_nodes:
                problems.append(f"semantic_node_missing_in_source:{n['id']}")
            elif (n.get("attrs") or {}).get("title") != \
                    (sem_nodes[n["id"]].get("attrs") or {}).get("title"):
                problems.append(f"semantic_attr_drift:{n['id']}")
        elif n.get("attribution") == "llm_proposal":
            # 只校验 paperapp 写入的 LLM 提案节点；既有 builder 产出的
            # application 层节点由 build_task_layer 负责，不属于本闸门。
            n_app += 1
            if n["id"] not in registered:
                problems.append(f"unregistered_llm_node:{n['id']}")
    return {"ok": not problems, "reason_code": "EQUIVALENT" if not problems else "DRIFT",
            "n_semantic_projection": n_sem, "n_application_nodes": n_app,
            "n_registered": len(registered), "diff": problems[:20],
            "semantic_sha": util.sha256_file(sem), "app_sha": util.sha256_file(ap)}


@util.with_lock
def materialize(run_id: str, *, out_dir=None, approver: str = "human:materialize",
                write: bool = False, graph_path=None) -> Dict[str, Any]:
    """默认 dry-run；write=True 且 verify ok 时才真正写 app_generation.json。"""
    props = nodecache.load_proposals(run_id, out_dir=out_dir)
    registered, rejected, conflicts, validated = [], [], [], []
    for p in props:
        if p.status == "deprecated":
            continue
        a = align.align(p, out_dir=out_dir, emit_signal=False)
        if a["action"] == "reuse":
            conflicts.append({"proposal_id": p.proposal_id, "reason": "reuse"})
            continue
        conflicts.extend({"proposal_id": p.proposal_id, "reason": c}
                         for c in a.get("conflicts", []))
        p.canonical_id = a["canonical_id"]
        v = validate.validate_proposal(p, gate_state="PASS", evidence_rank=1,
                                       out_dir=out_dir)
        if v["ok"]:
            validated.append(p.proposal_id)
            r = promote.promote(v["proposal"], approver=approver, run_id=run_id,
                                out_dir=out_dir)
            if r.get("ok"):
                registered.append(v["proposal"])
            else:
                rejected.append({"id": p.proposal_id, "reason": r["reason_code"]})
        else:
            rejected.append({"id": p.proposal_id, "reason": v["reason_code"]})
    delta = build_delta(registered)
    v = verify(app_path=graph_path, out_dir=out_dir)
    files: List[str] = []
    if v["ok"] and write and config.ALLOW_INCREMENTAL_WRITE and delta["nodes"]:
        ap = Path(graph_path or config.APP_GRAPH)
        d = json.loads(ap.read_text(encoding="utf-8"))
        have = {n["id"] for n in d["nodes"]}
        d["nodes"].extend(n for n in delta["nodes"] if n["id"] not in have)
        have_a = {a["id"] for a in d["assertions"]}
        d["assertions"].extend(a for a in delta["assertions"]
                               if a["id"] not in have_a)
        util.atomic_write(ap, d)
        files.append(ap.name)
    elif write and not v["ok"]:
        files = []                        # DRIFT 拒写
    registry.bump_usage({p.candidate_class for p in registered}, run_id,
                        out_dir=out_dir)
    promote.bump_usage([p.canonical_id for p in registered], run_id,
                       out_dir=out_dir)
    sig = signals.signal_stats(out_dir=out_dir)
    report = {
        "run_id": run_id, "ts": _now(),
        "n_proposed": len(props), "n_validated": len(validated),
        "n_registered": len(registered), "n_rejected": len(rejected),
        "n_conflicts": len(conflicts),
        "rebuild_equivalence": v["ok"], "verify_reason": v["reason_code"],
        "semantic_graph_sha_before": v.get("semantic_sha"),
        "semantic_graph_sha_after": util.sha256_file(config.SEMANTIC_GRAPH),
        "decision_fp": hitl.decision_fp(out_dir=out_dir),
        "signal_capture_rate": sig["signal_capture_rate"],
        "n_signals_captured": sig["n_signals"],
        "exploration_regret": 0,
        "files_written": files, "delta_ids": [n["id"] for n in delta["nodes"]],
        "rejected": rejected[:20], "conflicts": conflicts[:20],
    }
    base = Path(out_dir) if out_dir else config.RUNS_DIR
    p = base / (run_id.replace(":", "_")) / "MATERIALIZE_REPORT.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    util.atomic_write(p, report)
    util.append_jsonl(base / "MATERIALIZE_LOG.jsonl",
                      {"ts": _now(), "run_id": run_id,
                       "n_registered": len(registered), "ok": v["ok"]})
    return report
