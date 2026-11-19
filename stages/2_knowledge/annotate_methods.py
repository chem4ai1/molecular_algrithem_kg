#!/usr/bin/env python3
"""给 52 篇论文标注 method_family（流派）+ 修正标题。

输入：语义图（Paper 节点 label 是 PDF 页眉，需从 md 首行修正）
输出：带 method_family / true_title 的图
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.method_taxonomy import classify_by_text, METHOD_FAMILIES

GRAPH = ROOT / "storage/sciforge/factory_knowledge_v2.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_annotated.json"
MD = ROOT / "data/docx"


def title_from_md(aid: str) -> str:
    p = MD / f"{aid}.md"
    if not p.exists():
        return ""
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()[:40]
             if ln.strip()]
    # 跳过页眉/期刊名，找第一行足够长且非全大写的标题
    skip = re.compile(r"^(Published as|Preprint|nature machine|Under review|Please do not|"
                      r"Copyright|arXiv|journal|conference paper)", re.I)
    for ln in lines:
        if skip.search(ln) or len(ln) < 12 or len(ln) > 300:
            continue
        return re.sub(r"^#+\s*", "", ln.replace("**", "").replace("_", "")).strip()[:200]
    return lines[0][:200] if lines else ""


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    stats = {}
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        # 1) 修正标题
        true_title = title_from_md(aid)
        if true_title:
            p.attrs["true_title"] = true_title
        # 2) 方法流派标注：标题 + 算法名 + 原文机制
        algs = [g.nodes[a.target].attrs.get("name", "")
                for a in g.outgoing(p.id) if a.relation == "PROPOSES_METHOD"
                and a.target in g.nodes]
        text = " ".join([true_title, p.label] + algs)
        fams = classify_by_text(text, top_k=2)
        if fams:
            p.attrs["method_family"] = fams[0][0]
            p.attrs["method_family_score"] = round(fams[0][1], 3)
            if len(fams) > 1:
                p.attrs["method_family_secondary"] = fams[1][0]
        else:
            p.attrs["method_family"] = "unclassified"
    from collections import Counter
    stats = Counter(p.attrs.get("method_family") for p in papers)
    g.save(str(OUT))
    print(json.dumps({"n_papers": len(papers), "families": dict(stats),
                      "out": str(OUT)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
