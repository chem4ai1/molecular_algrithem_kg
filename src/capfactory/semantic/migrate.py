"""v3.2(46 类/105 关系) → v4 语义层(8 类/11 关系) 的图表迁移。

只读旧图、写新图（不覆盖），保证可回滚。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List

from .tbox_v4 import SEMANTIC_CLASSES, field_names

OUT = Path("storage_cf/sciforge/batch10_semantic_v4.json")

KEEP_ATTRS = {
    "Paper": field_names("Paper"),
    "Algorithm": field_names("Algorithm"),
    "AlgorithmModule": field_names("AlgorithmModule"),
    "CodeRepository": field_names("CodeRepository"),
    "CodeFunction": field_names("CodeFunction"),
    "Benchmark": field_names("Benchmark"),
}
# 旧属性 → 新属性（按类）
RENAME = {
    "Paper": {"algorithm_family": "flow_family",
              "algorithm_family_id": "flow_family",
              "research_problem": "research_question"},
    "Algorithm": {"schema_family": "flow_family"},
    "CodeFunction": {"docstring": "comment", "signature": "params"},
    "CodeRepository": {"url": "repo_url", "name": "repo_name"},
}
DROP_TYPES = {"ResearchQuestion", "ProblemCategory", "MetricDefinition",
              "LeaderboardEntry", "DataContract", "Evidence", "Limitation",
              "SourcePaper"}


def _func_type(name: str) -> str:
    n = (name or "").lower()
    for kw, t in (("forward", "forward"), ("generate", "generator"),
                  ("sample", "generator"), ("decode", "generator"),
                  ("loss", "loss"), ("train", "train"),
                  ("load", "io"), ("save", "io"), ("dump", "io"),
                  ("read", "io"), ("write", "io"), ("get", "accessor"),
                  ("parse", "transform"), ("process", "transform"),
                  ("canonical", "transform"), ("normalize", "transform")):
        if kw in n:
            return t
    return "helper"


def _purpose(name: str, attrs: Dict[str, Any]) -> str:
    p = attrs.get("purpose") or attrs.get("role") or ""
    if p and p != "unknown":
        return str(p)
    return f"实现 {name} 逻辑"


def migrate(graph: Any, *, out: Path = OUT, persist: bool = True
            ) -> Dict[str, Any]:
    from ..po import POGraph
    g = POGraph("semantic_v4")
    rep: Dict[str, Any] = {"nodes_in": len(graph.nodes),
                           "nodes_out": 0, "by_type": {},
                           "dropped_types": {}, "renamed_relations": {},
                           "dropped_relations": {}, "gaps": []}
    # 0) 先把被删类的内容回填为语义层属性（ResearchQuestion/ProblemCategory）
    rq_of_paper: Dict[str, str] = {}
    cat_of_rq: Dict[str, str] = {}
    for a in graph.assertions:
        if a.relation == "ADDRESSES":
            rq_of_paper.setdefault(a.source, a.target)
        elif a.relation == "BROADER":
            cat_of_rq.setdefault(a.source, a.target)
    for pid, rqid in rq_of_paper.items():
        rq = graph.nodes.get(rqid)
        if rq:
            graph.nodes[pid].attrs.setdefault("research_question", rq.label)
        cid = cat_of_rq.get(rqid, "")
        pc = graph.nodes.get(cid) if cid else None
        if pc:
            graph.nodes[pid].attrs.setdefault("problem_category", pc.label)

    # 1) 保留语义层节点，按 schema 裁剪属性
    TYPE_ALIAS = {"AlgorithmStep": "AlgorithmModule",
                  "MetricObservation": "Observation"}   # 别名归一
    for n in graph.nodes.values():
        t = TYPE_ALIAS.get(n.type, n.type)
        if t in DROP_TYPES or t not in SEMANTIC_CLASSES:
            rep["dropped_types"][n.type] = \
                rep["dropped_types"].get(n.type, 0) + 1
            continue
        a = dict(n.attrs)
        for old, new in RENAME.get(t, {}).items():
            if old in a and new not in a:
                a[new] = a[old]
        kept = {k: a[k] for k in KEEP_ATTRS[t] if k in a}
        # 语义层必需字段兜底
        if t == "AlgorithmModule":
            kept.setdefault("name", a.get("module_name") or n.label)
            kept.setdefault("mechanism", a.get("mechanism")
                            or a.get("label") or "unknown")
            kept.setdefault("inputs", a.get("input_schema") or "unknown")
            kept.setdefault("outputs", a.get("output_schema") or "unknown")
            kept.setdefault("formula", a.get("equation_ref") or "")
        if t == "CodeFunction":
            kept.setdefault("name", n.label)
            kept.setdefault("purpose", _purpose(n.label, a))
            kept.setdefault("comment", a.get("comment") or "")
            kept.setdefault("params", a.get("params") or "")
            kept.setdefault("returns", a.get("returns") or "")
            kept.setdefault("func_type", _func_type(n.label))
        kept.setdefault("name", n.label)
        g.node(n.id, t, n.label, **kept)
        rep["by_type"][t] = rep["by_type"].get(t, 0) + 1
    # 2) 关系重写
    paper_algo: Dict[str, str] = {}
    for a in graph.assertions:
        if a.relation == "PROPOSES_METHOD":
            paper_algo.setdefault(a.source, a.target)
    for a in graph.assertions:
        s, t = a.source, a.target
        if s not in g.nodes or t not in g.nodes:
            continue
        rel = a.relation
        if rel == "HAS_MODULE_DETAIL":
            src = paper_algo.get(s, s)
            if g.nodes.get(src) and g.nodes[src].type != "Algorithm":
                rep["gaps"].append({"rel": rel, "src": s,
                                    "reason": "no_algorithm_for_paper"})
                continue
            rel = "HAS_MODULE"
            s = src
            rep["renamed_relations"]["HAS_MODULE_DETAIL→HAS_MODULE"] = \
                rep["renamed_relations"].get("HAS_MODULE_DETAIL→HAS_MODULE", 0) + 1
        elif rel == "IMPLEMENTS_MODULE":
            rel, s, t = "MODULE_IMPLEMENTED_BY", t, s
            rep["renamed_relations"]["IMPLEMENTS_MODULE→MODULE_IMPLEMENTED_BY"] = \
                rep["renamed_relations"].get(
                    "IMPLEMENTS_MODULE→MODULE_IMPLEMENTED_BY", 0) + 1
        elif rel == "HAS_LEADERBOARD":
            continue
        elif rel in ("ADDRESSES", "BROADER"):
            # 问题已降为 Paper 属性
            continue
        try:
            g.assert_rel(s, t, rel)
        except Exception:  # noqa: BLE001
            rep["dropped_relations"][rel] = \
                rep["dropped_relations"].get(rel, 0) + 1
    # 3) 语义层补齐（Stage3 确定性，不调 LLM）
    from .enrich import enrich
    rep["enrich"] = enrich(g, legacy=graph)
    rep["nodes_out"] = len(g.nodes)
    rep["assertions_out"] = len(g.assertions)
    if persist:
        g.save(str(out))
        rep["path"] = str(out)
    return rep
