"""v6 前端 API：主界面 / Pipeline / 简化抽取 /（P1 数据、P2 图谱同文件扩展）。

设计原则：
* 主界面只做路由分发（数据 / 图谱 / Pipeline）；
* 抽取页每阶段固定五段：输入 / 提示词 / 输出 / 使用的图 / 产出节点；
* 三视图用**边白名单**过滤同一张图，不建三张图。
"""
from __future__ import annotations
import collections, threading, time, uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .extraction_api import (BATCH_DIR, GRAPH_PATH, IMPORT_DIR, PROJ,
                             STATIC_DIR, _extraction, _load_papers,
                             _prompt_catalog, _read, build_chains)

_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _graph() -> Any:
    from ..po import POGraph
    return POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists() else POGraph("v6")


def home_summary() -> Dict[str, Any]:
    g = _graph()
    c = collections.Counter(n.type for n in g.nodes.values())
    runs = []
    if BATCH_DIR.exists():
        for d in sorted(BATCH_DIR.iterdir()):
            if not d.is_dir():
                continue
            rep = _read(d, "PIPELINE_REPORT.json")
            if rep:
                runs.append({"arxiv_id": d.name, "ok": rep.get("ok"),
                             "seconds": rep.get("total_seconds"),
                             "n_blocks": rep.get("stages", {})
                             .get("stage1_vectors", {}).get("blocks")})
    runs.sort(key=lambda x: -(x.get("seconds") or 0))
    return {"graph": {"nodes": len(g.nodes), "edges": len(g.assertions),
                      "top": dict(c.most_common(8))},
            "counts": {"paper": c.get("Paper", 0),
                       "algorithm": c.get("Algorithm", 0),
                       "benchmark": c.get("Benchmark", 0),
                       "observation": c.get("MetricObservation", 0) +
                       c.get("Observation", 0),
                       "code_function": c.get("CodeFunction", 0)},
            "runs": runs[:8], "n_runs": len(runs),
            "links": {"data": "/data", "graph": "/data/graph",
                      "pipeline": "/pipeline", "extract": "/pipeline/extract"}}


PIPELINE_STAGES = [
    {"id": "extract", "order": 1, "label": "论文抽取", "stage": "extract",
     "input": "论文 Markdown + 代码 AST + 当前图谱",
     "output": "抽取报告（含 paradigm 范式层）+ 语义层节点/关系",
     "gate": "标题筛选 · 逐字证据 · AST 白名单 · 词表校验",
     "route": "/pipeline/extract"},
    {"id": "lock", "order": 2, "label": "方法锁定", "stage": "lock",
     "input": "ReproSpec 的 method SAU（stable_key）",
     "output": "METHOD_LOCK.json：逐条指纹 + 集合 hash",
     "gate": "指纹漂移即不通过（不静默）", "route": "/repro"},
    {"id": "codegen", "order": 3, "label": "代码生成", "stage": "codegen",
     "input": "ordering SAU 依赖 + code_grounding 符号",
     "output": "CODE_PLAN.json（DAG+任务）+ REPRO_SCRIPT.py",
     "gate": "脚本安全 · 符号召回 · 顺序单调 · 环降级告警",
     "route": "/repro"},
    {"id": "execute", "order": 4, "label": "复现执行", "stage": "execute",
     "input": "REPRO_SCRIPT.py + 数据契约",
     "output": "EXECUTION_LOG.json：subset/full + 失败定位到 SAU",
     "gate": "双跑一致 · 方法覆盖 · 失败落 SAU", "route": "/repro"},
    {"id": "anchor", "order": 5, "label": "主张锚定", "stage": "anchor",
     "input": "numeric SAU + 执行输出",
     "output": "CLAIM_ANCHORS.json：claim→单元格→图节点",
     "gate": "四 hash · 逐条 verified · 三级命中率",
     "route": "/repro"},
    {"id": "report", "order": 6, "label": "复现报告", "stage": "report",
     "input": "SAU 判定 + 锚定 + 树评分",
     "output": "REPRO_REPORT.md + FINAL_EVALUATION.json",
     "gate": "三层对齐分 · 阻断原因如实记录", "route": "/repro"},
]

