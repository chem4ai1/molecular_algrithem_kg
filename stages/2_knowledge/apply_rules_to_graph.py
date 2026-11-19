#!/usr/bin/env python3
"""对已有 Paper 节点重跑 E1 rules 段，并用规则结果回填图属性。"""
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.semantic.extractspec import loader
from capfactory.semantic.extractspec.rules import apply_rules
from capfactory.applayer.readiness import audit_graph

ap = argparse.ArgumentParser()
ap.add_argument("--graph", default=str(ROOT / "storage/sciforge/factory_knowledge_main.json"))
ap.add_argument("--stage", default="E1_paper")
a = ap.parse_args()

g = POGraph.load(a.graph)
sp = (loader.stages() or {})[a.stage]
fields = [k for k in sp.rules if k != "preprocess"]
updated = 0
for p in g.by_type("Paper"):
    aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
    md = ROOT / "data/docx" / f"{aid}.md"
    if not md.exists():
        continue
    filled = apply_rules(sp.rules, md.read_text(encoding="utf-8", errors="replace"))
    changed = False
    for k in fields:
        v = filled.get(k)
        if v and v != p.attrs.get(k):
            p.attrs[k] = v
            changed = True
    if changed:
        updated += 1
g.save(a.graph)
rep = audit_graph(g)
print(json.dumps({"updated_papers": updated,
                  "stats": rep["stats"],
                  "graph": a.graph}, ensure_ascii=False, indent=2))
