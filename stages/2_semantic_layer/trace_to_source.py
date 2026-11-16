#!/usr/bin/env python3
"""把图节点回溯到论文原文（md 行号 + 上下文），并给出可定位率。

用法：
    python stages/2_semantic_layer/trace_to_source.py --node benchmark:zinc
    python stages/2_semantic_layer/trace_to_source.py --paper 2411.06608
    python stages/2_semantic_layer/trace_to_source.py --paper 2411.06608 --json

定位等级：
    high   表格块 + 模型行 + 表头指标序数，且值完全一致
    medium 同块内值完全一致，但指标位次对不上
    low    仅按标签在全文中匹配（非数值节点）
未解析但 value_in_text=1 → 定位算法待改进；
未解析且 value_in_text=0 → 原文没有这个数，抽取可疑。
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from capfactory.po import POGraph                      # noqa: E402
from capfactory.semantic.source_locator import locate  # noqa: E402

GRAPH = ROOT / "storage_cf/sciforge/batch10_semantic_v4.json"
EXTRACT = ROOT / "storage_cf/sciforge/semantic_extraction"
MD = ROOT / "data/docx"


def _reports(aid: str):
    p = EXTRACT / (aid + ".json")
    if not p.exists():
        return {}
    return {aid: json.loads(p.read_text(encoding="utf-8"))}


def show_node(node_id: str) -> dict:
    from capfactory.semantic.provenance import trace
    g = POGraph.load(str(GRAPH))
    tr = trace(g, node_id, reports={})
    cands = [r["arxiv_id"] for r in (tr.get("relations") or []) if r.get("arxiv_id")]
    if not cands:
        n = g.nodes.get(node_id)
        pid = (n.attrs.get("paper_id") if n else "") or ""
        cands = [pid.split(":")[-1]] if pid else []
    out = {}
    for cand in cands:
        out = locate(g, node_id, md_dir=MD, reports=_reports(cand), max_hits=10)
        if out.get("hits"):
            break
    print(f"\n节点 {node_id}  ·  {out.get('type')}  ·  {out.get('label')}")
    print(f"论文 {out.get('paper')}  ·  md {out.get('n_lines')} 行 / "
          f"{out.get('n_tables')} 表 / {out.get('n_cells')} 单元格")
    for h in out.get("hits") or []:
        tag = (f"{h.get('table','')} {h.get('model','')}/{h.get('metric','')}"
               f"={h.get('value','')}" if h["kind"] == "cell" else "label")
        print(f"  L{h['line']:>5} [{h['confidence']:<6}] {tag}")
        print(f"          {h['snippet'][:110]}")
    if out.get("unresolved"):
        print(f"  未解析 {len(out['unresolved'])} 条，例：{out['unresolved'][0][:100]}")
    return out


def paper_report(aid: str) -> dict:
    g = POGraph.load(str(GRAPH))
    reports = _reports(aid)
    pids = [n.id for n in g.by_type("Paper") if n.attrs.get("arxiv_id") == aid]
    if not pids:
        return {"paper": aid, "error": "paper_not_in_graph"}
    bms = sorted({a.target for a in g.outgoing(pids[0], "EVALUATED_ON")})
    stat, total, miss_in, miss_out = Counter(), 0, 0, 0
    for b in bms:
        out = locate(g, b, md_dir=MD, reports=reports, max_hits=500)
        total += out.get("n_cells") or 0
        for h in out.get("hits") or []:
            if h["kind"] == "cell":
                stat[h["confidence"]] += 1
        for u in out.get("unresolved") or []:
            if "value_in_text=1" in u:
                miss_in += 1
            elif "value_in_text=0" in u:
                miss_out += 1
    ok = stat["high"] + stat["medium"]
    return {"paper": aid, "benchmarks": len(bms), "cells": total,
            "high": stat["high"], "medium": stat["medium"],
            "unresolved_locatable": miss_in, "unresolved_not_in_text": miss_out,
            "locate_rate": round(ok / total, 4) if total else 0.0,
            "high_rate": round(stat["high"] / total, 4) if total else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--node")
    ap.add_argument("--paper")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.node:
        out = show_node(a.node)
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    if a.paper:
        r = paper_report(a.paper)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
