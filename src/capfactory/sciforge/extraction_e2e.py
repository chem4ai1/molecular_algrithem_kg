"""抽取全流程端到端编排（单一入口、不重复重建、失败不吞）。

收敛 pipeline 里散落的 3 个 hook 为一条确定性链：
Stage2 产物 → assemble_stage3(A1-A5, 含 cards + leaderboard)
→ 相关论文解析 → 关系索引重建 → 派生节点补齐 → 报告
"""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path("storage_cf/sciforge/batch_multistage")
MD_DIR = Path("/home/zengshuxin/xKG-main/data/docx")
GRAPH = Path("storage_cf/sciforge/batch10_final_graph.json")


def run_extraction_e2e(arxiv_id, *, out_dir=None, graph=None,
                       persist_graph=False):
    from ..po import POGraph
    from .assembly import assemble_stage3
    from .assembly.hydrate import hydrate_derived_nodes
    from .source_resolution import resolve_all
    from .relation_layer import build_relations
    d = Path(out_dir) if out_dir else ROOT / arxiv_id
    t0 = time.time()
    rep = {"arxiv_id": arxiv_id, "out_dir": str(d), "steps": {},
           "artifacts": [], "ok": False}
    if graph is None:
        graph = POGraph.load(str(GRAPH))
    md_p = MD_DIR / (arxiv_id + ".md")
    md = md_p.read_text(encoding="utf-8", errors="replace") if md_p.exists() else ""

    def step(name, fn):
        t = time.time()
        try:
            v = fn()
            rep["steps"][name] = {"ok": True,
                                  "seconds": round(time.time() - t, 2),
                                  "result": v}
            return v
        except Exception as exc:
            msg = (type(exc).__name__ + ":" + str(exc))[:200]
            rep["steps"][name] = {"ok": False, "error": msg,
                                  "seconds": round(time.time() - t, 2)}
            return None

    asm = step("assemble_stage3", lambda: assemble_stage3(
        d, arxiv_id=arxiv_id, paper_id=("paper:" + arxiv_id), graph=graph,
        md=md, persist_graph=persist_graph))
    step("resolve_related_papers", lambda: resolve_all(
        graph, persist=True, persist_graph=False))
    step("hydrate_derived_nodes", lambda: hydrate_derived_nodes(graph))
    step("rebuild_relation_index", lambda: build_relations(graph, persist=True))
    names = sorted(p.name for p in d.glob("STAGE3_*"))
    extra = ("algorithm_cards.json", "leaderboard.json", "graph.json",
             "EXTRACTION_E2E_REPORT.json")
    names += [p.name for p in d.glob("*.json") if p.name in extra]
    rep["artifacts"] = sorted(set(names))
    if asm:
        m = asm["manifest"]
        rep["gate"] = m["gate"]
        rep["inputs_sha"] = m["inputs_sha"]
        rep["nodes_added"] = m["nodes_added"]
        rep["edges_added"] = m["edges_added"]
        rep["a4"] = m["a4"]
        rep["violations"] = len(m["violations"])
    rep["seconds"] = round(time.time() - t0, 2)
    all_ok = all(v["ok"] for v in rep["steps"].values())
    rep["ok"] = bool(all_ok and rep.get("gate") in ("PASS", "PARTIAL"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "EXTRACTION_E2E_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return rep
