"""图谱可查询性 / 推理能力 + 10 篇 D/A 与基准覆盖分析。

不问「图有多大」，而问「这张图能回答什么问题」：把常见研究查询写成
**路径模板**，逐篇算可回答率；再检查三类推理是否有足够的共享节点支撑。
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ..po import POGraph

PAPERS_CSV = "/home/zengshuxin/xKG-main/data/papers/papers.csv"


def _out(graph: POGraph, nid: str, rel: str) -> List[str]:
    return [e.target for e in graph.outgoing(nid, rel)]


def _in(graph: POGraph, nid: str, rel: str) -> List[str]:
    return [e.source for e in graph.incoming(nid, rel)]


def query_templates(graph: POGraph) -> Dict[str, Any]:
    papers = [n.id for n in graph.by_type("Paper")]
    checks: Dict[str, List[str]] = defaultdict(list)
    for p in papers:
        if _out(graph, p, "ADDRESSES"):
            checks["论文要回答什么问题"].append(p)
        if _out(graph, p, "PROPOSES_METHOD"):
            checks["论文提出什么方法"].append(p)
        if _out(graph, p, "HAS_MODULE_DETAIL"):
            checks["方法由哪些模块组成"].append(p)
        mods = _out(graph, p, "HAS_MODULE_DETAIL")
        if mods and any(_in(graph, m, "IMPLEMENTS_MODULE") for m in mods):
            checks["模块对应哪些代码符号"].append(p)
        if _out(graph, p, "EVALUATED_ON"):
            checks["在什么基准上评测"].append(p)
        benches = _out(graph, p, "EVALUATED_ON")
        if benches and any(_out(graph, b, "USES_METRIC") for b in benches):
            checks["基准用什么指标"].append(p)
        if _out(graph, p, "REPORTS"):
            checks["报告了哪些观测值"].append(p)
        les = [e.target for e in graph.assertions
               if e.relation == "REPORTED_BY" and e.target == p]
        if les:
            checks["能否进榜单比较"].append(p)
        if _out(graph, p, "HAS_CODE"):
            checks["代码仓库在哪"].append(p)
    rows = [{"query": k, "answerable": len(v), "total": len(papers),
             "rate": round(len(v) / max(len(papers), 1), 3)}
            for k, v in checks.items()]
    rows.sort(key=lambda x: x["rate"])
    return {"papers": len(papers), "queries": rows,
            "overall_rate": round(sum(r["answerable"] for r in rows) /
                                  max(len(rows) * len(papers), 1), 3)}


def reasoning_capabilities(graph: POGraph) -> Dict[str, Any]:
    """三类推理是否有共享节点支撑。"""
    # ① 同类方法对比：同一算法族下 ≥2 个 Algorithm
    fam_papers: Dict[str, set] = defaultdict(set)
    for a in graph.assertions:
        if a.relation == "PROPOSES_METHOD":
            fam_papers[a.target].add(a.source)
    # 用 Paper.algo_codes 近似族
    algo_groups: Dict[str, set] = defaultdict(set)
    for p in graph.by_type("Paper"):
        for c in p.attrs.get("algo_codes") or []:
            algo_groups[str(c)].add(p.id)
    shared_algo = {k: len(v) for k, v in algo_groups.items() if len(v) >= 2}

    # ② 同基准 SOTA：同一 benchmark 下 ≥2 条 LeaderboardEntry
    lb: Dict[str, List[str]] = defaultdict(list)
    for e in graph.assertions:
        if e.relation == "HAS_LEADERBOARD":
            lb[e.source].append(e.target)
    sota_ready = {k: len(v) for k, v in lb.items() if len(v) >= 2}

    # ③ 问题→方法推荐：同一 ProblemCategory 下 ≥2 篇论文
    cat_papers: Dict[str, set] = defaultdict(set)
    for q in graph.by_type("ResearchQuestion"):
        cats = _out(graph, q.id, "BROADER")
        papers = _in(graph, q.id, "ADDRESSES")
        for c in cats:
            for p in papers:
                cat_papers[c].add(p)
    problem_ready = {k: len(v) for k, v in cat_papers.items() if len(v) >= 2}

    return {
        "same_family_method_comparison": {
            "possible": bool(shared_algo), "groups": shared_algo,
            "note": "需要 ≥2 篇论文共享同一算法族"},
        "same_benchmark_sota": {
            "possible": bool(sota_ready), "groups": sota_ready,
            "note": "需要同一 Benchmark 下 ≥2 条 LeaderboardEntry + 可比键"},
        "problem_to_method_recommendation": {
            "possible": bool(problem_ready), "groups": problem_ready,
            "note": "需要同一 ProblemCategory 下 ≥2 篇论文"},
        "code_algorithm_grounding": {
            "links": sum(1 for a in graph.assertions
                         if a.relation in ("IMPLEMENTS_MODULE", "REALIZES")),
            "note": "模块↔代码符号对齐数量"},
    }


def da_distribution(graph: POGraph, *, selected: Sequence[str] = ()
                    ) -> Dict[str, Any]:
    with open(PAPERS_CSV, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    by_id = {r.get("arxiv_id"): r for r in rows}
    dom, algo, pairs = Counter(), Counter(), Counter()
    for p in graph.by_type("Paper"):
        aid = str(p.attrs.get("arxiv_id") or "")
        r = by_id.get(aid, {})
        ds = [x for x in re.findall(r"D\d{1,2}", r.get("domain") or "")]
        aas = [x for x in re.findall(r"A\d{2}", r.get("algorithms") or "")]
        for d in ds:
            dom[d] += 1
        for a in aas:
            algo[a] += 1
        for d in ds:
            for a in aas:
                pairs[f"{d}+{a}"] += 1
    all_a = {f"A{i:02d}" for i in range(1, 19)}
    all_d = {f"D{i}" for i in range(0, 11)}
    benches = [b.label for b in graph.by_type("Benchmark")]
    metrics = [m.label for m in graph.by_type("MetricDefinition")]
    return {"domains": dict(dom), "algo_families": dict(algo),
            "top_pairs": dict(pairs.most_common(10)),
            "uncovered_domains": sorted(all_d - set(dom)),
            "uncovered_algo_families": sorted(all_a - set(algo)),
            "benchmarks": benches, "metrics": metrics,
            "n_benchmarks": len(benches), "n_metrics": len(metrics),
            "papers_with_benchmark": sum(
                1 for p in graph.by_type("Paper")
                if _out(graph, p.id, "EVALUATED_ON"))}


def full_report(graph: POGraph) -> Dict[str, Any]:
    from ..ontology.refine import graph_quality
    q = graph_quality(graph)
    # 跨论文共享
    cnt = Counter()
    papers = {n.id for n in graph.by_type("Paper")}
    for a in graph.assertions:
        if a.source in papers:
            cnt[a.target] += 1
    shared = [(k, v, graph.nodes[k].type if k in graph.nodes else "?")
              for k, v in cnt.items() if v >= 2]
    return {"quality": q,
            "shared_nodes": len(shared), "shared_detail": shared[:12],
            "queryability": query_templates(graph),
            "reasoning": reasoning_capabilities(graph),
            "distribution": da_distribution(graph)}
