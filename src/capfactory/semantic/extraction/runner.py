"""语义层抽取编排：Stage0 指导 + E1–E6 + 重试 + 规则校准 + 报告。

- 切片改为读 blocks.jsonl（按 kind 聚合），不再用标题正则粗切；
- T-Box/A-Box 双指导注入每个 prompt，实例检索让抽取对齐已有图节点；
- paper_type 决定跑哪些阶段；
- E4 表格主路径 + LLM 兜底按 (model, metric, value) 去重；
- E5 的 Tool/Formula 只存 application_hints，语义层不建节点；
- E6 抽算法-算法改进链，只有谱系关系才生成 SUBCLASS_OF 线索。
"""
from __future__ import annotations
import os
import json, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 配置优先（data/extract_target/stages/*.yaml）；无配置时自动退化到 prompts.py。
# 这样新增阶段/字段只改 YAML，不动这里。
try:
    from ..extractspec.render import render, stages
except Exception:  # noqa: BLE001
    from .prompts import render, stages
from .validator import validate, fatal, retry_contract, cross_check
from .guides import classify_paper_type, guide_text

MD_DIR = Path(os.environ.get("CAPFACTORY_PAPERS_DIR", "data/docx"))
BLOCKS_DIR = Path("storage_cf/sciforge/batch_multistage")
PAPERS_CSV = Path(os.environ.get("CAPFACTORY_PAPERS_CSV",
                               "data/papers.csv"))
OUT_DIR = Path("storage_cf/sciforge/semantic_extraction")

KIND_MAP = {"paper": ("abstract", "introduction", "background", "related_work"),
            "algorithm": ("method", "approach", "model", "architecture"),
            "benchmark": ("experiment", "result", "evaluation", "benchmark")}
LINEAGE_KINDS = ("related_work", "introduction", "method", "approach")


def _slices(md: str, arxiv_id: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """按 blocks.jsonl 的 kind 聚合；缺失时回退到原文前 N 字符。"""
    meta: Dict[str, Any] = {"source": "fallback", "n_blocks": 0,
                            "kinds": {}}
    out = {"paper": (md or "")[:6000],
           "algorithm": (md or "")[:12000],
           "benchmark": (md or "")[:12000],
           "lineage": (md or "")[:8000]}
    p = BLOCKS_DIR / arxiv_id / "blocks.jsonl"
    if not p.exists():
        return out, meta
    buckets: Dict[str, List[str]] = {k: [] for k in KIND_MAP}
    buckets["lineage"] = []
    counts: Dict[str, int] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            b = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        kind = str(b.get("kind") or "").lower()
        text = str(b.get("text") or "")
        counts[kind] = counts.get(kind, 0) + 1
        for key, kws in KIND_MAP.items():
            if any(k in kind for k in kws):
                buckets[key].append(text)
        if any(k in kind for k in LINEAGE_KINDS):
            buckets["lineage"].append(text)
    for k, parts in buckets.items():
        if parts:
            out[k] = "\n\n".join(parts)[:16000]
    # E1 需要摘要/引言；blocks 若没有这两类，用原文前段补足
    if len(out["paper"]) < 3000 and md:
        out["paper"] = ((md or "")[:6000] + "\n\n" + out["paper"])[:10000]
    meta = {"source": "blocks.jsonl", "n_blocks": sum(counts.values()),
            "kinds": counts,
            "lengths": {k: len(v) for k, v in out.items()}}
    return out, meta


def _csv_domain(aid: str) -> str:
    if not PAPERS_CSV.exists():
        return ""
    import csv
    with PAPERS_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r.get("arxiv_id") or "").strip() == aid:
                return (r.get("domain") or "").strip()
    return ""


def _ast_symbols(graph: Any) -> set:
    return {n.attrs.get("name") or n.label
            for n in graph.by_type("CodeFunction")} if graph else set()


def _table_results(md: str, aid: str) -> List[Dict[str, Any]]:
    try:
        from ...sciforge.table_extract import parse_tables
        from ...sciforge.leaderboard import rows_from_tables
        return rows_from_tables(parse_tables(md),
                                paper_id="paper:" + aid, benchmark_id="")
    except Exception:  # noqa: BLE001
        return []


def _dedup_results(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """E4 去重：按 (model, metric, value)，表格主路径优先。"""
    seen, out = set(), []
    for r in rows or []:
        key = (str(r.get("model_name") or r.get("model") or "").strip().lower(),
               str(r.get("metric_name") or r.get("metric") or "").strip().lower(),
               str(r.get("value_raw") or r.get("value") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _call_stage(stage: str, *, chat_fn, sl: Dict[str, str],
                title: str, ast: set, guide: str,
                retries: int = 3,
                tolerate_empty: bool = False
                ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from ...llm.backends import chat as _chat
    from ...utils import parse_llm_json
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    key = {"E1_paper": "paper", "E2_algorithm": "algorithm",
           "E3_benchmark": "benchmark", "E4_values": "benchmark",
           "E5_relations": "algorithm", "E6_lineage": "lineage"}[stage]
    text = sl[key]
    meta: Dict[str, Any] = {"attempts": 0, "issues": [], "fatal": []}
    for attempt in range(retries):
        meta["attempts"] += 1
        prompt = (render(stage, title=title, paper_text=text,
                         code_symbols=", ".join(sorted(ast)[:60]) or "(无)",
                         rule_hints="")
                  + "\n" + guide)
        if attempt:
            prompt += "\n" + retry_contract(stage)
        try:
            raw = fn(prompt, max_tokens=16384, timeout=600)
            out, issues = validate(stage, parse_llm_json(raw),
                                   source_text=text)
        except Exception as exc:  # noqa: BLE001
            out, issues = {}, [type(exc).__name__ + ":" + str(exc)[:80]]
        meta["issues"] = issues
        bad = fatal(issues)
        # dataset_benchmark / theory / survey 论文可能确实没有新算法或基准；
        # 「核心为空」不算失败，避免把合理空结果判成整篇失败。
        if tolerate_empty and bad and all(
                str(x).startswith("missing:") for x in bad):
            meta["tolerated_empty"] = bad
            bad = []
        meta["fatal"] = bad
        if not bad:
            return out, meta
    return {}, meta


E4_SKIP_TYPES = ("theory", "survey")


def should_skip_e4(ptype: Dict[str, Any], n_table_rows: int, *,
                   run_stages: Any = None, enabled: bool = True,
                   min_table_rows: int = 40) -> bool:
    """E4 是「表格之外数值」的 LLM 兜底，733 次调用里 669 次零产出。
    两条跳过规则：
      A) 理论/综述且有表格行 → 跳过（防御性；当前阶段计划本就不含 E4）
      B) 表格已产出 >= min_table_rows 行 → 跳过（主要收益）
    实测阈值 40：省 113 次调用，只损失 37 行兜底（占 17810 行的 0.2%）。
    设 min_table_rows 为一个极大值即可完全退回旧行为。
    """
    if not enabled or run_stages is not None:
        return False
    if ptype["paper_type"] in E4_SKIP_TYPES and n_table_rows > 0:
        return True
    return n_table_rows >= min_table_rows


def run_extraction(arxiv_id: str, *, md: str = "", graph: Any = None,
                   chat_fn: Any = None, persist: bool = True,
                   run_stages: Optional[List[str]] = None,
                   retries: int = 3, use_guide: bool = True,
                   use_llm_classify: bool = True,
                   skip_e4_when_table_covered: bool = True,
                   e4_skip_min_table_rows: int = 40
                   ) -> Dict[str, Any]:
    t0 = time.time()
    if not md:
        p = MD_DIR / (arxiv_id + ".md")
        md = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    sl, slice_meta = _slices(md, arxiv_id)
    ast = _ast_symbols(graph)
    # 分类兜底要用真正会调 LLM 的函数（之前传 None，导致兜底从未生效）
    from ...llm.backends import chat as _chat
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    title = ""
    for _line in (md or "").splitlines()[:20]:
        _t = _line.strip().lstrip("#").strip()
        if len(_t) > 12:
            title = _t[:200]
            break
    ptype = classify_paper_type(sl["paper"][:1200], graph=graph,
                                chat_fn=fn if use_llm_classify else None,
                                title=title, use_llm=use_llm_classify)
    # 表格是确定性的，提前算一次供 E4 跳过判断与结果合并复用
    tbl = _table_results(md, arxiv_id)
    STAGE_SLICE = {"E1_paper": "paper", "E2_algorithm": "algorithm",
                   "E3_benchmark": "benchmark", "E4_values": "benchmark",
                   "E5_relations": "algorithm", "E6_lineage": "lineage"}
    want = run_stages or [s for s in stages() if s in ptype["stages"]]
    rep: Dict[str, Any] = {
        "arxiv_id": arxiv_id, "stages": {}, "paper_type": ptype,
        "slice_meta": slice_meta, "n_ast_symbols": len(ast),
        "guide_chars": 0}
    # E4 是「表格之外的数值」的 LLM 兜底：实测 theory/survey 在有表格行时
    # 兜底产出恒为 0，跳过可省一次 LLM 调用。显式 run_stages 时不跳过。
    if ("E4_values" in want
            and should_skip_e4(ptype, len(tbl), run_stages=run_stages,
                               enabled=skip_e4_when_table_covered,
                               min_table_rows=e4_skip_min_table_rows)):
        want = [x for x in want if x != "E4_values"]
        rep["stages"]["E4_values"] = {
            "ok": True, "skipped": True, "reason": "table_covered",
            "n_table_rows": len(tbl), "attempts": 0,
            "issues": [], "fatal": [], "data": {"model_results": []}}
        rep["e4_skipped"] = True
    tolerant = ptype["paper_type"] in ("dataset_benchmark", "theory",
                                        "survey", "application")
    for st in want:
        key = STAGE_SLICE.get(st, "paper")
        stage_guide = (guide_text(sl[key][:4000], graph, ptype, stage=st)
                       if use_guide else "")
        out, meta = _call_stage(st, chat_fn=chat_fn, sl=sl, title=arxiv_id,
                                ast=ast, guide=stage_guide, retries=retries,
                                tolerate_empty=tolerant)
        rep["guide_chars"] += len(stage_guide)
        rep["stages"][st] = {"ok": not meta["fatal"], **meta,
                             "n_fields": len(out), "data": out}
    # 规则校准
    e1 = rep["stages"].get("E1_paper", {}).get("data") or {}
    rep["domain_calibrated"] = _csv_domain(arxiv_id)
    if rep["domain_calibrated"]:
        e1["domain_code"] = rep["domain_calibrated"]
    # E4：表格主路径 + LLM 兜底 + 去重
    e4 = rep["stages"].get("E4_values", {}).get("data") or {}
    rows = _dedup_results(tbl + (e4.get("model_results") or []))
    rep["model_results"] = {"table": len(tbl),
                            "llm_fallback": len(e4.get("model_results") or []),
                            "deduplicated": len(rows), "rows": rows}
    # E5：只存应用层线索，语义层不建 Tool/Formula 节点
    e5 = rep["stages"].get("E5_relations", {}).get("data") or {}
    rep["application_hints"] = {
        "tools_formulas": e5.get("relations") or [],
        "note": "节点化留给应用层任务（复现/生成论文时按任务构建）"}
    # E6：算法-算法改进链，只有谱系类才生成 SUBCLASS_OF 线索
    e6 = rep["stages"].get("E6_lineage", {}).get("data") or {}
    rep["lineage"] = {
        "all": e6.get("lineage") or [],
        "subclass_of": [x for x in (e6.get("lineage") or [])
                        if x["kind"] in ("extends", "replaces", "improves")],
        "compared_only": [x for x in (e6.get("lineage") or [])
                          if x["kind"] == "compared_with"]}
    # 跨阶段检查
    e2 = rep["stages"].get("E2_algorithm", {}).get("data") or {}
    rep["cross_check"] = cross_check("E2_algorithm", e2, ast_symbols=ast)
    mods = {m["name"] for a in (e2.get("algorithms") or [])
            for m in (a.get("modules") or [])}
    rep["cross_check"] += cross_check("E5_relations", e5,
                                      module_names=mods)
    # 标准范式层：NER → 槽位规范化 → 关系逐字落地 → 模块追踪 → 槽位审计
    try:
        from .paradigm import apply_paradigm
        apply_paradigm(rep, graph=graph, slices=sl, ast_symbols=ast,
                       full_text=md)
    except Exception as exc:  # noqa: BLE001
        rep["paradigm_error"] = type(exc).__name__ + ":" + str(exc)[:100]
    rep["ok"] = all(v["ok"] for v in rep["stages"].values())
    rep["seconds"] = round(time.time() - t0, 2)
    if persist:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        import os
        _p = OUT_DIR / (arxiv_id + ".json")
        _tmp = _p.with_suffix(".tmp")
        _tmp.write_text(
            json.dumps(rep, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        os.replace(_tmp, _p)  # 原子写，避免后台批跑时读到半文件
    return rep
