"""Stage3：只做「相关论文 / 算法 / benchmark」三类出处，输出三份 CSV。

与旧 citations.py 不同：
* **不建 Citation 条目节点**，不建 Paper-CITES-> 全部参考文献的全量边；
* 参考文献节只作**临时索引**（ref_no → title/arxiv/doi），用完即弃；
* 只有三类根对象的出处才建 SourcePaper 节点；三份 CSV 各自独立；
* 仍全部用规则匹配（arXiv → DOI → 标题 token 相似度）。
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .citations import (parse_references, find_root_refs, load_paper_index,
                        _graph_paper, PaperIndex)

OUT_DIR = Path("storage_cf/sciforge")
CSV_PATHS = {
    "related_paper": OUT_DIR / "source_related_papers.csv",
    "algorithm": OUT_DIR / "source_algorithms.csv",
    "benchmark": OUT_DIR / "source_benchmarks.csv",
}
FIELDS = ["host_arxiv_id", "source_kind", "root_name", "root_id", "ref_no",
          "cited_title", "cited_arxiv_id", "cited_doi", "cited_year",
          "tree_relation", "evidence", "match_status", "resolved_paper_id",
          "added_paper_id", "suggested_action"]


def _ref_index(md: str) -> Dict[str, Dict[str, Any]]:
    """参考文献只作临时索引，不落图节点。"""
    return {r["ref_no"]: r for r in parse_references(md)}


def _roots(graph: Any, kind: str,
           tree_methods: Sequence[str]) -> List[Tuple[str, str]]:
    if kind == "related_paper":
        return [(m, f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+', '_', m.lower())[:40]}")
                for m in tree_methods[:12]]
    typ = "Algorithm" if kind == "algorithm" else "Benchmark"
    return [(n.label, n.id) for n in graph.by_type(typ)]


def build_sources(graph: Any, *, arxiv_id: str, paper_id: str, md: str,
                  tree: Optional[Dict[str, Any]] = None,
                  index: Optional[PaperIndex] = None,
                  out_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    idx = index or load_paper_index()
    refs = _ref_index(md)
    tree = tree or {}
    chains = tree.get("chains") or []
    tree_methods: List[str] = []
    tree_relation: Dict[str, str] = {}
    for c in chains:
        for m in c.get("methods") or []:
            if m not in tree_methods:
                tree_methods.append(m)
        for e in c.get("edges") or []:
            tree_relation[str(e.get("src") or e.get("dst") or "")] = \
                str(e.get("rel") or "")
    rep: Dict[str, Any] = {"arxiv_id": arxiv_id, "by_kind": {}, "csv": {}}
    host_title = str(graph.nodes[paper_id].label or "").lower() \
        if paper_id in graph.nodes else ""

    for kind in ("related_paper", "algorithm", "benchmark"):
        rows: List[Dict[str, Any]] = []
        made = 0
        for name, rid in _roots(graph, kind, tree_methods):
            if not name or (kind != "related_paper" and
                            name.lower() in host_title):
                continue
            for refno in find_root_refs(md, name, max_refs=2):
                ref = refs.get(refno, {})
                pid, mkind, score = idx.match(ref) if ref else ("", "unmatched", 0.0)
                sid = f"sourcepaper:{arxiv_id}:{kind}:{refno}"
                if sid not in graph.nodes:
                    graph.node(sid, "SourcePaper", f"{kind}:{name[:30]}[{refno}]",
                        root_type=kind, root_id=rid, source_kind=kind,
                        ref_no=refno, tree_relation=tree_relation.get(name, ""),
                        evidence=ref.get("raw", "")[:200],
                        needs_expansion=not bool(pid), resolved_paper_id=pid,
                        match_kind=mkind, match_score=score,
                        host_paper=paper_id,
                        source=f"data/docx/{arxiv_id}.md#[{refno}]",
                        provenance="source_rule")
                    made += 1
                rel = "SITUATED_IN" if kind == "related_paper" else "SOURCED_FROM"
                graph.assert_rel(
                    paper_id if kind == "related_paper" else rid, sid, rel)
                if pid:
                    graph.assert_rel(sid, _graph_paper(graph, pid),
                                     "RESOLVED_TO")
                rows.append({
                    "host_arxiv_id": arxiv_id, "source_kind": kind,
                    "root_name": name, "root_id": rid, "ref_no": refno,
                    "cited_title": ref.get("title", ""),
                    "cited_arxiv_id": ref.get("arxiv_id", ""),
                    "cited_doi": ref.get("doi", ""),
                    "cited_year": ref.get("year", ""),
                    "tree_relation": tree_relation.get(name, ""),
                    "evidence": (ref.get("raw", "") or "")[:160],
                    "match_status": mkind if pid else "unmatched",
                    "resolved_paper_id": pid, "added_paper_id": "",
                    "suggested_action": ("补 papers.csv 后重跑 resolve_sources"
                                         if not pid else "可沿 RESOLVED_TO 深挖")})
        rep["by_kind"][kind] = {
            "rows": len(rows), "nodes": made,
            "resolved": sum(1 for r in rows if r["resolved_paper_id"])}
        rep["csv"][kind] = _write(CSV_PATHS[kind], rows, arxiv_id)

    out = Path(out_dir or OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    (out / "SOURCE_INDEX.json").write_text(
        json.dumps({k: v for k, v in rep.items() if k != "csv"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    rep["csv_paths"] = {k: str(v) for k, v in CSV_PATHS.items()}
    return rep


def _write(path: Path, rows: List[Dict[str, Any]], aid: str) -> int:
    """按类落盘；保留用户填过的 added_paper_id，空 run 不覆盖既有清单。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    prev: Dict[Tuple[str, str, str], str] = {}
    other_hosts: List[Dict[str, str]] = []
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                k = (r.get("host_arxiv_id", ""), r.get("root_name", ""),
                     r.get("ref_no", ""))
                if (r.get("added_paper_id") or "").strip():
                    prev[k] = r["added_paper_id"].strip()
                if r.get("host_arxiv_id") != aid:
                    other_hosts.append({f: r.get(f, "") for f in FIELDS})
    if not rows and not other_hosts:
        if not path.exists():
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                csv.DictWriter(fh, fieldnames=FIELDS).writeheader()
        return 0
    merged = other_hosts + [{f: r.get(f, "") for f in FIELDS} for r in rows]
    seen: set = set()
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for row in merged:
            k = (row["host_arxiv_id"], row["root_name"], row["ref_no"])
            if k in seen:
                continue
            seen.add(k)
            row["added_paper_id"] = prev.get(k, row.get("added_paper_id", ""))
            w.writerow(row)
    return len(seen)


