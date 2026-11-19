#!/usr/bin/env python3
"""把 data3 论文 PDF 转成保留 markdown 表格的 data/docx/<aid>.md。"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/data3/manifest.json"
PAPER_DIR = ROOT / "data/data3/paper"
OUT_DIR = ROOT / "data/docx"


def _cell(v) -> str:
    if v is None:
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s.replace("|", "\\|")


def _table_md(rows) -> str:
    rows = [[_cell(c) for c in row] for row in rows if any(c is not None for c in row)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    # 合并多行表头：第二行若多是空/缩写，保留但不强行合并
    lines = ["| " + " | ".join(rows[0]) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def convert(pdf: Path, aid: str) -> dict:
    doc = pymupdf.open(str(pdf))
    parts = [f"# {aid}", ""]
    n_tables = 0
    for pi, page in enumerate(doc):
        parts += [f"## Page {pi + 1}", ""]
        tabs = page.find_tables().tables
        table_rects = [pymupdf.Rect(t.bbox) for t in tabs]
        blocks = page.get_text("blocks") or []
        text_blocks = []
        for b in blocks:
            r = pymupdf.Rect(b[:4])
            if any(r.intersects(tr) for tr in table_rects):
                continue
            txt = str(b[4]).strip()
            if txt:
                text_blocks.append(txt)
        parts += text_blocks
        parts.append("")
        for t in tabs:
            md = _table_md(t.extract())
            if md:
                n_tables += 1
                parts += [md, ""]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{aid}.md"
    text = "\n".join(parts)
    out.write_text(text, encoding="utf-8")
    return {"aid": aid, "pdf": str(pdf.relative_to(ROOT)), "out": str(out.relative_to(ROOT)),
            "pages": len(doc), "chars": len(text), "tables": n_tables}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    papers = man["papers"]
    if a.limit:
        papers = papers[:a.limit]
    reps = []
    for p in papers:
        aid = p["id"]
        local = p.get("local")
        pdf = PAPER_DIR / local if local else None
        if not pdf or not pdf.exists():
            cand = list(PAPER_DIR.glob(aid + "*.pdf"))
            if not cand:
                print(json.dumps({"skip": aid, "reason": "no pdf"}, ensure_ascii=False))
                continue
            pdf = cand[0]
        reps.append(convert(pdf, aid))
    print(json.dumps({"n": len(reps), "reports": reps}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
