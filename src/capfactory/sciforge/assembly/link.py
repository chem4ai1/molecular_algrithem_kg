"""A3 Link：三级根定位 + 原论文反查 + AST/代码符号对齐。"""
from __future__ import annotations
import re
from typing import Any, Dict, List

from .contract import LinkPlan


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def find_roots(graph: Any, paper_id: str, kind: str,
               hints: List[str]) -> List[str]:
    """三级：① Stage2 名字匹配图内节点 ② 图内关系 ③ 自建根（自举）。"""
    by_label = {}
    for n in graph.nodes.values():
        if n.type == kind:
            by_label[_slug(n.label)] = n.id
    out: List[str] = []
    for h in hints:
        k = _slug(h)
        if k in by_label:
            out.append(by_label[k])
        else:
            for n in graph.nodes.values():
                if n.type == kind and k and (k in _slug(n.label) or
                                             _slug(n.label) in k):
                    out.append(n.id)
                    break
    if not out:
        rel = {"Algorithm": "PROPOSES_METHOD",
               "Benchmark": "EVALUATED_ON"}.get(kind, "")
        if rel:
            out = [a.target for a in graph.outgoing(paper_id)
                   if a.relation == rel and a.target in graph.nodes]
    return [x for x in dict.fromkeys(out) if x]


def resolve_source_ref(name: str, md: str) -> Dict[str, Any]:
    """统一原论文反查（修 E16）：复用 algorithm_problem 的引用投票逻辑。"""
    try:
        from ..algorithm_problem import find_source_paper
        return find_source_paper(name, md)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:100]}


def ast_align(symbols: List[str], graph: Any) -> Dict[str, Any]:
    """代码符号与图内 CodeFunction 求交；未命中记 gap，不硬造符号。"""
    known = set()
    for n in graph.nodes.values():
        if n.type == "CodeFunction":
            known.add(n.label.lower())
            known.add(n.id.split(":")[-1].lower())
    hits = [s for s in symbols if s.lower() in known or
            s.split(".")[-1].lower() in known]
    gaps = [{"symbol": s, "reason": "no_ast_match"} for s in symbols
            if s not in hits]
    return {"hits": hits, "gaps": gaps}


def link(inp: Any, norm: Any, *, graph: Any, tbox: Any = None,
         repo: str = "") -> LinkPlan:
    p = LinkPlan(paper_root=inp.paper_id)
    p.algorithm_roots = find_roots(
        graph, inp.paper_id, "Algorithm",
        [str(inp.method.get("name") or "")] + norm.baselines[:4])
    p.benchmark_roots = find_roots(
        graph, inp.paper_id, "Benchmark",
        [b.get("name", "") for b in norm.benchmarks])
    # 三级：Stage2 明确给出但图里没有 → 自建根 + 补根边
    for b in norm.benchmarks:
        nm = str(b.get("name") or "")
        if not nm:
            continue
        bid = f"benchmark:{_slug(nm)}"
        if bid not in graph.nodes:
            p.root_edges.append({"src": inp.paper_id, "rel": "EVALUATED_ON",
                                 "dst": bid, "label": nm, "type": "Benchmark"})
            p.benchmark_roots.append(bid)
        elif inp.paper_id in graph.nodes and not any(
                a.target == bid and a.relation == "EVALUATED_ON"
                for a in graph.outgoing(inp.paper_id)):
            p.root_edges.append({"src": inp.paper_id, "rel": "EVALUATED_ON",
                                 "dst": bid, "label": "", "type": ""})
    p.benchmark_roots = [x for x in dict.fromkeys(p.benchmark_roots) if x]
    for m in norm.methods[:8]:
        p.source_refs.append({"name": m, **resolve_source_ref(m, inp.md)})
    ast = ast_align(norm.code_symbols, graph)
    p.ast_hits = ast["hits"]
    p.gaps = ast["gaps"]
    return p
