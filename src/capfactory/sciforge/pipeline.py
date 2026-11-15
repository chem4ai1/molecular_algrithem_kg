"""多阶段抽取编排：主链筛选 → 块向量化 → 按块深挖 → 三类出处 CSV。

阶段（对应用户定义）：
  Stage0  Paper 根：LLM 按小标题筛选，只用保留块建主链（表格/参考文献/相关论文不建）
  Stage1  块向量化：bge-m3 存储，可按类型检索
  Stage2  按块肢解：科技树 / 算法-公式-代码 / 基准数据特征+指标
  Stage3  三类出处：规则匹配 → 三份 CSV，不建 Citation 条目
"""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..ingest.pdf import split_sections
from .blocks import (screen_headings, build_blocks, BlockStore,
                     build_main_chain, ensure_plan)
from .deepdive import deep_dive, tree_to_graph
from .sources import build_sources
from .tentacle import _ast_functions

MD_DIR = Path("/home/zengshuxin/xKG-main/data/docx")


def _symbols(repo: str) -> str:
    return "\n".join(f"- {f['name']}" for f in _ast_functions(repo))


def run_pipeline(*, arxiv_id: str, paper_id: str, graph: Any,
                 repo: str = "", out_dir: str | Path = "storage_cf/sciforge/multistage",
                 chat_fn: Optional[Callable[..., str]] = None,
                 embed: bool = True, router: Any = None,
                 use_polo_fallback: bool = True) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = (MD_DIR / f"{arxiv_id}.md").read_text(encoding="utf-8", errors="replace")
    secs = split_sections(md)
    rep: Dict[str, Any] = {"arxiv_id": arxiv_id, "paper_id": paper_id,
                           "n_sections": len(secs), "stages": {}}
    t_all = time.time()
    if router is None and chat_fn is None:
        from .llm_router import LLMRouter
        router = LLMRouter(use_polo_fallback=use_polo_fallback)

    # ---- Stage0：小标题筛选 + 主链 ----
    t0 = time.time()
    plan = screen_headings(list(secs), chat_fn=chat_fn, router=router,
                           max_tokens=2000)
    plan = ensure_plan(plan, list(secs), secs)
    main = build_main_chain(graph, paper_id=paper_id, sections=secs, plan=plan)
    rep["stages"]["stage0_main_chain"] = {
        "seconds": round(time.time() - t0, 2), "plan": plan, "main_chain": main}
    (out / "STAGE0_HEADING_PLAN.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Stage1：块向量化 ----
    t0 = time.time()
    blocks = build_blocks(secs, plan)
    store = BlockStore(blocks)
    vstats = store.vectorize() if embed and blocks else {"embedded": 0}
    bpath = store.save(out / "blocks.jsonl")
    rep["stages"]["stage1_vectors"] = {
        "seconds": round(time.time() - t0, 2), "blocks": len(blocks),
        "vector_stats": vstats, "path": bpath,
        "by_kind": {k: sum(1 for b in blocks if b["kind"] == k)
                    for k in ("related_work", "method", "benchmark")},
        "sample_search": store.search("baseline comparison metric", top_k=2)
        if blocks else []}

    # ---- Stage2：按块深挖 ----
    t0 = time.time()
    dd = deep_dive(blocks, code_symbols=_symbols(repo), chat_fn=chat_fn,
                   router=router)
    rep["stages"]["stage2_deepdive"] = {
        "seconds": round(time.time() - t0, 2), "ok": dd["ok"],
        "n_attempts": dd["n_attempts"], "summary": dd["summary"],
        "modules": {k: {"ok": v["ok"], "n_attempts": v["n_attempts"],
                        "attempts": v["attempts"],
                        "backend": v.get("backend", "legacy")}
                    for k, v in dd["modules"].items()}}
    for k, v in dd["logical"].items():
        (out / f"STAGE2_{k}.json").write_text(
            json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
    tree = dd["logical"]["related_work"]
    graph_stats = tree_to_graph(graph, tree.get("chains") or [],
                                paper_id=paper_id)
    rep["stages"]["stage2_deepdive"]["tree_graph"] = graph_stats

    # ---- Stage3：三类出处 + 三份 CSV ----
    t0 = time.time()
    src = build_sources(graph, arxiv_id=arxiv_id, paper_id=paper_id, md=md,
                        tree=tree, out_dir=out)
    rep["stages"]["stage3_sources"] = {
        "seconds": round(time.time() - t0, 2), "by_kind": src["by_kind"],
        "csv_paths": src["csv_paths"]}

    # ---- Stage3 之后：表格抽取 → PG → 刷新基准可更新榜单与动态 SOTA ----
    t0 = time.time()
    try:
        from .benchmark_fill import extract_and_refresh
        lb = extract_and_refresh(arxiv_id, graph, md, persist=True)
        rep["stages"]["stage3_leaderboard"] = {
            "ok": True, "seconds": round(time.time() - t0, 2),
            "rows": lb["import"].get("rows"),
            "benchmark_ids": lb["import"].get("benchmark_ids"),
            "refreshed": lb["refresh"]["refreshed"],
            "sota_changes": lb["refresh"]["sota_changes"]}
    except Exception as exc:  # noqa: BLE001  不阻断主流程
        rep["stages"]["stage3_leaderboard"] = {
            "ok": False, "error": f"{type(exc).__name__}:{exc}"[:200],
            "seconds": round(time.time() - t0, 2)}

    # ---- Stage3 之后：语义层抽取（新链路，取代旧 paper_core LLM 重抽）----
    t0 = time.time()
    try:
        from ..semantic.extraction.runner import run_extraction
        xr = run_extraction(arxiv_id, md=md, graph=graph, persist=True)
        rep["stages"]["semantic_extract"] = {
            "ok": xr["ok"], "seconds": round(time.time() - t0, 2),
            "paper_type": xr["paper_type"]["paper_type"],
            "n_stages": len(xr["stages"]),
            "slot_score": (xr.get("paradigm") or {}).get(
                "summary", {}).get("slot_score")}
    except Exception as exc:  # noqa: BLE001  不阻断主流程
        rep["stages"]["semantic_extract"] = {
            "ok": False, "error": f"{type(exc).__name__}:{exc}"[:200],
            "seconds": round(time.time() - t0, 2)}

    # ---- Stage3 标准化入口：s3_assembly（A1–A5 确定性装配） ----
    # 蓝图 P2-9：把三个 Stage3 子步骤收敛到统一 Manifest，旧键保留兼容
    t0 = time.time()
    try:
        from .assembly import assemble_stage3
        asm = assemble_stage3(out, arxiv_id=arxiv_id, paper_id=paper_id,
                              graph=graph, run_id=job.get("job_id", ""),
                              md=md, persist_graph=True)
        mf = asm["manifest"]
        rep["stages"]["s3_assembly"] = {
            "ok": asm["ok"], "gate": mf["gate"],
            "skipped": asm.get("skipped", False),
            "inputs_sha": mf["inputs_sha"],
            "seconds": round(time.time() - t0, 2),
            "nodes_added": mf["nodes_added"],
            "edges_added": mf["edges_added"],
            "violations": len(mf["violations"]),
            "substeps": {k: bool(rep["stages"].get(k, {}).get("ok", True))
                         for k in ("stage3_sources", "stage3_leaderboard",
                                   "stage3_paper_core")}}
    except Exception as exc:  # noqa: BLE001 失败不吞：写 error + gate
        rep["stages"]["s3_assembly"] = {
            "ok": False, "gate": "BLOCKED",
            "error": f"{type(exc).__name__}:{exc}"[:200],
            "seconds": round(time.time() - t0, 2)}

    rep["total_seconds"] = round(time.time() - t_all, 2)
    rep["ok"] = (bool(main["main_chain_sections"]) and dd["ok"])
    (out / "PIPELINE_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return rep
