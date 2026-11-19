#!/usr/bin/env python3
"""第 1 步：规则抽取 P2/P4/P6 支撑字段（零 LLM 成本）。

抽 data_sources / dedup_rule / split_spec / hyperparams / result_tables
并写入语义层图（Paper 属性）。
"""
from __future__ import annotations
import json, re, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.dataset_spec import extract_dataset_spec

GRAPH = ROOT / "storage/sciforge/factory_knowledge_v3.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_rules.json"
MD = ROOT / "data/docx"

HP_PAT = re.compile(
    r"\b(number of iterations|number of steps|max(?:imum)? steps|temperature|top-?k|"
    r"learning rate|batch size|number of samples|sampling budget|oracle budget|"
    r"beam size|threshold)\b[^.]{0,60}?([0-9]+(?:\.[0-9]+)?%?)", re.I)


def parse_md_tables(text: str, max_tables: int = 3) -> list:
    """解析 markdown 表格 → [{label, columns, rows}]。"""
    lines = text.splitlines()
    tables, i = [], 0
    while i < len(lines) and len(tables) < max_tables:
        ln = lines[i]
        if ln.strip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s\-:|]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            # 表头过滤：列名不能是「纯数值/数值+单位」（如 229M、17.5M、0.84）
            NUMish = re.compile(r"^[\*_\s]*[+-]?\d+(\.\d+)?\s*[%MKkGmBb\*_\s]*$")
            text_cols = sum(1 for h in header if not NUMish.match(h))
            if len(header) < 2 or text_cols < len(header) / 2:
                i += 1
                continue
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append(cells)
                j += 1
            if rows:
                # 表标题：往上找 Table N
                label = ""
                for k in range(max(0, i - 6), i):
                    m = re.search(r"(Table\s+\d+[^.\n]{0,60})", lines[k])
                    if m:
                        label = m.group(1).strip()
                        break
                tables.append({"label": label or f"table_{len(tables)+1}",
                               "columns": header, "rows": rows[:30]})
            i = j
        else:
            i += 1
    return tables


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    stat = Counter()
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        md = MD / f"{aid}.md"
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        spec = extract_dataset_spec(text)
        # P2
        if spec["sources"]:
            p.attrs["data_sources"] = spec["sources"]; stat["sources"] += 1
        if spec["dedup_rule"]:
            p.attrs["dedup_rule"] = spec["dedup_rule"]; stat["dedup"] += 1
        if spec["split"]:
            p.attrs["split_spec"] = spec["split"]; stat["split"] += 1
        # P4 hyperparams
        hp = []
        for m in HP_PAT.finditer(text):
            hp.append({"param": m.group(1).lower(), "value": m.group(2),
                       "context": text[max(0, m.start()-30):m.end()].replace("\n", " ")[:100]})
            if len(hp) >= 6:
                break
        if hp:
            p.attrs["hyperparams"] = hp; stat["hyperparams"] += 1
        # P6 result_tables
        tbs = parse_md_tables(text)
        if tbs:
            p.attrs["result_tables"] = tbs; stat["tables"] += 1
            stat["table_count"] += len(tbs)
    g.save(str(OUT))
    print(json.dumps({"n_papers": len(papers), "filled": dict(stat),
                      "coverage": {k: f"{v}/{len(papers)}" for k, v in stat.items()
                                   if k != "table_count"},
                      "out": str(OUT)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