def resolve_sources(graph: Any, *, out_dir: Any = None,
                    auto: bool = False) -> Dict[str, Any]:
    """回填出处解析（保留旧签名，新增自动解析能力）。

    auto=True 时先用 source_resolution.resolve_all 把相关论文/科技树线索
    解析成真实 Paper 节点（库内命中或 proxy），再处理人工 added_paper_id。
    out_dir 支持 run-scoped 报告（修蓝图 E5）。
    """
    from pathlib import Path
    from .source_resolution import resolve_all
    rep: Dict[str, Any] = {"resolved": 0, "auto": None}
    if auto:
        rep["auto"] = resolve_all(
            graph, persist=True, persist_graph=False,
            out_dir=Path(out_dir) if out_dir else None)
    n = 0
    for kind, path in CSV_PATHS.items():
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            pid = (r.get("added_paper_id") or "").strip()
            if not pid:
                continue
            sid = f"sourcepaper:{r['host_arxiv_id']}:{kind}:{r['ref_no']}"
            if sid in graph.nodes:
                graph.nodes[sid].attrs["needs_expansion"] = False
                graph.nodes[sid].attrs["resolved_paper_id"] = pid
                graph.assert_rel(sid, _graph_paper(graph, pid),
                                 "RESOLVED_TO")
                n += 1
    rep["resolved"] = n
    return rep
