"""论文多阶段抽取工作台 API。

前端可见三件事：每个阶段的**提示词**、**抽取结果**、**建立的链样式**；
并可把链导入当前知识图谱。支持 cached（读已落盘 run，秒级）与 live（真跑本地 qwen）。
"""
from __future__ import annotations
import os
import csv, json, re, threading, time, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(os.environ.get("CAPFACTORY_ROOT", "."))
PROJ = ROOT / "xKG-main"
STATIC_DIR = Path(__file__).parent / "static"
MD_DIR = ROOT / "data/docx"
PAPERS_CSV = ROOT / "data/papers/papers.csv"
BATCH_DIR = PROJ / "storage_cf/sciforge/batch_multistage"
GRAPH_PATH = PROJ / "storage_cf/sciforge/batch10_final_graph.json"
IMPORT_DIR = PROJ / "storage_cf/sciforge/web_imports"

_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

STAGE_META = [
    {"id": "stage0", "label": "Stage 0 · 小标题筛选与主链", "kind": "heading"},
    {"id": "stage1", "label": "Stage 1 · 块向量化存储", "kind": "vector"},
    {"id": "stage2", "label": "Stage 2 · 按块类型肢解", "kind": "deepdive"},
    {"id": "stage3", "label": "Stage 3 · 三类出处与 CSV", "kind": "source"},
]


