"""把论文摘要 / PO 节点 / 文本块写入向量库.

每个条目统一为 ``{id, text, meta}``，``meta.kind`` 区分来源：
``abstract`` / ``po_node`` / ``chunk`` / ``image``。这样同一套检索接口
可以跨集合查询，也可用 ``filter_fn`` 只查某一类。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..utils import now_iso
from .embedder import BgeEmbedder
from .store import VectorStore

DEFAULT_DATA = "data"


def _paper_index(data_dir: Path) -> Dict[str, Dict[str, str]]:
    """arxiv_id → papers.csv 行（补 domain / algorithms / year）。"""
    p = data_dir / "papers/papers.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return {r["arxiv_id"]: r for r in csv.DictReader(fh) if r.get("arxiv_id")}


def index_paper_abstracts(data_dir: str | Path = DEFAULT_DATA, *,
                          store: Optional[VectorStore] = None,
                          limit: int = 0, batch_size: int = 16,
                          root: str | Path = "storage_cf/vector") -> VectorStore:
    """索引 ``papers/abstracts/*.json``（含标题），可选 ``limit`` 控制首跑规模。"""
    root_dir = Path(data_dir)
    st = store or VectorStore(root, "papers",
                              BgeEmbedder(batch_size=batch_size))
    abs_dir = root_dir / "papers/abstracts"
    if not abs_dir.is_dir():
        return st
    rows = _paper_index(root_dir)
    files = sorted(abs_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    items: List[Dict[str, Any]] = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        aid = str(d.get("arxiv_id") or f.stem)
        title = str(d.get("title") or "").strip()
        abstract = str(d.get("abstract") or "").strip()
        if not (title or abstract):
            continue
        row = rows.get(aid, {})
        text = f"{title}\n\n{abstract}".strip()
        items.append({
            "id": f"paper:{aid}",
            "text": text[:4000],
            "meta": {"kind": "abstract", "arxiv_id": aid, "title": title,
                     "published": d.get("published", ""),
                     "domain": row.get("domain", ""),
                     "algorithms": row.get("algorithms", ""),
                     "year": row.get("year", ""),
                     "paper_id": row.get("paper_id", "")},
        })
    added = st.add(items)
    st.meta.update({"source": str(abs_dir), "indexed_at": now_iso(),
                    "added_last_run": added})
    st.save()
    return st


def index_po_graph(graph: Any, *, store: Optional[VectorStore] = None,
                   root: str | Path = "storage_cf/vector",
                   kinds: Sequence[str] = ("Paper", "CapabilityClaim", "MetricObservation",
                                           "Evidence", "CodeArtifact", "Dataset",
                                           "ResearchProblem", "Algorithm"),
                   limit: int = 0, batch_size: int = 16) -> VectorStore:
    """把 PO 图节点转成可检索文本（类型 + 标签 + 关键属性 + 定义）。"""
    from ..po.semantics import CONCEPT_SEMANTICS
    st = store or VectorStore(root, "po_nodes", BgeEmbedder(batch_size=batch_size))
    items: List[Dict[str, Any]] = []
    for n in graph.nodes.values():
        t = getattr(n, "type", "")
        if kinds and t not in kinds:
            continue
        attrs = getattr(n, "attrs", {}) or {}
        parts = [t, str(getattr(n, "label", "")), CONCEPT_SEMANTICS.get(t, {}).get("definition", "")]
        for k in ("statement", "scope", "definition", "interpretation", "quote",
                  "metric", "unit", "domain_codes", "algo_codes", "availability",
                  "license", "rule", "version_status"):
            v = attrs.get(k)
            if isinstance(v, (str, int, float)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, list):
                parts.append(f"{k}: {', '.join(str(x) for x in v[:6])}")
        text = " | ".join(p for p in parts if p)[:2000]
        items.append({"id": str(getattr(n, "id", "")), "text": text,
                      "meta": {"kind": "po_node", "type": t,
                               "attribution": getattr(n, "attribution", ""),
                               "domain_codes": attrs.get("domain_codes", []),
                               "algo_codes": attrs.get("algo_codes", [])}})
    if limit:
        items = items[:limit]
    st.add(items)
    st.meta.update({"source": "POGraph", "indexed_at": now_iso()})
    st.save()
    return st


def index_texts(items: Sequence[Dict[str, Any]], *, name: str = "chunks",
                root: str | Path = "storage_cf/vector",
                batch_size: int = 16) -> VectorStore:
    """索引任意文本（``items[i] = {id, text, meta}``），供 PDF 块/图片描述复用。"""
    st = VectorStore(root, name, BgeEmbedder(batch_size=batch_size))
    st.add(items)
    st.save()
    return st


def demo_queries(store: VectorStore, queries: Sequence[str],
                 top_k: int = 3) -> List[Dict[str, Any]]:
    """对一组查询跑检索，返回带延迟的结果（用于效果观察/回归）。"""
    import time
    out = []
    for q in queries:
        t0 = time.time()
        hits = store.search(q, top_k=top_k)
        out.append({"query": q, "latency_ms": round((time.time() - t0) * 1000, 1),
                    "hits": hits})
    return out
