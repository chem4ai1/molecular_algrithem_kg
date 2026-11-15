"""论文身份回填：给图里的 Paper 补 arXiv ID / DOI 别名，让「标题身份」与「预印本身份」能对上.

问题：图谱里的 ``Paper`` 只有 ``title`` / ``doi``（期刊版），而 PDF 语料是 arXiv
预印本（``1509.09292``、``arXiv:1802.05283v4``）。两者是同一篇论文的**不同身份**，
不补别名就永远链不上——这不是链接算法的问题，是**身份字段缺失**。

做法（保守，宁可少补也不错补）：

1. DOI 精确匹配（``10.xxxx/...`` 归一后全等）；
2. 标题前缀匹配，要求归一键长度 ≥ 40 且**在语料中唯一**；
3. 每次回填都记 ``alias_source``（``doi`` / ``title``）与 ``alias_confidence``，
   便于人工复核与回滚。

回填只写 ``arxiv_id`` / ``aliases`` 属性，不改节点 id、不动已有字段。
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils import now_iso

DEFAULT_PAPERS_CSV = "/home/zengshuxin/xKG-main/data/papers/papers.csv"
_ARXIV = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_DOI = re.compile(r"(10\.\d{4,9}/[^\s,;]+)", re.I)


def norm_title(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def arxiv_of(text: str) -> str:
    m = _ARXIV.search(str(text or ""))
    return m.group(1) if m else ""


def doi_of(text: str) -> str:
    m = _DOI.search(str(text or ""))
    return m.group(1).rstrip(".").lower() if m else ""


def load_corpus_index(path: str | Path = DEFAULT_PAPERS_CSV) -> Dict[str, Any]:
    """从 ``papers.csv`` 建 DOI / 标题 → arXiv ID 的索引。"""
    by_doi: Dict[str, str] = {}
    by_title: Dict[str, List[str]] = {}
    p = Path(path)
    if not p.exists():
        return {"by_doi": by_doi, "by_title": by_title, "n_rows": 0}
    n = 0
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            aid = str(row.get("arxiv_id") or "").strip()
            if not aid:
                continue
            n += 1
            d = doi_of(row.get("doi") or "")
            if d:
                by_doi.setdefault(d, aid)
            t = norm_title(row.get("title") or "")
            if len(t) >= 40:
                by_title.setdefault(t, []).append(aid)
    return {"by_doi": by_doi, "by_title": by_title, "n_rows": n}


def backfill_paper_ids(graph: Any, *,
                       csv_path: str | Path = DEFAULT_PAPERS_CSV,
                       title_min_len: int = 40,
                       overwrite: bool = False) -> Dict[str, Any]:
    """给 ``Paper`` 节点补 ``arxiv_id`` / ``aliases``，返回统计。"""
    idx = load_corpus_index(csv_path)
    stats: Dict[str, Any] = {"n_papers": 0, "by_doi": 0, "by_title": 0,
                             "already": 0, "unmatched": 0, "corpus_rows": idx["n_rows"],
                             "samples": [], "unmatched_samples": []}
    for p in graph.by_type("Paper"):
        stats["n_papers"] += 1
        if p.attrs.get("arxiv_id") and not overwrite:
            stats["already"] += 1
            continue
        aid = ""
        source = ""
        d = doi_of(p.attrs.get("doi") or "")
        if d and d in idx["by_doi"]:
            aid, source = idx["by_doi"][d], "doi"
        else:
            t = norm_title(p.attrs.get("title") or "")
            hits = idx["by_title"].get(t) if len(t) >= title_min_len else None
            if hits and len(set(hits)) == 1:      # 标题必须唯一，避免错配
                aid, source = hits[0], "title"
        if not aid:
            stats["unmatched"] += 1
            if len(stats["unmatched_samples"]) < 8:
                stats["unmatched_samples"].append(
                    {"paper": p.id, "title": str(p.attrs.get("title") or "")[:60],
                     "doi": str(p.attrs.get("doi") or "")[:40]})
            continue
        aliases = list(dict.fromkeys(
            list(p.attrs.get("aliases") or [])
            + [aid, f"arXiv:{aid}", f"{aid}.pdf"]))
        p.attrs["arxiv_id"] = aid
        p.attrs["aliases"] = aliases
        p.attrs["alias_source"] = source
        p.attrs["alias_confidence"] = 1.0 if source == "doi" else 0.8
        p.attrs["alias_backfilled_at"] = now_iso()
        stats["by_doi" if source == "doi" else "by_title"] += 1
        if len(stats["samples"]) < 8:
            stats["samples"].append({"paper": p.id, "arxiv_id": aid, "source": source})
    return stats