def _load_papers() -> List[Dict[str, Any]]:
    repos: Dict[str, str] = {}
    sel_p = PROJ / "storage_cf/sciforge/batch10_report.json"
    if sel_p.exists():
        with open(sel_p, encoding="utf-8") as fh:
            selected = json.load(fh).get("selected", [])
        for x in selected:
            repos[x["arxiv_id"]] = x.get("repo", "")
    out: List[Dict[str, Any]] = []
    with open(PAPERS_CSV, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            aid = (r.get("arxiv_id") or "").strip()
            if not aid or not (MD_DIR / f"{aid}.md").exists():
                continue
            out.append({"arxiv_id": aid,
                        "title": (r.get("title") or "")[:140],
                        "year": r.get("year") or "",
                        "domain": r.get("domain") or "",
                        "algorithms": r.get("algorithms") or "",
                        "repo": repos.get(aid, ""),
                        "code_urls": (r.get("code_urls") or "")[:200],
                        "has_md": True,
                        "has_cached_run": (BATCH_DIR / aid /
                                           "PIPELINE_REPORT.json").exists()})
    return out


def _read(d: Path, name: str) -> Dict[str, Any]:
    p = d / name
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _prompt_catalog() -> Dict[str, str]:
    from ..sciforge.blocks import HEADING_PROMPT
    from ..semantic.extraction.prompts import PROMPTS  # 新链路 E1–E6
    return {"heading_screen": HEADING_PROMPT, **PROMPTS,
            "sources_rule": ("规则匹配（无 LLM 提示词）：References 节按 [n] 切条 → "
                             "arXiv id → DOI → 标题 token Jaccard≥0.72 匹配 papers.csv；"
                             "相关论文/算法/benchmark 三类根对象各自输出 CSV。"),
            "vector_rule": ("无 LLM 提示词：bge-m3:latest 把筛选后的块向量化（1024 维）"
                            "落 blocks.jsonl，支持按 kind 余弦检索。")}


def _node(nodes: list, nid: str, label: str, typ: str, style: str) -> None:
    if not any(n["id"] == nid for n in nodes):
        nodes.append({"id": nid, "label": label[:60], "type": typ,
                      "style": style})


def build_chains(aid: str, ex: Dict[str, Any]) -> Dict[str, Any]:
    """把四阶段结果统一成可视图 + 可导入的 nodes/edges。"""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    pid = f"paper:{aid}"
    _node(nodes, pid, aid, "Paper", "paper")
    plan = ex.get("plan") or {}
    for i, h in enumerate(plan.get("main_chain") or []):
        sid = f"section:{aid}:main:{i}"
        _node(nodes, sid, h, "Section", "main_chain")
        edges.append({"source": pid, "target": sid, "rel": "HAS_SECTION",
                      "style": "main_chain"})
    for kind, heads in (plan.get("blocks") or {}).items():
        for i, h in enumerate(heads or []):
            bid = f"block:{aid}:{kind}:{i}"
            _node(nodes, bid, h, "Block", "block")
            edges.append({"source": pid, "target": bid, "rel": "HAS_BLOCK",
                          "style": "block", "kind": kind})
    tree = ex.get("tree") or {}
    for c in tree.get("chains") or []:
        st = c.get("style") or "tree"
        for m in c.get("methods") or []:
            mid = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+','_',str(m).lower())[:36]}"
            _node(nodes, mid, str(m), "SourcePaper", "tech_tree")
        for e in c.get("edges") or []:
            a = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+','_',str(e.get('src','')).lower())[:36]}"
            b = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+','_',str(e.get('dst','')).lower())[:36]}"
            _node(nodes, a, str(e.get("src") or ""), "SourcePaper", "tech_tree")
            _node(nodes, b, str(e.get("dst") or ""), "TechTreeNode", "tech_tree")
            edges.append({"source": a, "target": b, "rel": e.get("rel") or "",
                          "style": st, "confidence": e.get("confidence"),
                          "evidence": (e.get("evidence") or "")[:120]})
    method = ex.get("method") or {}
    alg = f"algorithm:{aid}"
    _node(nodes, alg, method.get("algorithm_name") or aid, "Algorithm", "method")
    for i, s in enumerate(method.get("steps") or []):
        sid = f"algorithmstep:{aid}:{i}"
        _node(nodes, sid, s.get("name") or f"step{i}", "AlgorithmStep", "method")
        edges.append({"source": alg, "target": sid, "rel": "HAS_STEP",
                      "style": "method", "mechanism": s.get("mechanism", "")[:80]})
        if s.get("formula_ref"):
            fid = f"formula:{aid}:{i}"
            _node(nodes, fid, s["formula_ref"], "Formula", "method")
            edges.append({"source": sid, "target": fid, "rel": "HAS_FORMULA",
                          "style": "method"})
        for j, t in enumerate(s.get("tools") or []):
            tid = f"tool:{aid}:{i}:{j}"
            _node(nodes, tid, str(t), "Tool", "method")
            edges.append({"source": sid, "target": tid, "rel": "USES_TOOL",
                          "style": "method"})
        for j, sym in enumerate(s.get("code_symbols") or []):
            cid = f"codefunction:{aid}:{i}:{j}"
            _node(nodes, cid, str(sym), "CodeFunction", "code")
            edges.append({"source": sid, "target": cid, "rel": "REALIZED_BY",
                          "style": "code"})
    bench = ex.get("benchmark") or {}
    for i, b in enumerate(bench.get("benchmarks") or []):
        bid = f"benchmark:{aid}:{i}"
        _node(nodes, bid, b.get("name") or f"benchmark{i}", "Benchmark", "benchmark")
        edges.append({"source": pid, "target": bid, "rel": "EVALUATED_ON",
                      "style": "benchmark"})
        did = f"datacontract:{aid}:{i}"
        _node(nodes, did, "DataContract", "DataContract", "benchmark")
        edges.append({"source": bid, "target": did, "rel": "HAS_DATA_CONTRACT",
                      "style": "benchmark"})
    for i, o in enumerate(bench.get("observations") or []):
        oid = f"observation:{aid}:{i}"
        _node(nodes, oid, f"{o.get('metric')}={o.get('value')}",
              "Observation", "benchmark")
        edges.append({"source": pid, "target": oid, "rel": "REPORTS",
                      "style": "benchmark"})
    # ---- 边 enrich：端点真实名称/类型 + 语义链分组 ----
    TREE_CN = {"bottleneck": "瓶颈→机制", "improvement": "改进/替代",
               "taxonomy": "分类归属", "comparison": "方法对比"}
    STEP_RELS = {"HAS_FORMULA", "USES_TOOL", "REALIZED_BY", "HAS_MODULE_IMPL"}
    TREE_RELS = {"COMPARES_WITH", "IMPROVED_BY", "REPLACES", "REPLACED_BY",
                 "BELONGS_TO", "HAS_LIMITATION", "ADDRESSED_BY", "ON_METRIC",
                 "DELTA"}
    BENCH_RELS = {"EVALUATED_ON", "HAS_DATA_CONTRACT", "REPORTS",
                  "REPORTS_VALUE", "BINDS_EVAL_TOOL"}
    idx = {n["id"]: n for n in nodes}

    def _chain(e, s, t):
        rel = e["rel"]
        if rel == "HAS_SECTION":
            return "main", "论文主链 · 小节", "论文"
        if rel == "HAS_BLOCK":
            k = e.get("kind") or "block"
            return "block:" + k, f"深挖块 · {k}", "块"
        if rel in TREE_RELS:
            st = e.get("style") or "tree"
            return ("tree:" + st, "科技树 · " + TREE_CN.get(st, st), "科技树")
        if rel == "HAS_STEP":
            name = (t or {}).get("label", "")
            return "step:" + e["target"], f"算法步骤 · {name}", "算法"
        if rel in STEP_RELS:
            name = (s or {}).get("label", "")
            return "step:" + e["source"], f"算法步骤 · {name}", "算法"
        if rel in BENCH_RELS:
            name = (t or {}).get("label", "")
            if rel == "REPORTS":
                return "benchmark", "基准 · 评测观测", "基准"
            return "benchmark:" + e["target"], f"基准 · {name}", "基准"
        if rel in ("SITUATED_IN", "SOURCED_FROM", "RESOLVED_TO"):
            return "source", "出处 · 论文", "出处"
        return "other", "其它关系", "其它"

    for e in edges:
        s_n, t_n = idx.get(e["source"]), idx.get(e["target"])
        e["source_label"] = (s_n or {}).get("label") or e["source"]
        e["source_type"] = (s_n or {}).get("type") or "?"
        e["target_label"] = (t_n or {}).get("label") or e["target"]
        e["target_type"] = (t_n or {}).get("type") or "?"
        cid, clabel, ckind = _chain(e, s_n, t_n)
        e["chain_id"], e["chain_label"], e["chain_kind"] = cid, clabel, ckind
    chains: Dict[str, Any] = {}
    for e in edges:
        c = chains.setdefault(e["chain_id"], {
            "id": e["chain_id"], "label": e["chain_label"],
            "kind": e["chain_kind"], "edges": []})
        c["edges"].append(e)
    return {"nodes": nodes, "edges": edges,
            "chains": sorted(chains.values(),
                             key=lambda c: (-len(c["edges"]), c["label"])),
            "styles": sorted({n["style"] for n in nodes})}


def _extraction(d: Path) -> Dict[str, Any]:
    return {"plan": _read(d, "STAGE0_HEADING_PLAN.json"),
            "tree": _read(d, "STAGE2_related_work.json"),
            "method": _read(d, "STAGE2_method.json"),
            "benchmark": _read(d, "STAGE2_benchmark.json"),
            "report": _read(d, "PIPELINE_REPORT.json")}


def _build_job_state(job: Dict[str, Any]) -> Dict[str, Any]:
    aid, d = job["arxiv_id"], Path(job["out_dir"])
    ex = _extraction(d)
    cat = _prompt_catalog()
    rep = ex["report"]
    sg = rep.get("stages", {})
    heads = list(ex["plan"].get("main_chain") or []) + [
        h for v in (ex["plan"].get("blocks") or {}).values()
        for h in (v or [])]
    stages: List[Dict[str, Any]] = [
        {"id": "stage0", "label": STAGE_META[0]["label"], "status": "done",
         "prompt": cat["heading_screen"].replace(
             "{headings}", "\n".join("- " + h for h in heads)[:1400]),
         "result": {"plan": ex["plan"]},
         "meta": {"source": ex["plan"].get("source"),
                  "degraded": ex["plan"].get("degraded", False),
                  "seconds": sg.get("stage0_main_chain", {}).get("seconds")}},
        {"id": "stage1", "label": STAGE_META[1]["label"], "status": "done",
         "prompt": cat["vector_rule"], "result": sg.get("stage1_vectors", {}),
         "meta": {"blocks": sg.get("stage1_vectors", {}).get("blocks"),
                  "vector_stats": sg.get("stage1_vectors", {}).get("vector_stats")}},
        {"id": "stage2", "label": STAGE_META[2]["label"], "status": "done",
         "prompts": {k: cat.get(k, "") for k in
                     ("related_work", "method", "benchmark_profile",
                      "benchmark_values")},
         "result": {"related_work": ex["tree"], "method": ex["method"],
                    "benchmark": ex["benchmark"]},
         "meta": {"summary": sg.get("stage2_deepdive", {}).get("summary"),
                  "modules": sg.get("stage2_deepdive", {}).get("modules", {}),
                  "seconds": sg.get("stage2_deepdive", {}).get("seconds")}},
        {"id": "stage3", "label": STAGE_META[3]["label"], "status": "done",
         "prompt": cat["sources_rule"],
         "result": sg.get("stage3_sources", {}).get("by_kind", {}),
         "meta": {"csv_paths": sg.get("stage3_sources", {}).get("csv_paths", {})}},
    ]
    chains = build_chains(aid, ex)
    return {"job_id": job["id"], "arxiv_id": aid, "title": job["title"],
            "repo": job["repo"], "mode": job["mode"], "status": job["status"],
            "stages": stages, "chains": chains,
            "summary": {"ok": rep.get("ok"),
                        "total_seconds": rep.get("total_seconds"),
                        "n_nodes": len(chains["nodes"]),
                        "n_edges": len(chains["edges"]),
                        "styles": chains["styles"]}}


class ExtractRequest(BaseModel):
    arxiv_id: str
    mode: str = "cached"
    use_polo: bool = True


def list_papers(q: str = "", limit: int = 40) -> Dict[str, Any]:
    items = _load_papers()
    if q:
        ql = q.lower()
        items = [x for x in items if ql in x["title"].lower()
                 or ql in x["arxiv_id"] or ql in x["repo"].lower()]
    return {"total": len(items), "items": items[:limit],
            "hint": "论文库 papers.csv ∩ 本地 Markdown；repo 来自批量抽取映射或 code_urls"}


def start_job(req: ExtractRequest) -> Dict[str, Any]:
    papers = {p["arxiv_id"]: p for p in _load_papers()}
    if req.arxiv_id not in papers:
        raise HTTPException(404, "论文不在库中或缺少本地 Markdown")
    p = papers[req.arxiv_id]
    jid = uuid.uuid4().hex[:10]
    d = (BATCH_DIR / req.arxiv_id if req.mode == "cached" else
         PROJ / "storage_cf/sciforge/web_runs" / jid)
    job = {"id": jid, "arxiv_id": req.arxiv_id, "title": p["title"],
           "repo": p["repo"], "mode": req.mode, "status": "running",
           "created_at": time.time(), "out_dir": str(d)}
    with _LOCK:
        _JOBS[jid] = job

    def worker() -> None:
        try:
            if req.mode == "live":
                from ..po import POGraph
                from ..sciforge.pipeline import run_pipeline
                from ..sciforge.llm_router import LLMRouter
                g = POGraph("web")
                g.node(f"paper:{req.arxiv_id}", "Paper", p["title"][:70])
                g.node(f"algorithm:{req.arxiv_id}", "Algorithm", p["title"][:40])
                g.node(f"benchmark:{req.arxiv_id}", "Benchmark", "primary")
                run_pipeline(arxiv_id=req.arxiv_id,
                             paper_id=f"paper:{req.arxiv_id}", graph=g,
                             repo=p["repo"], out_dir=d,
                             router=LLMRouter(use_polo_fallback=req.use_polo),
                             embed=True)
            if not (d / "PIPELINE_REPORT.json").exists():
                raise RuntimeError("未找到抽取产物；请改用 live 模式真跑")
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
        job["finished_at"] = time.time()

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": jid, "status": "running", "mode": req.mode,
            "arxiv_id": req.arxiv_id}


