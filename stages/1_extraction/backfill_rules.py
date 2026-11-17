#!/usr/bin/env python3
"""规则层回填：从 783 篇 md 补 Paper.authors / abstract / title。

不调 LLM、不覆盖已有值。只填没有的字段。
"""
from __future__ import annotations
import argparse, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph                    # noqa: E402

MD = ROOT / "data/docx"
CSV = ROOT / "data/papers.csv"
GRAPH = ROOT / "storage_cf/sciforge/batch10_semantic_v4.json"
ORG = re.compile(r"universit|institut|laborator|department|dept\.|college|"
                 r"academy|research center|school of|technology|_inc", re.I)


def parse_head(md: Path) -> dict:
    lines = [ln.strip() for ln in
             md.read_text(encoding="utf-8", errors="replace")[:12000].splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return {}
    out = {"title": lines[0][:200]}
    # 作者：前 12 行里像人名的行（不含机构关键词、不含抽象长句）
    cand = []
    for ln in lines[1:14]:
        if len(ln) > 140 or ORG.search(ln) or "@" in ln or "http" in ln:
            continue
        if re.search(r"\d\s*[,;]?\s*$", ln) and len(ln) < 90:
            continue
        cand.append(ln)
    if cand:
        joined = cand[0] if len(cand) == 1 else " ".join(cand[:3])
        parts = re.split(r",\s*|\s+and\s+|\s*;\s*", joined)
        people = [p.strip() for p in parts
                  if 2 < len(p.strip()) < 60 and not ORG.search(p)][:15]
        if people:
            out["authors"] = people
    # 摘要：Abstract 后的首段，或标题后的首个长段
    body = "\n".join(lines)
    m = re.search(r"(?im)^\s*(abstract|summary)\s*[:.]?\s*\n(.{80,3000}?)(?:\n\s*\n|\n\s*\d+\s+introduction)", body)
    if m:
        out["abstract"] = re.sub(r"\s+", " ", m.group(2)).strip()[:2000]
    else:
        for ln in lines[1:40]:
            if 120 <= len(ln) <= 2600 and not ORG.search(ln):
                out["abstract"] = ln[:2000]
                break
    return out


def csv_map() -> dict:
    import csv
    out = {}
    with CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            aid = (r.get("arxiv_id") or "").strip()
            if not aid:
                aid = (r.get("paper_id") or "").split(":")[-1]
            if not aid:
                continue
            rec = {}
            for k in ("title", "authors", "abstract", "doi", "venue", "year"):
                v = (r.get(k) or "").strip()
                if v:
                    rec[k] = [x.strip() for x in v.split(";") if x.strip()] \
                        if k == "authors" else v
            out[aid] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    g = POGraph.load(str(GRAPH))
    csv_by_aid = csv_map()
    files = sorted(MD.glob("*.md"))
    if a.limit:
        files = files[:a.limit]
    stat = {"papers": 0, "authors": 0, "abstract": 0, "title": 0,
            "doi": 0, "venue": 0, "year": 0, "skip": 0}
    t0 = time.time()
    for f in files:
        aid = f.stem
        n = g.nodes.get("paper:" + aid)
        if n is None:
            stat["skip"] += 1
            continue
        stat["papers"] += 1
        info = csv_by_aid.get(aid) or {}
        source = "csv"
        if not info.get("authors"):
            info = dict(parse_head(f))
            source = "md"
        stat["src_" + source] = stat.get("src_" + source, 0) + 1
        for k in ("authors", "abstract", "title", "doi", "venue", "year"):
            if info.get(k) and not n.attrs.get(k):
                stat[k] += 1
                if not a.dry_run:
                    n.attrs[k] = info[k]
    if not a.dry_run:
        g.save(str(GRAPH))
    print({"stat": stat, "secs": round(time.time() - t0, 1),
           "saved": not a.dry_run, "graph": str(GRAPH)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