_DEFAULT_WS = ("storage/repro_test/2411.06608",
               "storage/repro_runs/2411.06608",
               "storage_cf/repro_runs/2411.06608")


def _repro_state() -> Dict[str, str]:
    """把生命周期状态映射成页面状态：done / blocked / ready。"""
    import pathlib as _pl
    ws = next((_pl.Path(x) for x in _DEFAULT_WS if _pl.Path(x).exists()), None)
    if ws is None:
        return {}
    try:
        from ..reprospec.lifecycle import stage_status
        st = stage_status(ws)
    except Exception:  # noqa: BLE001  状态读取失败不应拖垮首页
        return {}
    out = {}
    for k, v in (st.get("stages") or {}).items():
        out[k] = {"done": "done", "failed": "blocked",
                  "pending": "ready"}.get(v.get("state"), "ready")
    # 报告环节：有最终评价文件即视为完成
    out["report"] = ("done" if (ws / "FINAL_EVALUATION.json").exists()
                     else "ready")
    return out


def pipeline_stages() -> Dict[str, Any]:
    live = _repro_state()
    stages = []
    for s in PIPELINE_STAGES:
        row = dict(s)
        if s["id"] == "extract":
            row["state"] = "ready"
            row["state_note"] = "常开"
        else:
            row["state"] = live.get(s["id"], "ready")
            row["state_note"] = {"done": "已完成", "blocked": "已阻断",
                                 "ready": "可运行"}.get(row["state"], "可运行")
        stages.append(row)
    return {"stages": stages,
            "implemented": [s["id"] for s in stages],
            "workspace": next((x for x in _DEFAULT_WS
                               if _pl_exists(x)), ""),
            "note": "六个阶段均已实现；lock 之后的状态读自复现工作区"}


def _pl_exists(x: str) -> bool:
    import pathlib as _pl
    return _pl.Path(x).exists()


def list_papers(q: str = "", limit: int = 60) -> Dict[str, Any]:
    items = _load_papers()
    if q:
        ql = q.lower()
        items = [x for x in items if ql in x["title"].lower()
                 or ql in x["arxiv_id"] or ql in x["repo"].lower()]
    return {"total": len(items), "items": items[:limit]}


def pipeline_runs() -> Dict[str, Any]:
    out = []
    if BATCH_DIR.exists():
        for d in sorted(BATCH_DIR.iterdir()):
            rep = _read(d, "PIPELINE_REPORT.json")
            if rep:
                out.append({"arxiv_id": d.name, "ok": rep.get("ok"),
                            "seconds": rep.get("total_seconds")})
    return {"runs": out}


STAGE_SPEC = [
    ("stage0", "小标题筛选与主链", "stage0_main_chain"),
    ("stage1", "块向量化存储", "stage1_vectors"),
    ("stage2", "按块类型肢解", "stage2_deepdive"),
    ("stage3", "三类出处与 CSV", "stage3_sources"),
]


def _graph_usage() -> Dict[str, Any]:
    g = _graph()
    return {"path": GRAPH_PATH.name, "nodes": len(g.nodes),
            "edges": len(g.assertions),
            "read": ["Paper", "Algorithm", "Benchmark", "CodeFunction"]}


