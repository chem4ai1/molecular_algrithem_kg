"""P1：抽取状态/筛选、原文溯源、编辑输入重抽。"""
from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from .extraction_api import (BATCH_DIR, MD_DIR, PROJ, _load_papers, _read,
                             _prompt_catalog)
from .home_api import _stage_view, STAGE_SPEC

OUT = PROJ / "storage_cf/sciforge/batch_multistage"


def run_state(aid: str) -> Dict[str, Any]:
    d = OUT / aid
    rep = _read(d, "PIPELINE_REPORT.json")
    if not rep:
        return {"status": "pending", "arxiv_id": aid}
    ok = bool(rep.get("ok")) and (rep.get("stages", {})
                                  .get("stage1_vectors", {}).get("blocks", 0) or 0) > 0
    return {"status": "done" if ok else "failed", "arxiv_id": aid,
            "seconds": rep.get("total_seconds"),
            "n_blocks": rep.get("stages", {}).get("stage1_vectors", {}).get("blocks"),
            "summary": rep.get("stages", {}).get("stage2_deepdive", {})
            .get("summary")}


def papers_with_status(status: str = "all", q: str = "", limit: int = 100
                       ) -> Dict[str, Any]:
    items = []
    for p in _load_papers():
        st = run_state(p["arxiv_id"])
        if status != "all" and st["status"] != status:
            continue
        if q and q.lower() not in (
                f"{p['title']} {p['arxiv_id']} {p['repo']}".lower()):
            continue
        items.append({**p, **st})
    order = {"done": 0, "failed": 1, "pending": 2}
    items.sort(key=lambda x: (order.get(x["status"], 3), x["arxiv_id"]))
    return {"total": len(items), "items": items[:limit],
            "counts": {"done": sum(1 for p in _load_papers()
                                   if run_state(p["arxiv_id"])["status"] == "done"),
                       "pending": sum(1 for p in _load_papers()
                                      if run_state(p["arxiv_id"])["status"] == "pending"),
                       "failed": sum(1 for p in _load_papers()
                                     if run_state(p["arxiv_id"])["status"] == "failed")}}


def _sections(aid: str) -> Dict[str, str]:
    from ..ingest.pdf import split_sections
    p = MD_DIR / f"{aid}.md"
    if not p.exists():
        return {}
    return split_sections(p.read_text(encoding="utf-8", errors="replace"))


def source_snippets(aid: str, stage: str = "stage0") -> Dict[str, Any]:
    """各阶段实际读取的原文片段（溯源）。"""
    d = OUT / aid
    plan = _read(d, "STAGE0_HEADING_PLAN.json")
    secs = _sections(aid)
    out: List[Dict[str, Any]] = []
    if stage == "stage0":
        heads = list(plan.get("main_chain") or []) + [
            h for v in (plan.get("blocks") or {}).values() for h in (v or [])]
        out.append({"label": "小标题清单（模型输入）",
                    "text": "\n".join(f"- {h}" for h in heads)})
        for h in plan.get("main_chain") or []:
            out.append({"label": f"主链小节 · {h}",
                        "text": (secs.get(h) or "")[:1400]})
    elif stage == "stage1":
        for kind, hs in (plan.get("blocks") or {}).items():
            for h in hs or []:
                out.append({"label": f"块 · {kind} · {h}",
                            "text": (secs.get(h) or "")[:1600]})
    elif stage == "stage2":
        for kind, hs in (plan.get("blocks") or {}).items():
            for h in hs or []:
                out.append({"label": f"深挖块 · {kind} · {h}",
                            "text": (secs.get(h) or "")[:2200]})
    elif stage == "stage3":
        for h, t in secs.items():
            if re.search(r"reference|bibliograph|引用|参考文献", h, re.I):
                out.append({"label": f"参考文献 · {h}", "text": t[:2400]})
        out.append({"label": "匹配规则", "text": _prompt_catalog()["sources_rule"]})
    return {"arxiv_id": aid, "stage": stage, "snippets": out,
            "n_snippets": len(out)}


