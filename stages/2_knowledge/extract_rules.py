#!/usr/bin/env python3
"""规则抽取（声明式）：规则全部来自 data/extract_target/stages/*.yaml 的 rules: 段。

本脚本不含任何抽取正则——只负责「读 YAML → 执行 → 写图」。
新增/修改规则只需改 YAML。
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.semantic.extractspec import loader
from capfactory.semantic.extractspec.rules import apply_rules

GRAPH = ROOT / "storage/sciforge/factory_knowledge_v3.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_rules.json"
MD = ROOT / "data/docx"
STAGE = "E1_paper"


def main():
    spec = (loader.stages() or {}).get(STAGE)
    if spec is None or not getattr(spec, "rules", None):
        print(json.dumps({"error": f"{STAGE} 未声明 rules 段"}, ensure_ascii=False))
        return 1
    fields = [k for k in spec.rules if k != "preprocess"]
    print(f"YAML 声明字段: {fields}", flush=True)

    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    stat = Counter()
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        md = MD / f"{aid}.md"
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        filled = apply_rules(spec.rules, text)
        for k, v in filled.items():
            p.attrs[k] = v
            stat[k] += 1
    g.save(str(OUT))
    print(json.dumps({"n_papers": len(papers), "filled": dict(stat),
                      "coverage": {k: f"{v}/{len(papers)}" for k, v in stat.items()},
                      "source": "data/extract_target/stages/E1_paper.yaml#rules",
                      "out": str(OUT)}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
