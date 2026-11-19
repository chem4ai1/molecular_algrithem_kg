#!/usr/bin/env python3
"""P2 + P6 端到端：论文表格 → ResultTable 节点 → LaTeX + DatasetSpec 去泄漏。"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.paper_artifacts import table_to_latex
from capfactory.semantic.extractspec import loader as _loader

GRAPH = ROOT / "storage/sciforge/factory_knowledge_rules.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_p6.json"
GEN = ROOT / "storage/generated"


def pick_numeric_columns(header: list, rows: list) -> list:
    """挑出数值列（>=60% 单元格可转 float）。"""
    cols = []
    for idx, name in enumerate(header):
        if idx == 0:
            continue
        vals = [r[idx] for r in rows if idx < len(r)]
        num = 0
        for v in vals:
            try:
                float(str(v).replace("%", "").replace("*", "").strip())
                num += 1
            except ValueError:
                pass
        if vals and num / len(vals) >= 0.6:
            cols.append((idx, name))
    return cols


def main():
    # 主结果表判定规则来自 YAML（不再硬编码）
    _sp = (_loader.stages() or {}).get("E1_paper")
    _rt = (_sp.rules.get("result_tables") if _sp else {}) or {}
    FIRST_COL_KW = _rt.get("main_table_first_col_keywords") or ["model", "method"]
    MIN_ROWS = int(_rt.get("main_table_min_rows") or 2)
    print(f"YAML 判定规则: first_col={FIRST_COL_KW} min_rows={MIN_ROWS}", flush=True)
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    GEN.mkdir(parents=True, exist_ok=True)
    for old in GEN.glob("*.tex"):      # 清理上轮残留，避免误判覆盖率
        old.unlink()
    made, skipped = 0, 0
    report = []
    # 只对最像主结果的表做转换（选数值列最多的那张）
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        tables = p.attrs.get("result_tables") or []
        best = None
        for t in tables:
            # 主结果表启发式：第一列必须是 Model/Method/Approach 之类
            first = str(t["columns"][0]).lower()
            if not any(k in first for k in FIRST_COL_KW):
                continue
            cols = pick_numeric_columns(t["columns"], t["rows"])
            if len(cols) >= 1 and len(t["rows"]) >= MIN_ROWS:
                if best is None or len(cols) > len(best[1]):
                    best = (t, cols)
        if not best:
            skipped += 1
            continue
        t, cols = best
        rows = []
        for r in t["rows"]:
            row = {"model": r[0]}
            for idx, name in cols:
                row[name] = str(r[idx]).replace("%", "").replace("*", "").strip() \
                    if idx < len(r) else ""
            rows.append(row)
        latex = table_to_latex(rows, columns=[n for _, n in cols],
                               caption=t.get("label", ""), label=f"tab:{aid}")
        # 只负责产出 .tex；ResultTable 节点由 applayer.miner 统一派生
        (GEN / f"{aid}.tex").write_text(latex, encoding="utf-8")
        made += 1
        report.append({"aid": aid, "table": t.get("label", "")[:50],
                       "cols": [n for _, n in cols], "rows": len(rows)})
    g.save(str(OUT))
    (GEN / "p6_report.json").write_text(
        json.dumps({"made": made, "skipped": skipped, "tables": report[:20]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"made": made, "skipped": skipped,
                      "sample": report[:5], "out": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