class RerunReq(BaseModel):
    arxiv_id: str
    stage: str                    # stage0 | stage2:<kind>
    input_text: str = ""          # 编辑后的输入（原文或标题清单）
    use_polo: bool = True


def rerun_stage(req: RerunReq) -> Dict[str, Any]:
    """用编辑后的输入重抽单个阶段/模块；只覆盖该模块产物，不动其它阶段。"""
    aid = req.arxiv_id
    d = OUT / aid
    if not d.exists() and req.stage == "stage0":
        d.mkdir(parents=True, exist_ok=True)
    from ..sciforge.llm_router import LLMRouter
    from ..sciforge.deepdive import run_module
    from ..sciforge.blocks import screen_headings
    t0 = time.time()
    if req.stage == "stage0":
        headings = [re.sub(r"^\s*[-*]\s*", "", x).strip()
                    for x in (req.input_text or "").splitlines()
                    if x.strip()]
        if len(headings) < 2:
            raise HTTPException(400, "标题清单至少需要 2 行")
        plan = screen_headings(headings, max_tokens=2000,
                               router=LLMRouter(use_polo_fallback=req.use_polo))
        (d / "STAGE0_HEADING_PLAN.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "stage": "stage0", "plan_source": plan.get("source"),
                "main_chain": plan.get("main_chain"), "seconds": round(time.time() - t0, 2)}
    if not req.stage.startswith("stage2:"):
        raise HTTPException(400, "该阶段暂不支持单独重抽")
    kind = req.stage.split(":", 1)[1]
    if kind not in ("related_work", "method", "benchmark_profile",
                    "benchmark_values"):
        raise HTTPException(400, f"未知模块：{kind}")
    text = req.input_text or ""
    if len(text) < 60:
        raise HTTPException(400, "输入原文太短（<60 字符）")
    r = run_module(kind, block_text=text[:40000],
                   router=LLMRouter(use_polo_fallback=req.use_polo))
    name = {"related_work": "STAGE2_related_work.json",
            "method": "STAGE2_method.json",
            "benchmark_profile": "STAGE2_benchmark.json",
            "benchmark_values": "STAGE2_benchmark.json"}[kind]
    path = d / name
    if kind == "benchmark_values":
        prev = _read(d, "STAGE2_benchmark.json")
        data = {**prev, **(r.get("data") or {})}
    elif kind == "benchmark_profile":
        prev = _read(d, "STAGE2_benchmark.json")
        data = {**(r.get("data") or {}), **{k: v for k, v in prev.items()
                                             if k not in (r.get("data") or {})}}
    else:
        data = r.get("data") or {}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return {"ok": r["ok"], "stage": req.stage, "backend": r.get("backend"),
            "n_attempts": r.get("n_attempts"),
            "summary_keys": list(data),
            "seconds": round(time.time() - t0, 2)}


def run_detail(aid: str) -> Dict[str, Any]:
    """已有 run 的只读详情：状态 + 四阶段 + 链（不创建任务、不重抽）。"""
    from .extraction_api import build_chains, _extraction
    st = run_state(aid)
    if st["status"] == "pending":
        raise HTTPException(404, "该论文尚未抽取")
    d = OUT / aid
    stages = [_stage_view(aid, d, i) for i in range(4)]
    chains = build_chains(aid, _extraction(d))
    return {"arxiv_id": aid, "status": st["status"], "seconds": st["seconds"],
            "summary": st.get("summary"),
            "stages": stages, "chains": chains,
            "n_nodes": len(chains["nodes"]), "n_edges": len(chains["edges"])}


def register(app) -> int:
    routes = [
        ("/api/v7/papers", papers_with_status, "GET", True),
        ("/api/v7/run/{aid}", run_detail, "GET", True),
        ("/api/v7/source/{aid}", source_snippets, "GET", True),
        ("/api/v7/rerun", rerun_stage, "POST", True),
    ]
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in routes:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
