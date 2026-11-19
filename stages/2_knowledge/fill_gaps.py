#!/usr/bin/env python3
"""补 D2/D3 缺口：强规则 → 同流派众数 → 标记来源（不调 LLM）。"""
from __future__ import annotations
import json, sys, re
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph

GRAPH = ROOT / "storage/sciforge/factory_knowledge_enriched.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_complete.json"
MD = ROOT / "data/docx"


def strong_rule(text: str, title: str) -> tuple[str | None, str | None]:
    """从原文强信号判定，不用众数。"""
    head = text[:4000]
    t = title.lower()
    # survey/review → interpretive
    if re.search(r"\b(a survey|review of|systematic review)\b", t) or \
       re.search(r"this (survey|review) (categorizes|surveys|reviews)", head, re.I):
        return "interpretive", "interpretive"
    # 纯理论：theorem/proof 且无实验节
    if re.search(r"theorem \d|proof of theorem|we prove that", head, re.I) and \
       not re.search(r"we (evaluate|experiment|benchmark)", head, re.I):
        return "derivational", "formal"
    return None, None


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    # 众数表
    modes = {}
    for fam in set(p.attrs.get("method_family") for p in papers):
        ps = [p for p in papers if p.attrs.get("method_family") == fam]
        ev = Counter(p.attrs.get("evidence_type") for p in ps if p.attrs.get("evidence_type"))
        pa = Counter(p.attrs.get("paradigm") for p in ps if p.attrs.get("paradigm"))
        modes[fam] = (ev.most_common(1)[0][0] if ev else None,
                      pa.most_common(1)[0][0] if pa else None)
    filled = []
    for p in papers:
        if p.attrs.get("evidence_type") and p.attrs.get("paradigm"):
            continue
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        md = MD / f"{aid}.md"
        text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
        ev, pa = strong_rule(text, p.attrs.get("true_title") or p.label)
        source = "strong_rule"
        if not ev:
            ev, pa = modes.get(p.attrs.get("method_family"), (None, None))
            source = "family_mode"
        if ev and not p.attrs.get("evidence_type"):
            p.attrs["evidence_type"] = ev
            p.attrs["evidence_type_source"] = source
        if pa and not p.attrs.get("paradigm"):
            p.attrs["paradigm"] = pa
            p.attrs["paradigm_source"] = source
        filled.append({"aid": aid, "family": p.attrs.get("method_family"),
                       "evidence_type": ev, "paradigm": pa, "source": source})
    g.save(str(OUT))
    print(json.dumps({"filled": filled,
                      "remaining_ev": sum(1 for p in papers if not p.attrs.get("evidence_type")),
                      "remaining_pa": sum(1 for p in papers if not p.attrs.get("paradigm")),
                      "out": str(OUT)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