def _stage_view(aid: str, d: Path, idx: int) -> Dict[str, Any]:
    sid, label, key = STAGE_SPEC[idx]
    ex = _extraction(d)
    rep = ex.get("report") or {}
    sg = (rep.get("stages") or {}).get(key, {})
    cat = _prompt_catalog()
    chains = build_chains(aid, ex)
    blocks = ex["plan"].get("blocks") or {}
    if idx == 0:
        heads = list(ex["plan"].get("main_chain") or [])
        n_heads = len(heads) + sum(len(v or []) for v in blocks.values())
        view = {
            "input": {"source": f"data/docx/{aid}.md",
                      "slice_chars": 48000, "headings": n_heads},
            "prompt": cat["heading_screen"].replace(
                "{headings}", "\n".join("- " + h for h in heads)[:1400]),
            "output": {"main_chain": heads,
                       "blocks": {k: len(v or []) for k, v in blocks.items()},
                       "n_main": len(heads),
                       "n_blocks": sum(len(v or []) for v in blocks.values())},
            "nodes": [{"id": f"section:{aid}:main:{i}", "type": "Section",
                       "label": h} for i, h in enumerate(heads)]}
    elif idx == 1:
        view = {"input": {"source": "STAGE0 筛选出的块",
                          "blocks": sg.get("blocks")},
                "prompt": cat["vector_rule"],
                "output": {"vector_stats": sg.get("vector_stats"),
                           "by_kind": sg.get("by_kind"),
                           "blocks_jsonl": sg.get("path")},
                "nodes": [{"id": f"block:{aid}:{k}:{i}", "type": "Block",
                           "label": h}
                          for k, hs in blocks.items()
                          for i, h in enumerate(hs or [])]}
    elif idx == 2:
        mods = sg.get("modules") or {}
        view = {"input": {"source": "STAGE1 blocks.jsonl",
                          "modules": ["related_work", "method",
                                      "benchmark_profile", "benchmark_values"],
                          "ast_symbols": rep.get("ast_symbols")},
                "prompts": {k: cat.get(k, "") for k in
                            ("related_work", "method", "benchmark_profile",
                             "benchmark_values")},
                "output": {"summary": sg.get("summary"),
                           "backends": {k: v.get("backend")
                                        for k, v in mods.items()},
                           "related_work": ex["tree"],
                           "method": ex["method"],
                           "benchmark": ex["benchmark"]},
                "nodes": [n for n in chains["nodes"]
                          if n["style"] in ("method", "code", "benchmark",
                                            "tech_tree")]}
    else:
        view = {"input": {"source": "STAGE2 结果 + 各篇参考文献",
                          "rule": "arXiv → DOI → 标题 token Jaccard≥0.72"},
                "prompt": cat["sources_rule"],
                "output": sg.get("by_kind") or {},
                "nodes": [n for n in chains["nodes"]
                          if n["type"] == "SourcePaper"]}
    return {"id": sid, "order": idx + 1, "label": label,
            "status": "done" if (sg or idx == 0) else "pending",
            "graph": _graph_usage(),
            "meta": {"seconds": sg.get("seconds"),
                     "source": sg.get("source")},
            **view}


def extract_state(job: Dict[str, Any]) -> Dict[str, Any]:
    aid, d = job["arxiv_id"], Path(job["out_dir"])
    chains = build_chains(aid, _extraction(d))
    return {"job_id": job["id"], "arxiv_id": aid, "title": job["title"],
            "repo": job["repo"], "status": job["status"],
            "data_source": job["source_label"],
            "stages": [_stage_view(aid, d, i) for i in range(4)],
            "summary": {"n_nodes": len(chains["nodes"]),
                        "n_edges": len(chains["edges"]),
                        "styles": chains["styles"],
                        "total_seconds": (job.get("report") or {}).get(
                            "total_seconds")}}


class ExtractReq(BaseModel):
    arxiv_id: str
    mode: str = "auto"          # auto | cached | live
    use_polo: bool = True


