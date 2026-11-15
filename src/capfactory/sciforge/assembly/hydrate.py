"""给 Stage3/来源解析新建的派生节点补齐三库最小属性，保证契约一致。"""
from __future__ import annotations
from typing import Any, Dict

PAPER_DEFAULTS = {
    "research_problem": "unknown（代理/库内节点，待论文核心抽取补全）",
    "problem_type": "unknown", "domain": "unknown", "domain_code": "D0",
    "algorithm_family": "unknown", "algorithm_family_id": "unknown",
    "why_hard": "unknown", "evidence": "",
    "relation_hints": {"related_papers": [], "algorithms": [],
                       "benchmarks": []},
    "domain_codes": ["D0"], "algo_codes": ["A01"], "paper_type": "method",
    "schema_version": "v3_paper_core",
}
BENCH_DEFAULTS = {
    "name": "", "input_form": "unknown", "output_form": "unknown",
    "metrics": [], "model_results": [], "sota_by_metric": {},
    "matrix": {}, "n_samples": "unknown", "scale": "规模未标注",
    "modality": "unknown", "research_object": "unknown",
    "schema_family": "molecule_generation", "schema_version": "v2_lean",
}


def hydrate_derived_nodes(graph: Any) -> Dict[str, int]:
    n_paper = n_bench = 0
    for n in graph.by_type("Paper"):
        if "research_problem" in n.attrs:
            continue
        for k, v in PAPER_DEFAULTS.items():
            n.attrs.setdefault(k, v)
        if n.attrs.get("name") is None:
            n.attrs["name"] = n.label
        n.attrs.setdefault("title", n.label)
        n.attrs.setdefault("arxiv_id", n.id.split(":")[-1])
        n_paper += 1
    for n in graph.by_type("Benchmark"):
        before = set(n.attrs)
        # 蓝图 §3.4.1：每个节点强制 4 个溯源属性，全库统一
        n.attrs.setdefault("source_locator", "graph_extraction")
        n.attrs.setdefault("assembly_provenance", "graph_extraction")
        n.attrs.setdefault("run_id", "")
        n.attrs.setdefault("inputs_sha", "")
        for k, v in BENCH_DEFAULTS.items():
            n.attrs.setdefault(k, [] if isinstance(v, list) else
                               ({} if isinstance(v, dict) else v))
        if not n.attrs.get("name"):
            n.attrs["name"] = n.label
        if set(n.attrs) != before:
            n_bench += 1
    return {"paper": n_paper, "benchmark": n_bench}
