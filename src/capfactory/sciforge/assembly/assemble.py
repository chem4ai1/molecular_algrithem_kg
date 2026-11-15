"""Stage3 唯一入口：A1 Collect → A2 Normalize → A3 Link → A4 Materialize → A5 Verify。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

from .contract import Stage3Manifest
from .collect import collect
from .normalize import normalize
from .link import link
from .materialize import materialize
from .verify import verify

ARTIFACTS = ("STAGE3_MANIFEST.json", "STAGE3_REPORT.md",
             "STAGE3_VIOLATIONS.json", "STAGE3_LINK_PLAN.json")


def assemble_stage3(out_dir: Any, *, arxiv_id: str, paper_id: str,
                    graph: Any, run_id: str = "", md: str = "",
                    repo: str = "", persist_graph: bool = True
                    ) -> Dict[str, Any]:
    """确定性装配；不调 LLM，不覆盖主图文件（写 out_dir/graph.json）。"""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    # A1
    inp = collect(d, arxiv_id=arxiv_id, paper_id=paper_id, graph=graph,
                  run_id=run_id, md=md)
    man = Stage3Manifest(run_id=inp.run_id, arxiv_id=arxiv_id,
                         paper_id=paper_id, inputs_sha=inp.inputs_sha)
    man.a1 = {"complete": inp.complete, "blockers": inp.blockers,
              "n_blocks": len(inp.blocks),
              "stage2_files": len([k for k in
                                   ("related_work", "method", "benchmark")
                                   if getattr(inp, k)])}
    # 幂等：同 sha 且产物齐全 → skipped
    mf = d / "STAGE3_MANIFEST.json"
    REQUIRED_ARTIFACTS = ARTIFACTS + ("algorithm_cards.json",
                                      "leaderboard.json", "graph.json")
    if inp.complete and mf.exists():
        try:
            old = json.loads(mf.read_text(encoding="utf-8"))
            complete = all((d / a).exists() for a in REQUIRED_ARTIFACTS)
            if old.get("inputs_sha") == inp.inputs_sha and complete:
                # 幂等跳过也要把旧 A4/A5 带回，供端到端报告使用
                for k in ("a2", "a3", "a4", "a5", "nodes_added",
                          "edges_added", "csv_rows", "pg_rows",
                          "sota_changes", "warnings", "violations",
                          "gaps", "tbox_hash"):
                    setattr(man, k, old.get(k, getattr(man, k)))
                man.skipped = True
                man.gate = old.get("gate", "PASS")
                return {"ok": True, "skipped": True,
                        "gate": man.gate, "manifest": man.to_dict()}
        except Exception:  # noqa: BLE001
            pass
    if not inp.complete:
        man.gate = "BLOCKED"
        _write_artifacts(d, man, inp, None, None, None, None)
        return {"ok": False, "gate": "BLOCKED", "manifest": man.to_dict(),
                "blockers": inp.blockers}
    # A2/A3
    norm = normalize(inp)
    man.a2 = {"n_benchmarks": len(norm.benchmarks),
              "n_steps": len(norm.steps), "n_tree_edges": len(norm.tree_edges),
              "n_metrics": len(norm.metrics), "problems": norm.problems}
    plan = link(inp, norm, graph=graph, repo=repo)
    man.a3 = {"algorithm_roots": len(plan.algorithm_roots),
              "benchmark_roots": len(plan.benchmark_roots),
              "root_edges": len(plan.root_edges),
              "ast_hits": len(plan.ast_hits), "gaps": len(plan.gaps)}
    man.gaps = plan.gaps + [{"issue": p} for p in norm.problems]
    # A4/A5
    a4 = materialize(inp, norm, plan, graph=graph)
    # P1-7：榜单刷新（A4 子模块，存图统一由此处做）
    try:
        from .leaderboard_refresh import refresh_leaderboard
        lb = refresh_leaderboard(inp, plan, graph=graph)
        a4["pg_rows"] = lb.get("pg_rows") or 0
        a4["sota_changes"] = lb.get("sota_changes") or []
        if not lb.get("ok"):
            man.warnings.append("leaderboard:" + str(lb.get("error", ""))[:120])
    except Exception as exc:  # noqa: BLE001
        man.warnings.append(f"leaderboard:{type(exc).__name__}:{exc}"[:120])
    # P1-8：算法族二级卡片 + 检索索引重建（A4 子模块，与榜单对称）
    try:
        from .cards import build_algorithm_cards
        a4["algorithm_cards"] = build_algorithm_cards(
            inp, norm, plan, graph=graph, use_llm=False)
    except Exception as exc:  # noqa: BLE001 失败不吞
        a4["algorithm_cards"] = {"ok": False,
                                 "error": f"{type(exc).__name__}:{exc}"[:200]}
        man.warnings.append("algorithm_cards:" + str(exc)[:120])
    man.a4 = {k: a4[k] for k in ("csv_rows", "pg_rows", "sota_changes")}
    man.a4["algorithm_cards"] = {
        k: v for k, v in (a4.get("algorithm_cards") or {}).items()
        if k != "cards"}
    man.nodes_added = a4["nodes_added"]
    man.edges_added = a4["edges_added"]
    man.csv_rows = a4["csv_rows"]
    man.warnings += a4["warnings"]
    man.pg_rows = a4["pg_rows"]
    verify(graph, man, a4)
    # 关系索引重建（不调 LLM）
    try:
        from ..relation_layer import build_relations
        build_relations(graph, persist=True)
        man.a5["relation_index_rebuilt"] = True
    except Exception as exc:  # noqa: BLE001
        man.warnings.append(f"relation_index:{type(exc).__name__}:{exc}"[:120])
    if persist_graph:
        try:
            graph.save(str(d / "graph.json"))
        except Exception as exc:  # noqa: BLE001
            man.warnings.append(f"graph_save:{type(exc).__name__}:{exc}"[:120])
    _write_artifacts(d, man, inp, norm, plan, a4, None)
    return {"ok": man.gate != "BLOCKED", "gate": man.gate,
            "skipped": False, "manifest": man.to_dict(),
            "nodes_added": man.nodes_added, "edges_added": man.edges_added}


def _write_artifacts(d: Path, man: Stage3Manifest, inp: Any, norm: Any,
                     plan: Any, a4: Any, _: Any) -> None:
    (d / "STAGE3_MANIFEST.json").write_text(
        json.dumps(man.to_dict(), ensure_ascii=False, indent=2,
                   default=str), encoding="utf-8")
    (d / "STAGE3_VIOLATIONS.json").write_text(
        json.dumps(man.violations, ensure_ascii=False, indent=2,
                   default=str), encoding="utf-8")
    (d / "STAGE3_LINK_PLAN.json").write_text(json.dumps(
        {"algorithm_roots": (plan.algorithm_roots if plan else []),
         "benchmark_roots": (plan.benchmark_roots if plan else []),
         "root_edges": (plan.root_edges if plan else []),
         "ast_hits": (plan.ast_hits if plan else []),
         "gaps": (plan.gaps if plan else [])},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [f"# Stage3 Assembly Report · {man.arxiv_id}", "",
             f"- gate: **{man.gate}**", f"- run_id: `{man.run_id}`",
             f"- inputs_sha: `{man.inputs_sha}`",
             f"- 新增节点: {man.nodes_added}",
             f"- 新增边: {man.edges_added}",
             f"- CSV 行数: {man.csv_rows}",
             f"- 悬空边: {man.a5.get('n_dangling_edges', '-')}",
             f"- violations: {len(man.violations)}",
             f"- warnings: {len(man.warnings)}", "",
             "Stage3 只做确定性装配（A1–A5），不调 LLM 产生新事实。"]
    (d / "STAGE3_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