def start_extract(req: ExtractReq) -> Dict[str, Any]:
    papers = {p["arxiv_id"]: p for p in _load_papers()}
    if req.arxiv_id not in papers:
        raise HTTPException(404, "论文不在库中或缺少本地 Markdown")
    p = papers[req.arxiv_id]
    cached = (BATCH_DIR / req.arxiv_id / "PIPELINE_REPORT.json").exists()
    mode = req.mode if req.mode != "auto" else ("cached" if cached else "live")
    jid = uuid.uuid4().hex[:10]
    d = (BATCH_DIR / req.arxiv_id if mode == "cached" else
         PROJ / "storage_cf/sciforge/web_runs" / jid)
    job = {"id": jid, "arxiv_id": req.arxiv_id, "title": p["title"],
           "repo": p["repo"], "status": "running", "mode": mode,
           "source_label": "缓存 run" if mode == "cached" else "实时抽取",
           "out_dir": str(d), "created": time.time()}
    with _LOCK:
        _JOBS[jid] = job

    def worker() -> None:
        try:
            if mode == "live":
                from ..po import POGraph
                from ..sciforge.pipeline import run_pipeline
                from ..sciforge.llm_router import LLMRouter
                g = POGraph("web")
                g.node(f"paper:{req.arxiv_id}", "Paper", p["title"][:70])
                g.node(f"algorithm:{req.arxiv_id}", "Algorithm",
                       p["title"][:40])
                g.node(f"benchmark:{req.arxiv_id}", "Benchmark", "primary")
                run_pipeline(arxiv_id=req.arxiv_id,
                             paper_id=f"paper:{req.arxiv_id}", graph=g,
                             repo=p["repo"], out_dir=d,
                             router=LLMRouter(use_polo_fallback=req.use_polo))
            if not (d / "PIPELINE_REPORT.json").exists():
                raise RuntimeError("未找到抽取产物")
            job["report"] = _read(d, "PIPELINE_REPORT.json")
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": jid, "status": "running", "mode": mode,
            "arxiv_id": req.arxiv_id}


def get_extract(job_id: str) -> Dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job["status"] == "running":
        return {"job_id": job_id, "status": "running",
                "arxiv_id": job["arxiv_id"], "repo": job["repo"],
                "title": job["title"], "data_source": job["source_label"],
                "stages": [{"id": s[0], "order": i + 1, "label": s[1],
                            "status": "running"}
                           for i, s in enumerate(STAGE_SPEC)],
                "summary": {}}
    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed",
                "error": job.get("error"), "stages": [], "summary": {}}
    return extract_state(job)


def import_extract(job_id: str) -> Dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(409, "任务未完成")
    from ..po import POGraph
    g = (POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists()
         else POGraph("v6"))
    before = (len(g.nodes), len(g.assertions))
    chains = build_chains(job["arxiv_id"], _extraction(Path(job["out_dir"])))
    an = ae = 0
    for n in chains["nodes"]:
        if n["id"] not in g.nodes:
            g.node(n["id"], n["type"], n["label"], style=n["style"],
                   provenance="web_extraction", import_job=job_id)
            an += 1
    for e in chains["edges"]:
        if e["source"] in g.nodes and e["target"] in g.nodes:
            if g.assert_rel(e["source"], e["target"], e["rel"]):
                ae += 1
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = IMPORT_DIR / f"graph_after_{job_id}.json"
    g.save(str(out))
    return {"added_nodes": an, "added_edges": ae,
            "graph_before": list(before),
            "graph_after": [len(g.nodes), len(g.assertions)],
            "saved": str(out)}


def _page(name: str) -> HTMLResponse:
    p = STATIC_DIR / name
    if not p.exists():
        raise HTTPException(500, f"页面缺失：{name}")
    return HTMLResponse(p.read_text(encoding="utf-8"))


def home_page() -> HTMLResponse:
    return _page("home.html")


def pipeline_page() -> HTMLResponse:
    return _page("pipeline.html")


def extract_page() -> HTMLResponse:
    return _page("pipeline_extract.html")


_V6_ROUTES = [
    ("/api/v6/home/summary", home_summary, "GET", True),
    ("/api/v6/data/papers", list_papers, "GET", True),
    ("/api/v6/pipeline/stages", pipeline_stages, "GET", True),
    ("/api/v6/pipeline/runs", pipeline_runs, "GET", True),
    ("/api/v6/pipeline/extract", start_extract, "POST", True),
    ("/api/v6/pipeline/extract/{job_id}", get_extract, "GET", True),
    ("/api/v6/pipeline/extract/{job_id}/import", import_extract, "POST", True),
    ("/api/v6/home", home_page, "GET", False),
    ("/api/v6/pipeline", pipeline_page, "GET", False),
    ("/api/v6/extract", extract_page, "GET", False),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V6_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