def get_job(job_id: str) -> Dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job["status"] == "running":
        return {"job_id": job_id, "status": "running",
                "arxiv_id": job["arxiv_id"], "repo": job["repo"],
                "title": job["title"],
                "stages": [{"id": m["id"], "label": m["label"],
                            "status": "running"} for m in STAGE_META],
                "chains": {"nodes": [], "edges": []}, "summary": {}}
    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error"),
                "stages": [], "chains": {"nodes": [], "edges": []}}
    return _build_job_state(job)


def import_to_graph(job_id: str) -> Dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(409, "任务未完成，不能导入图谱")
    from ..po import POGraph
    g = POGraph.load(str(GRAPH_PATH)) if GRAPH_PATH.exists() else POGraph("web")
    before = (len(g.nodes), len(g.assertions))
    chains = _build_job_state(job)["chains"]
    added_n = added_e = 0
    for n in chains["nodes"]:
        if n["id"] not in g.nodes:
            g.node(n["id"], n["type"], n["label"], style=n["style"],
                   provenance="web_extraction", import_job=job_id)
            added_n += 1
    for e in chains["edges"]:
        if e["source"] in g.nodes and e["target"] in g.nodes:
            if g.assert_rel(e["source"], e["target"], e["rel"]):
                added_e += 1
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = IMPORT_DIR / f"graph_after_{job_id}.json"
    g.save(str(out))
    return {"job_id": job_id, "added_nodes": added_n, "added_edges": added_e,
            "graph_before": list(before),
            "graph_after": [len(g.nodes), len(g.assertions)],
            "saved": str(out)}


def extraction_page() -> HTMLResponse:
    p = STATIC_DIR / "extraction.html"
    if not p.exists():
        raise HTTPException(500, "抽取工作台页面缺失")
    return HTMLResponse(p.read_text(encoding="utf-8"))


_V5_ROUTES = [
    ("/api/v5/extraction/papers", list_papers, "GET", True),
    ("/api/v5/extraction/jobs", start_job, "POST", True),
    ("/api/v5/extraction/jobs/{job_id}", get_job, "GET", True),
    ("/api/v5/extraction/jobs/{job_id}/import", import_to_graph, "POST", True),
    ("/api/v5/extraction", extraction_page, "GET", False),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V5_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
