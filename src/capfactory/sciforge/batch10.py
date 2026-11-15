"""10 篇「论文 + 代码仓库」的批量抽取、对齐与图谱建立。

两阶段：

1. **抽取建图**：每篇取 Markdown 的 Abstract/Method/Results + 仓库 AST 符号清单，
   用 polo 大模型按 ``ontology.prompts.build_prompt`` 的源头约束抽
   proposed_methods / baselines / modules / experiments / code_symbols，
   验证符号有效率后落成 POGraph 节点。
2. **对齐填充**：统计图上缺失字段，把「原文片段 + 代码结构 + 当前节点」
   再交给 polo，允许它基于对算法能力的认知补齐模块 IO、Benchmark 契约、
   代码符号对应关系。

所有调用走 ``PoloClient`` 的 ``UsageMeter``，消耗可审计。
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..po import POGraph
from ..utils import parse_llm_json
from ..ingest.pdf import split_sections
from ..ontology.modules import code_structure, _compact_structure, _symbol_index
from ..ontology.prompts import build_prompt
from .polo import PoloClient, UsageMeter

DATA = Path("/home/zengshuxin/xKG-main/data")
MD_DIR = DATA / "docx"
REPO_DIR = DATA / "repos" / "src"


def _norm_repo(s: str) -> str:
    s = (s or "").strip().lower().replace("https://github.com/", "").strip("/")
    return s.replace("/", "__")


def candidates() -> List[Dict[str, Any]]:
    rows = list(csv.DictReader(open(DATA / "papers" / "papers.csv",
                                    encoding="utf-8-sig")))
    repos = {d.lower(): d for d in os.listdir(REPO_DIR)}
    out = []
    for r in rows:
        aid = (r.get("arxiv_id") or "").strip()
        if not aid or not (MD_DIR / f"{aid}.md").exists():
            continue
        for cu in (r.get("code_urls") or "").split(";"):
            n = _norm_repo(cu)
            if not n:
                continue
            hit = next((d for d in repos.values()
                        if n == d or n in d or d in n), None)
            if hit:
                out.append({"arxiv_id": aid, "title": r.get("title") or "",
                            "domain": r.get("domain") or "",
                            "algorithms": r.get("algorithms") or "",
                            "repo": hit, "code_url": cu.strip()})
                break
    return out


def pick_stratified(cands: List[Dict[str, Any]], n: int = 10) -> List[Dict[str, Any]]:
    """按领域分层，保证 10 篇覆盖多个 D 类。"""
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cands:
        by[c["domain"]].append(c)
    picked: List[Dict[str, Any]] = []
    keys = sorted(by, key=lambda k: -len(by[k]))
    while len(picked) < n:
        added = False
        for k in keys:
            if by[k]:
                picked.append(by[k].pop(0))
                added = True
                if len(picked) >= n:
                    break
        if not added:
            break
    return picked


def paper_text(aid: str, *, max_chars: int = 9000) -> str:
    md = (MD_DIR / f"{aid}.md").read_text(encoding="utf-8", errors="replace")
    secs = split_sections(md)
    keep = [f"## {k}\n{v}" for k, v in secs.items()
            if any(x in k.lower() for x in ("abstract", "introduction", "method",
                                            "experiment", "result", "conclusion",
                                            "approach", "model"))]
    return "\n\n".join(keep)[:max_chars] or md[:max_chars]


def extract_one(item: Dict[str, Any], cli: PoloClient, *,
                max_tokens: int = 12000, max_chars: int = 128000,
                paper_type: str = "method") -> Dict[str, Any]:
    aid, repo = item["arxiv_id"], item["repo"]
    struct = code_structure(REPO_DIR / repo, max_symbols=40)
    text = paper_text(aid, max_chars=max_chars)
    secs = split_sections((MD_DIR / f"{aid}.md").read_text(
        encoding="utf-8", errors="replace"))
    ev = [f"section:{aid}:{k}" for k in list(secs)[:12]]
    prompt = build_prompt(paper_text=text,
                          code_symbols=_compact_structure(struct, limit=30),
                          evidence_ids=ev, paper_chars=max_chars,
                          paper_type=paper_type)
    out = cli.chat(prompt, task=f"extract:{aid}", max_tokens=max_tokens)
    raw = parse_llm_json(out) or {}
    if isinstance(raw.get("paper"), dict):
        raw["paper"].setdefault("paper_type", paper_type)

    idx = _symbol_index(struct)
    syms = [s for m in (raw.get("modules") or [])
            for s in (m.get("code_symbols") or []) if isinstance(m, dict)]
    valid = [s for s in syms if s in idx]
    return {"paper": item, "raw": raw, "struct": struct,
            "raw_out_len": len(out), "raw_out_head": out[:160],
            "evidence_ids": ev, "paper_type": paper_type,
            "symbol_stats": {"claimed": len(syms), "valid": len(valid),
                             "hallucinated": [s for s in syms if s not in idx][:6],
                             "rate": round(len(valid) / max(len(syms), 1), 3)},
            "n_sections": len(secs), "prompt_chars": len(prompt)}


# ---------------------------------------------------------------------------
# 建图
# ---------------------------------------------------------------------------
def _n(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:48]


def build_graph(results: List[Dict[str, Any]]) -> Tuple[POGraph, Dict[str, Any]]:
    g = POGraph("batch10::papers_code")
    st: Dict[str, Any] = {"papers": 0, "modules": 0, "methods": 0,
                          "baselines": 0, "metrics": 0, "benchmarks": 0,
                          "code_functions": 0, "questions": 0, "categories": 0,
                          "observations": 0, "leaderboard_entries": 0,
                          "edges": 0, "problems": []}

    def rel(a: str, b: str, r: str) -> None:
        if a and b and a in g.nodes and b in g.nodes and g.assert_rel(a, b, r):
            st["edges"] += 1

    for res in results:
        p, raw, struct = res["paper"], res["raw"], res["struct"]
        aid = p["arxiv_id"]
        pid = f"paper:{aid}"
        g.node(pid, "Paper", p["title"][:80] or aid, title=p["title"],
               arxiv_id=aid, domain_codes=[p["domain"]],
               algo_codes=[x for x in re.findall(r"A\d{2}", p["algorithms"])],
               paper_type=(raw.get("paper") or {}).get("paper_type") or "method")
        st["papers"] += 1
        rid = f"coderepository:{_n(p['repo'])}"
        if rid not in g.nodes:
            g.node(rid, "CodeRepository", p["repo"], repo_name=p["repo"],
                   local_path=str(REPO_DIR / p["repo"]),
                   is_original_repo=True, repo_provenance="paper_declared")
        rel(pid, rid, "HAS_CODE")

        idx = _symbol_index(struct)
        for m in raw.get("proposed_methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            mid = f"algorithm:{_n(m['name'])}"
            if mid not in g.nodes:
                g.node(mid, "Algorithm", m["name"], name=m["name"],
                       kind="method", architecture=m.get("architecture", ""))
                st["methods"] += 1
            rel(pid, mid, "PROPOSES_METHOD")
        for b in raw.get("baselines") or []:
            if not isinstance(b, dict) or not b.get("name"):
                continue
            bid = f"algorithm:{_n(b['name'])}"
            if bid not in g.nodes:
                g.node(bid, "Algorithm", b["name"], name=b["name"],
                       kind="baseline", is_baseline=True)
                st["baselines"] += 1
            rel(pid, bid, "RELATED_TO")

        mods = [m for m in (raw.get("modules") or []) if isinstance(m, dict)]
        for i, m in enumerate(mods):
            name = str(m.get("module_name") or f"module{i}")
            sid = f"algorithmstep:{aid}:{i}:{_n(name)}"
            g.node(sid, "AlgorithmStep", name, module_name=name,
                   mechanism=m.get("mechanism", ""),
                   causal_role=m.get("causal_role", ""),
                   inputs=m.get("inputs") or [], outputs=m.get("outputs") or [],
                   input_schema=m.get("input_schema", ""),
                   output_schema=m.get("output_schema", ""),
                   code_symbols=m.get("code_symbols") or [],
                   equation_ref=m.get("equation_ref", ""),
                   order=m.get("order") or i + 1,
                   grounding_status=m.get("grounding_status", ""),
                   paper_id=pid)
            st["modules"] += 1
            rel(pid, sid, "HAS_MODULE_DETAIL")
            for sym in m.get("code_symbols") or []:
                if sym not in idx:
                    continue
                s = idx[sym]
                fid = f"codefunction:{_n(p['repo'])}:{_n(s['file'])}:{_n(s['name'])}"
                if fid not in g.nodes:
                    g.node(fid, "CodeFunction", s["name"], name=s["name"],
                           signature=s.get("signature", ""),
                           causal_role=s.get("causal_role", ""),
                           module_path=s.get("file", ""))
                    st["code_functions"] += 1
                rel(fid, sid, "IMPLEMENTS_MODULE")

        for exp in raw.get("experiments") or []:
            if not isinstance(exp, dict):
                continue
            bn = str(exp.get("benchmark") or "")
            if bn:
                bid = f"benchmark:{_n(bn)}"
                if bid not in g.nodes:
                    g.node(bid, "Benchmark", bn, name=bn, paper_id=pid)
                    st["benchmarks"] += 1
                rel(pid, bid, "EVALUATED_ON")
            for mt in exp.get("metrics") or []:
                if not isinstance(mt, dict) or not mt.get("name"):
                    continue
                mname = mt["name"]
                mid = f"metric:{_n(mname)}"
                if mid not in g.nodes:
                    g.node(mid, "MetricDefinition", mname, name=mname,
                           direction=mt.get("direction", ""), unit=mt.get("unit", ""))
                    st["metrics"] += 1
                if bn:
                    rel(f"benchmark:{_n(bn)}", mid, "USES_METRIC")
        # ---- 问题层：ResearchQuestion + ProblemCategory ----
        pc_ids: Dict[str, str] = {}
        for i, q in enumerate(raw.get("questions") or []):
            if not isinstance(q, dict) or not q.get("question"):
                continue
            qid = f"researchquestion:{aid}:{i}"
            g.node(qid, "ResearchQuestion", q["question"][:100],
                   question=q["question"], granularity=q.get("granularity") or
                   "paper_specific", paper_id=pid)
            st["questions"] += 1
            rel(pid, qid, "ADDRESSES")
            cat = str(q.get("problem_category") or "").strip()
            if re.fullmatch(r"P\d{2}[a-z]?", cat):
                pcid = f"problemcategory:{cat}"
                if pcid not in g.nodes:
                    g.node(pcid, "ProblemCategory", cat, code=cat, label=cat)
                    st["categories"] += 1
                pc_ids[cat] = pcid
                rel(qid, pcid, "BROADER")
        # 把问题挂到 Benchmark 的 problem_ids
        for b in g.by_type("Benchmark"):
            if b.attrs.get("paper_id") == pid and pc_ids and not b.attrs.get("problem_ids"):
                b.attrs["problem_ids"] = list(pc_ids.values())

        # ---- 观测层：MetricObservation + LeaderboardEntry ----
        obs = list(raw.get("observations") or [])
        for exp in raw.get("experiments") or []:
            if not isinstance(exp, dict):
                continue
            for v in exp.get("values") or []:
                if isinstance(v, dict):
                    obs.append({**v, "benchmark": v.get("benchmark") or
                                exp.get("benchmark", "")})
        for i, o in enumerate(obs):
            if not isinstance(o, dict) or o.get("value") in (None, ""):
                continue
            mname = str(o.get("metric") or "")
            mid = f"metric:{_n(mname)}" if mname else ""
            if mid and mid not in g.nodes:
                g.node(mid, "MetricDefinition", mname, name=mname,
                       unit=o.get("unit", ""), direction=o.get("direction", ""))
                st["metrics"] += 1
            oid = f"metricobservation:{aid}:{i}"
            g.node(oid, "MetricObservation", f"{mname}={o['value']}",
                   value=o["value"], unit=o.get("unit", ""),
                   metric=o.get("metric", ""),
                   metric_definition_id=mid, subject=o.get("subject", ""),
                   stage=o.get("stage", ""), paper_id=pid,
                   evidence_ids=o.get("evidence_ids") or [])
            st["observations"] += 1
            rel(pid, oid, "REPORTS")
            rel(oid, mid, "OF_METRIC")
            bname = str(o.get("benchmark") or "")
            bid = f"benchmark:{_n(bname)}" if bname else ""
            if bid and bid in g.nodes:
                leid = f"leaderboardentry:{aid}:{i}"
                g.node(leid, "LeaderboardEntry", f"{mname}={o['value']}",
                       benchmark_id=bid, metric_id=mid, value=o["value"],
                       unit=o.get("unit", ""), subject=o.get("subject", ""),
                       paper_id=pid, group_key="", rank=1,
                       sota_claimable=False)
                st["leaderboard_entries"] += 1
                rel(bid, leid, "HAS_LEADERBOARD")
                rel(leid, oid, "FROM_OBSERVATION")
                rel(leid, pid, "REPORTED_BY")
    return g, st


def missing_fields(graph: POGraph) -> Dict[str, Any]:
    """统计图上「缺什么」：按类看关键字段的空值率。"""
    watch = {
        "AlgorithmStep": ("mechanism", "inputs", "outputs", "input_schema",
                          "output_schema", "code_symbols", "equation_ref"),
        "Benchmark": ("input_schema", "output_schema", "research_object",
                      "split_type", "metric_ids", "problem_ids"),
        "Algorithm": ("architecture", "algo_codes", "paper_ids"),
        "MetricDefinition": ("direction", "unit", "value_type"),
        "CodeFunction": ("signature", "causal_role", "matched_step_ids"),
        "ResearchQuestion": ("question", "granularity", "evidence_ids"),
        "MetricObservation": ("value", "unit", "metric_definition_id", "evidence_ids"),
        "LeaderboardEntry": ("benchmark_id", "metric_id", "group_key"),
    }
    out: Dict[str, Any] = {}
    for t, fields in watch.items():
        ns = graph.by_type(t)
        if not ns:
            continue
        out[t] = {"n": len(ns),
                  **{f: round(sum(1 for n in ns
                                  if n.attrs.get(f) in (None, "", [], {})) / len(ns), 3)
                     for f in fields}}
    return out
