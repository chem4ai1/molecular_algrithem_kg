"""V3 步骤2：按**三类根族**延伸的触手抽取（替换旧平铺三类触手）。

根族：Paper → hypothesis / solution_use；
     Algorithm → step_decomposition（步骤+模块+公式+工具）/ code_grounding；
     Benchmark → evaluation_values / data_profile（输入输出形式与对象等）。
不调用 LLM API；每个新节点带 source（md 行号或 AST 文件）。
"""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..ingest.pdf import split_sections
from ..ontology.schema_v3 import ROOT_FAMILIES
from ..ontology.chains import TENTACLE_SPECS

ROOT = Path("/home/zengshuxin/xKG-main")
MD_DIR = ROOT / "data/docx"
REPO_DIR = ROOT / "data/repos/src"

_METRIC_WORDS = ("validity", "uniqueness", "novelty", "diversity", "qed", "sas",
                 "logp", "rmsd", "jsd", "accuracy", "precision", "recall",
                 "f1", "auc", "mae", "rmse", "success", "hit", "affinity",
                 "coverage", "improvement", "error", "score", "rate", "time",
                 "wasserstein", "r2")
_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?%?"
_TOOL_WORDS = ("rdkit", "force field", "gmm", "transformer", "pytorch",
               "openbabel", "scipy", "numpy", "jensen", "bce", "smiles",
               "sssr", "canonicalization", "monte carlo")
_FORM_WORDS = ("smiles", "3d", "coordinate", "vector", "embedding", "graph",
               "sequence", "distribution", "scalar")
_OBJECT_WORDS = ("molecule", "fragment", "protein", "pocket", "property",
                 "distribution", "vocabulary", "vector", "ligand")


def _sections(md_text: str) -> Dict[str, str]:
    return split_sections(md_text or "")


def _section_text(sections: Dict[str, str], keys: Sequence[str],
                  limit: int = 20000) -> str:
    return "\n\n".join(v for k, v in sections.items()
                       if any(x in k.lower() for x in keys))[:limit]


def _method_text(sections: Dict[str, str], limit: int = 20000) -> str:
    return _section_text(sections, ("method", "approach", "model", "architecture",
                                    "training", "sampling", "rollout",
                                    "representation", "3.", "4."), limit)


def _tokens(s: str) -> set:
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s or "")
    words = re.findall(r"[a-z][a-z0-9_]{1,}", split.lower())
    stop = {"the", "and", "for", "with", "from", "that", "this", "of", "to"}
    out = set()
    for w in words:
        if w in stop:
            continue
        out.add(w)
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                out.add(w[:-len(suf)])
    return out


def _best_match(anchor: str, candidates: Sequence[Dict[str, Any]],
                field: str) -> Optional[Dict[str, Any]]:
    a = _tokens(anchor)
    best, score = None, 0
    for c in candidates:
        n = len(a & _tokens(str(c.get(field, ""))))
        if n > score:
            best, score = c, n
    return best if score >= 1 else None


