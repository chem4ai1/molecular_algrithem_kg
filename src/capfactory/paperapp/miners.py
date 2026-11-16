"""D1–D4 确定性派生挖掘（NON_LLM、幂等、只写应用层）。

不改 applayer/miner.py 的既有 8 个 miner，也不改语义层图。
所有输出带 derived_from / miner / provenance="deterministic"。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from . import config


def _attrs(n) -> Dict[str, Any]:
    return dict(getattr(n, "attrs", {}) or {})


def _out(graph, nid: str, rel: str) -> List[str]:
    return [a.target for a in (getattr(graph, "assertions", []) or [])
            if a.source == nid and a.relation == rel]


def _as_list(v) -> List[str]:
    """字符串整体作词元，按分隔符切分；不拆中文单字。"""
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    return [x.strip() for x in re.split(r"[,，;；、|/]+", s) if x.strip()]


def D1_flow_closure(graph) -> Dict[str, Any]:
    """模块 inputs/outputs 词元交集 → 直接前驱 + 环检测。"""
    mods = {nid: _attrs(n) for nid, n in (getattr(graph, "nodes", {}) or {}).items()
            if getattr(n, "type", "") in ("AlgorithmModule", "AlgorithmStep")}
    producers: Dict[str, List[str]] = defaultdict(list)
    consumers: Dict[str, List[str]] = defaultdict(list)
    for nid, a in mods.items():
        for t in _as_list(a.get("outputs")):
            producers[t].append(nid)
        for t in _as_list(a.get("inputs")):
            consumers[t].append(nid)
    edges: List[Dict[str, str]] = []
    for token, srcs in producers.items():
        for s in srcs:
            for d in consumers.get(token, []):
                if s != d:
                    edges.append({"source": s, "relation": "DERIVED_FROM",
                                  "target": d, "token": token})
    # 环检测（有向图 DFS）
    adj: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e["target"])
    cycles: List[List[str]] = []
    state: Dict[str, int] = {}

    def dfs(u: str, stack: List[str]):
        state[u] = 1
        stack.append(u)
        for v in adj.get(u, []):
            if state.get(v) == 1 and v in stack:
                cycles.append(stack[stack.index(v):] + [v])
            elif state.get(v, 0) == 0:
                dfs(v, stack)
        stack.pop()
        state[u] = 2

    for n in sorted(adj):
        if state.get(n, 0) == 0:
            dfs(n, [])
    return {"miner": "D1:flow_closure", "provenance": "deterministic",
            "derived_from": sorted(mods), "n_edges": len(edges),
            "edges": edges[:200], "n_cycles": len(cycles), "cycles": cycles[:20]}


def D2_method_benchmark_matrix(graph) -> Dict[str, Any]:
    """Algorithm × Benchmark 共现矩阵 → 空格即结构性 ResearchGap 候选。"""
    nodes = getattr(graph, "nodes", {}) or {}
    algos = [k for k, n in nodes.items() if getattr(n, "type", "") == "Algorithm"]
    bench = [k for k, n in nodes.items() if getattr(n, "type", "") == "Benchmark"]
    linked = {(a.source, a.target) for a in (getattr(graph, "assertions", []) or [])
              if a.relation == "EVALUATED_ON"}
    cells = [{"algorithm": a, "benchmark": b, "covered": (a, b) in linked}
             for a in algos for b in bench]
    gaps = [{"gap_id": f"gap:blank:{c['algorithm']}:{c['benchmark']}",
             "gap_type": "structural_blank", "kind": "D2"}
            for c in cells if not c["covered"]]
    return {"miner": "D2:method_benchmark_matrix", "provenance": "deterministic",
            "derived_from": algos + bench, "n_cells": len(cells),
            "n_gaps": len(gaps), "gaps": gaps[:100]}


def D3_lineage_slice(graph) -> Dict[str, Any]:
    """Paper--RELATED_TO-->Paper 谱系按年份切片 → FrontierNode。"""
    nodes = getattr(graph, "nodes", {}) or {}
    rels = [a for a in (getattr(graph, "assertions", []) or [])
            if a.relation == "RELATED_TO"]
    rows = []
    for a in rels:
        src, dst = nodes.get(a.source), nodes.get(a.target)
        if src is None or dst is None:
            continue
        year = _attrs(dst).get("year") or _attrs(a).get("year") or ""
        rows.append({"frontier_id": f"appfrontier:{a.source}:{a.target}",
                     "paper": a.target, "year": year,
                     "state": "unsolved" if _attrs(dst).get("open_problems") else "solved",
                     "derived_from": [a.source, a.target]})
    return {"miner": "D3:lineage_slice", "provenance": "deterministic",
            "derived_from": sorted({r["derived_from"][0] for r in rows}),
            "frontier_nodes": rows[:200], "n": len(rows)}


def D4_capability_cooccurrence(graph) -> Dict[str, Any]:
    """CodeFunction 按仓库共现 + 符号 → Capability 成熟度（复用 gaps.py 口径）。"""
    nodes = getattr(graph, "nodes", {}) or {}
    fns = {k: _attrs(n) for k, n in nodes.items()
           if getattr(n, "type", "") == "CodeFunction"}
    groups: Dict[str, List[str]] = defaultdict(list)
    for k, a in fns.items():
        file = str(a.get("file") or a.get("path") or "unknown")
        groups[file].append(k)
    rows = []
    for f, members in groups.items():
        maturity = min(1.0, len(members) / 5.0)
        status = "covered" if maturity >= 0.5 else ("partial" if maturity >= 0.2 else "gap")
        rows.append({"capability_id": f"appcap:{f}", "file": f,
                     "n_functions": len(members), "maturity": round(maturity, 4),
                     "status": status, "derived_from": members[:20]})
    return {"miner": "D4:capability_cooccurrence", "provenance": "deterministic",
            "derived_from": sorted(fns), "capabilities": rows[:100], "n": len(rows)}


def run_derived(graph) -> Dict[str, Any]:
    out = {}
    for name, fn in (("D1", D1_flow_closure), ("D2", D2_method_benchmark_matrix),
                     ("D3", D3_lineage_slice), ("D4", D4_capability_cooccurrence)):
        try:
            out[name] = fn(graph)
        except Exception as exc:  # noqa: BLE001
            out[name] = {"miner": name, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "derived": out, "n_miners": len(out),
            "semantic_version": config.SEMANTIC_TBOX_VERSION}


def inject_human_hypothesis(hypothesis: Dict[str, Any], *, boost: float = 0.0) -> Dict[str, Any]:
    """I4/P2：人的方向同样必须满足 gap_anchor 或显式 exploratory 理由。"""
    statement = str(hypothesis.get("statement") or "").strip()
    claim = str(hypothesis.get("falsifiable_claim") or "").strip()
    gap = str(hypothesis.get("gap_anchor") or "").strip()
    exploratory = str(hypothesis.get("exploratory_reason") or "").strip()
    if not statement or not claim:
        return {"ok": False, "reason_code": "missing_statement_or_claim"}
    if not gap and not exploratory:
        return {"ok": False, "reason_code": "missing_gap_anchor"}
    effective_boost = min(max(boost, 0.0), config.HUMAN_BOOST_CAP)
    return {"ok": True, "reason_code": "ok", "origin": "human",
            "hypothesis": {**hypothesis, "origin": "human", "boost": effective_boost},
            "requires_mcts": True, "same_weight_as_machine": effective_boost == 0.0}