def _markdown_tables(text: str) -> List[Dict[str, Any]]:
    tables, lines = [], (text or "").splitlines()
    i = 0
    while i < len(lines) - 1:
        if "|" in lines[i] and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and "|" in lines[j]:
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                nums = [(h, c) for h, c in zip(header, cells)
                        if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?%?", c)]
                if nums:
                    rows.append({"line": j + 1, "cells": cells, "numeric": nums})
                j += 1
            if rows:
                tables.append({"line": i + 1, "header": header, "rows": rows[:8]})
            i = j
        else:
            i += 1
    return tables


def _numbered_steps(text: str) -> List[Dict[str, Any]]:
    out = []
    for m in re.finditer(r"(?:^|\n)\s*(?:\(?(\d{1,2})[.)]|Step\s+(\d+))\s+"
                         r"([^\n]{12,240})", text or "", re.I):
        out.append({"index": int(m.group(1) or m.group(2)),
                    "text": m.group(3).strip()[:200], "offset": m.start()})
    return out[:12]


def metric_mentions(text: str, *, max_items: int = 40) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pat = re.compile(r"\b(" + "|".join(_METRIC_WORDS) + r")\b[^.\n\d=]{0,45}?"
                     r"(?:\(|\bis\b|\bof\b|=|:)\s*(" + _NUM + r")\s*%?", re.I)
    bad = re.compile(r"dropout|learning rate|warmup|epoch|batch size|\[\d+\]|"
                     r"see (?:the )?(?:SI|supplement)|configuration|we set|"
                     r"number of|layers|heads|temperature|\bseed\b", re.I)
    for ln, line in enumerate((text or "").splitlines(), 1):
        if bad.search(line):
            continue
        for m in pat.finditer(line):
            word, val = m.group(1).lower(), m.group(2)
            if not re.search(r"[.%eE]", val) and len(val) <= 2:
                continue
            out.append({"metric": word, "value": val, "line": ln,
                        "context": line.strip()[:160],
                        "source_kind": "metric_sentence"})
            if len(out) >= max_items:
                return out
    return out


def flattened_tables(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"\bTable\s+(\d+)\s*[:.)]", line, re.I)
        if not m:
            continue
        block = "\n".join(lines[i:i + 14])
        vals = re.findall(r"\b(" + _NUM + r")\b", block)
        words = [w for w in _METRIC_WORDS if re.search(r"\b" + w + r"\b", block, re.I)]
        if vals and words:
            out.append({"table": int(m.group(1)), "line": i + 1,
                        "caption": line.strip()[:120], "metric_words": words[:6],
                        "values": vals[:8], "source_kind": "flattened_table"})
    return out[:12]


def _ast_functions(repo: str) -> List[Dict[str, str]]:
    from ..ontology.modules import code_structure
    rp = REPO_DIR / repo
    if not repo or not rp.exists():
        return []
    st = code_structure(rp, max_symbols=40)
    return [{"name": str(s.get("name") or ""), "file": str(s.get("file") or ""),
             "signature": str(s.get("signature") or "")}
            for s in (st.get("symbols") or []) if s.get("name")]


def _hypothesis_sentences(text: str) -> List[Dict[str, Any]]:
    cues = re.compile(r"\b(?:we (?:hypothesize|argue|posit|contend|believe|"
                      r"expect|assume)|our (?:view|hypothesis|assumption|"
                      r"claim|position) is|one way to|we note that|"
                      r"is (?:essential|critical)|remains? (?:a|an|the))\b", re.I)
    out = []
    for i, line in enumerate((text or "").splitlines(), 1):
        for sent in re.split(r"(?<=[.!?])\s+", line):
            s = sent.strip()
            if 35 < len(s) < 260 and cues.search(s):
                kind = ("stance" if re.search(r"we note|exclude|not directly", s, re.I)
                        else "assumption" if re.search(r"assum|hypothes", s, re.I)
                        else "claim")
                out.append({"statement": s[:240], "kind": kind, "line": i})
    return out[:8]


def _formula_signals(text: str) -> List[Dict[str, Any]]:
    out = []
    for m in re.finditer(r"\((\d{1,2})\)\s*\n?([^\n]{0,180})", text or "", re.M):
        if int(m.group(1)) > 12:
            continue
        ctx = m.group(2).strip()
        if not re.search(r"=|where|defined as", ctx, re.I):
            continue
        out.append({"equation_no": m.group(1),
                    "latex": ctx[:160], "offset": m.start()})
    return out[:6]


def _tool_signals(text: str) -> List[str]:
    low = (text or "").lower()
    return [w for w in _TOOL_WORDS if w in low][:8]


def _data_profile_signals(text: str) -> Dict[str, Any]:
    low = (text or "").lower()
    forms = [w for w in _FORM_WORDS if re.search(r"\b" + re.escape(w) + r"\b", low)]
    objects = [w for w in _OBJECT_WORDS if re.search(r"\b" + re.escape(w) + r"\b", low)]
    m_budget = re.search(r"(?:approximately|about|~)\s*([\d,]+)\s*"
                         r"(?:generated\s*)?molecules", low)
    m_repeat = re.search(r"(\d+)\s*times per target", low)
    m_range = re.search(r"µ\s*±\s*2σ|mu\s*\+\-\s*2\s*sigma", low)
    baselines = [b for b in ("hiervae", "gdss", "mars", "targetdiff") if b in low]
    return {"input_forms": forms[:4], "output_forms": forms[:4],
            "input_objects": objects[:4], "output_objects": objects[:4],
            "sample_budget": m_budget.group(1) if m_budget else "",
            "repeats": m_repeat.group(1) if m_repeat else "",
            "threshold": "µ±2σ" if m_range else "",
            "baseline_methods": baselines,
            "metric_family": [w for w in _METRIC_WORDS if w in low][:6],
            "leakage_risk": "conditioning vectors sampled from training GMM"
            if "gmm" in low else ""}


def run_tentacles(graph: Any, *, papers: Sequence[Tuple[str, str]],
                  repo_by_aid: Optional[Dict[str, str]] = None,
                  out_dir: Optional[str | Path] = None,
                  write_back: bool = True) -> Dict[str, Any]:
    """按根族执行 6 类触手；返回可落盘报告，可选写回图。"""
    import json
    repo_by_aid = repo_by_aid or {}
    rep: Dict[str, Any] = {"papers": {}, "totals": defaultdict(int),
                           "root_families": list(ROOT_FAMILIES)}

    def node(nid: str, typ: str, label: str, **attrs: Any) -> bool:
        if nid in graph.nodes:
            return False
        if write_back:
            graph.node(nid, typ, label, **attrs)
        return True

    def edge(a: str, b: str, rel: str) -> bool:
        if a not in graph.nodes or b not in graph.nodes or not write_back:
            return False
        return graph.assert_rel(a, b, rel)

    for aid, pid in papers:
        f = MD_DIR / f"{aid}.md"
        if not f.exists():
            continue
        md = f.read_text(encoding="utf-8", errors="replace")
        secs = _sections(md)
        intro = _section_text(secs, ("introduction", "abstract", "conclusion"), 12000)
        method = _method_text(secs)
        exp = _section_text(secs, ("experiment", "benchmark", "setup", "result",
                                   "table", "calibration", "5.", "6."), 20000)
        per: Dict[str, Any] = {k: [] for k in TENTACLE_SPECS}
        per["sources"] = {}

        # 三类根
        out = {}
        for a in graph.assertions:
            out.setdefault(a.source, []).append(a)
        def targets(rel: str, typ: str) -> List[str]:
            return sorted({e.target for e in out.get(pid, [])
                           if e.relation == rel and e.target in graph.nodes and
                           graph.nodes[e.target].type == typ})[:4]
        algos = targets("PROPOSES_METHOD", "Algorithm")
        benches = targets("EVALUATED_ON", "Benchmark")
        rqs = targets("ADDRESSES", "ResearchQuestion")
        metric_defs = [n.id for n in graph.by_type("MetricDefinition")]
        data_forms = {n.label: n.id for n in graph.by_type("DataForm")}
        robjs = {n.label: n.id for n in graph.by_type("ResearchObject")}

        # ---------- Paper 根 ----------
        hyps = _hypothesis_sentences(intro)
        for i, h in enumerate(hyps[:5]):
            hid = f"hypothesis:tentacle:{aid}:{i}"
            if node(hid, "Hypothesis", h["statement"][:70],
                    statement=h["statement"], kind=h["kind"], paper_id=pid,
                    quote=h["statement"][:200],
                    source=f"data/docx/{aid}.md#L{h['line']}",
                    provenance="tentacle"):
                rep["totals"]["new_nodes"] += 1
            edge(pid, hid, "DECLARES_HYPOTHESIS")
            for b in benches[:1]:
                edge(b, hid, "TESTS_HYPOTHESIS")
            rep["totals"]["new_edges"] += 1
            per["paper.hypothesis"].append({
                "id": hid, "kind": h["kind"], "line": h["line"],
                "statement": h["statement"][:110]})
        # C8：算法如何被用于解决问题
        ma_id = f"methodapplication:tentacle:{aid}:0"
        if algos and rqs:
            if node(ma_id, "MethodApplication", f"use:{aid}",
                    paper_id=pid, task_family="solution_application",
                    source=f"data/docx/{aid}.md#introduction+experiments",
                    provenance="tentacle"):
                rep["totals"]["new_nodes"] += 1
            edge(rqs[0], algos[0], "ADDRESSED_BY")
            edge(algos[0], ma_id, "PARTICIPATES_IN")
            edge(ma_id, rqs[0], "APPLIES_TO")
            rep["totals"]["new_edges"] += 3
            per["paper.solution_use"].append({
                "problem": rqs[0], "algorithm": algos[0],
                "application": ma_id, "edges": ["ADDRESSED_BY",
                                               "PARTICIPATES_IN", "APPLIES_TO"]})

        # ---------- Algorithm 根：拆解 + 模块/公式/工具 + 代码对应 ----------
        steps = [e.target for e in out.get(pid, [])
                 if e.relation == "HAS_MODULE_DETAIL" and
                 e.target in graph.nodes and
                 graph.nodes[e.target].type == "AlgorithmStep"]
        formulas = _formula_signals(method)
        tools = _tool_signals(method)
        for a_id in algos:
            for i, sid in enumerate(steps[:6]):
                edge(a_id, sid, "HAS_STEP")
                if formulas:
                    fo = formulas[i % len(formulas)]
                    fid = f"formula:tentacle:{aid}:{i}"
                    if node(fid, "Formula", f"eq({fo['equation_no']})",
                            latex=fo["latex"], equation_no=fo["equation_no"],
                            source=f"data/docx/{aid}.md#method:eq{fo['equation_no']}",
                            provenance="tentacle"):
                        rep["totals"]["new_nodes"] += 1
                    edge(sid, fid, "HAS_FORMULA")
                if tools:
                    tl = tools[i % len(tools)]
                    tid = f"tool:tentacle:{aid}:{i}"
                    if node(tid, "Tool", tl, name=tl, kind="library_or_force_field",
                            source=f"data/docx/{aid}.md#method:{tl}",
                            provenance="tentacle"):
                        rep["totals"]["new_nodes"] += 1
                    edge(sid, tid, "USES_TOOL")
                rep["totals"]["new_edges"] += 1
                per["algorithm.step_decomposition"].append({
                    "algorithm": a_id, "step": sid,
                    "formula": formulas[i % len(formulas)]["equation_no"]
                    if formulas else None,
                    "tool": tools[i % len(tools)] if tools else None})
        funcs = _ast_functions(repo_by_aid.get(aid, ""))
        for i, sid in enumerate(steps[:6]):
            label = str(graph.nodes[sid].label)
            hit = _best_match(label, funcs, "name")
            if not hit:
                per["algorithm.code_grounding"].append({
                    "step": sid, "function": None, "note": "no AST symbol matched"})
                continue
            fid = f"codefunction:tentacle:{aid}:{i}"
            if node(fid, "CodeFunction", hit["name"], file=hit["file"],
                    repo=repo_by_aid.get(aid, ""),
                    source=f"AST:{hit['file']}:{hit['name']}",
                    provenance="tentacle"):
                rep["totals"]["new_nodes"] += 1
            edge(sid, fid, "REALIZED_BY")
            mods = [n.id for n in graph.by_type("CodeModule")
                    if n.attrs.get("repo") == repo_by_aid.get(aid, "")][:1]
            for m in mods:
                edge(sid, m, "HAS_MODULE_IMPL")
            rep["totals"]["new_edges"] += 1
            per["algorithm.code_grounding"].append({
                "step": sid, "function": hit["name"], "file": hit["file"],
                "edges": ["REALIZED_BY"]})

        # ---------- Benchmark 根：评测值 + 数据契约 ----------
        mentions = metric_mentions(md)
        primary_bench = benches[:1]
        for b_id in benches:
            for a_id in algos[:1]:
                edge(b_id, a_id, "EVALUATES_METHOD")
            if b_id not in primary_bench:
                continue
            for i, men in enumerate(mentions[:8]):
                mid = next((m for m in metric_defs
                            if men["metric"] in m.lower()),
                           metric_defs[0] if metric_defs else "")
                if not mid:
                    continue
                oid = f"observation:tentacle:{aid}:{i}"
                if node(oid, "Observation", f"{men['metric']}={men['value']}",
                        value=men["value"], metric=men["metric"],
                        source=f"data/docx/{aid}.md#L{men['line']}",
                        quote=men["context"], provenance="tentacle"):
                    rep["totals"]["new_nodes"] += 1
                edge(b_id, oid, "REPORTS_VALUE")
                edge(oid, mid, "OF_METRIC")
                rep["totals"]["new_edges"] += 2
                per["benchmark.evaluation_values"].append({
                    "benchmark": b_id, "metric": men["metric"],
                    "value": men["value"], "line": men["line"],
                    "source": "metric_sentence"})
            prof = _data_profile_signals(exp)
            did = f"datacontract:tentacle:{aid}"
            if node(did, "DataContract", f"contract:{aid}",
                    input_form=",".join(prof["input_forms"]),
                    output_form=",".join(prof["output_forms"]),
                    input_object=",".join(prof["input_objects"]),
                    output_object=",".join(prof["output_objects"]),
                    sample_budget=prof["sample_budget"] or prof["repeats"],
                    threshold=prof["threshold"],
                    metric_family=",".join(prof["metric_family"]),
                    baseline_methods=prof["baseline_methods"],
                    leakage_risk=prof["leakage_risk"],
                    source=f"data/docx/{aid}.md#experiments",
                    provenance="tentacle"):
                rep["totals"]["new_nodes"] += 1
            edge(b_id, did, "HAS_DATA_CONTRACT")
            for key, rel, pool in (
                    ("input_forms", "HAS_INPUT_FORM", data_forms),
                    ("output_forms", "HAS_OUTPUT_FORM", data_forms),
                    ("input_objects", "HAS_INPUT_OBJECT", robjs),
                    ("output_objects", "HAS_OUTPUT_OBJECT", robjs)):
                for w in prof[key][:2]:
                    tid = pool.get(w)
                    if not tid:
                        kind = "DataForm" if "form" in key else "ResearchObject"
                        tid = f"{kind.lower()}:tentacle:{aid}:{w}"
                        if node(tid, kind, w, form=w,
                                source=f"data/docx/{aid}.md#experiments",
                                provenance="tentacle"):
                            rep["totals"]["new_nodes"] += 1
                    edge(b_id, tid, rel)
                    rep["totals"]["new_edges"] += 1
            per["benchmark.data_profile"].append({
                "benchmark": b_id, "contract": did, **prof})

        # 兼容旧报告键
        per["algorithm"] = per["algorithm.code_grounding"]
        per["metric_table"] = per["benchmark.evaluation_values"]
        per["algorithm_step"] = per["algorithm.step_decomposition"]
        per["table_signals"] = [{"table": t["table"], "line": t["line"]}
                                for t in flattened_tables(md)[:3]]
        per["sources"] = {"md_chars": len(md),
                          "n_flat_tables": len(flattened_tables(md)),
                          "n_metric_mentions": len(mentions),
                          "n_hypotheses": len(hyps), "n_formulas": len(formulas),
                          "n_tools": len(tools), "n_steps": len(steps),
                          "n_ast_functions": len(funcs),
                          "n_anchor_steps": len(steps),
                          "n_benchmarks": len(benches)}
        rep["papers"][aid] = per

    rep["totals"] = dict(rep["totals"])
    rep["n_papers"] = len(rep["papers"])
    if out_dir:
        import json as _json
        o = Path(out_dir)
        o.mkdir(parents=True, exist_ok=True)
        (o / "TENTACLE_REPORT.json").write_text(
            _json.dumps(rep, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    return rep
