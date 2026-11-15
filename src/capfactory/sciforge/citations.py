"""三阶段抽取的「引用层」：根对象的出处论文 source 节点。

用户定义：抽取时被抽取对象就是根节点，后面都是基于它的延伸。
  Stage 1  Paper     根 → 属性 / 章节 / 问题 / 假设 / **参考文献 Citation**
  Stage 2  Algorithm 根 → 步骤 / 模块 / 公式 / 工具 / 代码 + **source 论文**
  Stage 3  Benchmark 根 → 评测值 / 数据契约 + **source 论文**

算法/基准若在正文里带引用标记（如 ``HierVAE [14]`` / ``ZINC [20]``），
就把该 ref_no 解析成 SourcePaper 节点，并：
  * 命中当前论文库 → ``RESOLVED_TO`` 连到已有 Paper 节点，可继续深挖；
  * 未命中 → 节点仍建立（``needs_expansion=True``），并落
    ``unknown_citations.csv`` 供用户后续扩充论文库，之后可回填。

匹配优先级：arXiv id → DOI → 归一化标题 token 相似度。全部确定性规则。
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path("/home/zengshuxin/xKG-main")
MD_DIR = ROOT / "data/docx"
PAPERS_CSV = ROOT / "data/papers/papers.csv"
CSV_OUT = Path("storage_cf/sciforge/unknown_citations.csv")

CSV_FIELDS = ["host_arxiv_id", "root_type", "root_id", "ref_no",
              "cited_title", "cited_arxiv_id", "cited_doi", "cited_year",
              "raw", "match_status", "added_paper_id", "suggested_action"]

_STOP = {"the", "a", "an", "of", "for", "and", "with", "to", "in", "on",
         "via", "from", "by", "using", "towards", "toward"}


def _norm(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())
            if w not in _STOP}


def parse_references(md: str, *, limit: int = 200) -> List[Dict[str, Any]]:
    """切 ``References`` 节的 ``[n]`` 条目，抽 arXiv id / DOI / 标题 / 年份。"""
    m = re.search(r"\n\s*References\s*\n", md or "", re.I)
    tail = ("\n" + md[m.end():]) if m else ""
    if not tail.strip():
        return []
    parts = re.split(r"\n\s*\[(\d{1,3})\]\s*", tail[:120000])
    out: List[Dict[str, Any]] = []
    for i in range(1, min(len(parts), limit * 2 + 1), 2):
        no, body = parts[i], re.sub(r"\s+", " ", parts[i + 1]).strip()
        if len(body) < 12:
            continue
        arx = re.search(r"arXiv[:\s]*(?:preprint\s*)?(?:arXiv[:\s]*)?(\d{4}\.\d{4,5})",
                        body, re.I)
        doi = re.search(r"doi[:\s]*(10\.[^\s,;]+)", body, re.I)
        yr = re.search(r"\b(19|20)\d{2}[a-z]?\b", body)
        # 标题启发式：首个句号后的、到下一个句号/年份前的片段
        seg = re.split(r"(?<=[a-z]{2})\.\s+", body)
        title = (seg[1] if len(seg) > 1 and len(seg[1]) > 12 else
                 seg[0])[:180]
        out.append({"ref_no": no, "raw": body[:400], "title": title,
                    "arxiv_id": arx.group(1) if arx else "",
                    "doi": (doi.group(1).rstrip(".") if doi else "").lower(),
                    "year": yr.group(0) if yr else ""})
    return out


class PaperIndex:
    """论文库索引：arxiv / doi / 标题 token。"""

    def __init__(self, rows: List[Dict[str, str]]) -> None:
        self.by_arxiv: Dict[str, str] = {}
        self.by_doi: Dict[str, str] = {}
        self.titles: List[Tuple[str, set, str]] = []
        for r in rows:
            pid = (r.get("arxiv_id") or r.get("paper_id") or "").strip()
            if not pid:
                continue
            if (r.get("arxiv_id") or "").strip():
                self.by_arxiv[r["arxiv_id"].strip()] = pid
            if (r.get("doi") or "").strip():
                self.by_doi[r["doi"].strip().lower()] = pid
            ti = (r.get("title") or "").strip()
            if ti:
                self.titles.append((ti, _norm(ti), pid))

    def match(self, ref: Dict[str, Any], *, threshold: float = 0.72
              ) -> Tuple[str, str, float]:
        """返回 (paper_id, match_kind, score)。"""
        if ref.get("arxiv_id") and ref["arxiv_id"] in self.by_arxiv:
            return self.by_arxiv[ref["arxiv_id"]], "arxiv_id", 1.0
        if ref.get("doi") and ref["doi"] in self.by_doi:
            return self.by_doi[ref["doi"]], "doi", 1.0
        a = _norm(ref.get("title") or ref.get("raw") or "")
        if not a:
            return "", "unmatched", 0.0
        best, score = "", 0.0
        for _ti, toks, pid in self.titles:
            inter = len(a & toks)
            s = inter / max(len(a | toks), 1)
            if s > score:
                best, score = pid, s
        return (best, "title", round(score, 3)) if score >= threshold \
            else ("", "unmatched", round(score, 3))


def load_paper_index() -> PaperIndex:
    with open(PAPERS_CSV, encoding="utf-8-sig") as fh:
        return PaperIndex(list(csv.DictReader(fh)))


def _body_before_references(md: str) -> str:
    m = re.search(r"\n\s*References\s*\n", md or "", re.I)
    return (md[:m.start()] if m else md)[:200000]


def find_root_refs(md: str, label: str, *, max_refs: int = 3,
                   max_distance: int = 60) -> List[str]:
    """找「根对象名 + [n]」共现的引用编号（同句优先，按距离排序）。"""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", label or "")
             if len(w) > 2]
    if not words:
        return []
    key = words[0].lower()
    body = _body_before_references(md)
    hits: List[Tuple[int, str]] = []
    for line in body.splitlines():
        if key not in line.lower():
            continue
        pos = line.lower().find(key)
        for m in re.finditer(r"\[(\d{1,3})\]", line):
            d = abs(m.start() - pos)
            if d <= max_distance:      # 只认「名字附近」的引用，避免同行噪声
                hits.append((d, m.group(1)))
    if not hits:
        return []
    hits.sort(key=lambda x: x[0])
    out: List[str] = []
    for _d, n in hits:
        if n not in out:
            out.append(n)
        if len(out) >= max_refs:
            break
    return out


def _graph_paper(graph: Any, pid: str) -> str:
    """解析到图内 Paper；库内命中但图内没有时建轻量 proxy 节点。"""
    node_id = f"paper:{pid}"
    if node_id not in graph.nodes:
        graph.node(node_id, "Paper", f"cited:{pid}", arxiv_id=pid,
                   from_citation=True, in_graph=False,
                   source="papers.csv citation match",
                   provenance="citation_resolve")
    return node_id


def build_citation_layer(graph: Any, *, papers: List[Tuple[str, str]],
                         out_dir: Optional[str | Path] = None,
                         index: Optional[PaperIndex] = None
                         ) -> Dict[str, Any]:
    """三阶段抽取的引用层：建 Citation / SourcePaper 并链接到 Paper。"""
    index = index or load_paper_index()
    rep: Dict[str, Any] = {"papers": {},
        "totals": {"citations": 0, "resolved": 0, "unresolved": 0,
                   "source_papers": 0, "source_resolved": 0,
                   "proxy_papers": 0}, "csv_rows": []}
    for aid, pid in papers:
        f = MD_DIR / f"{aid}.md"
        if not f.exists() or pid not in graph.nodes:
            continue
        md = f.read_text(encoding="utf-8", errors="replace")
        refs = parse_references(md)
        by_no: Dict[str, str] = {}
        host: Dict[str, Any] = {"n_refs": len(refs), "citations": [],
                                "sources": []}
        for ref in refs:
            cid = f"citation:{aid}:{ref['ref_no']}"
            matched_id, kind, score = index.match(ref)
            graph.node(cid, "Citation", f"[{ref['ref_no']}] {ref['title'][:60]}",
                       ref_no=ref["ref_no"], raw=ref["raw"], title=ref["title"],
                       arxiv_id=ref["arxiv_id"], doi=ref["doi"], year=ref["year"],
                       match_status=kind, match_score=score,
                       matched_paper_id=matched_id,
                       source=f"data/docx/{aid}.md#references",
                       provenance="citation_parse")
            by_no[ref["ref_no"]] = cid
            graph.assert_rel(pid, cid, "CITES")
            rep["totals"]["citations"] += 1
            if matched_id:
                target = _graph_paper(graph, matched_id)
                graph.assert_rel(cid, target, "RESOLVES_TO")
                graph.assert_rel(pid, target, "CITES_PAPER")
                rep["totals"]["resolved"] += 1
                if graph.nodes[target].attrs.get("from_citation"):
                    rep["totals"]["proxy_papers"] += 1
            else:
                rep["totals"]["unresolved"] += 1
                rep["csv_rows"].append({
                    "host_arxiv_id": aid, "root_type": "Citation",
                    "root_id": cid, "ref_no": ref["ref_no"],
                    "cited_title": ref["title"],
                    "cited_arxiv_id": ref["arxiv_id"], "cited_doi": ref["doi"],
                    "cited_year": ref["year"], "raw": ref["raw"],
                    "match_status": "unmatched", "added_paper_id": "",
                    "suggested_action": "补 papers.csv 后重跑 resolve_pending_sources"})
            host["citations"].append({"ref_no": ref["ref_no"],
                                      "match": kind, "paper": matched_id})

        # Stage 2/3：Algorithm 与 Benchmark 的 source 论文（有引用才建）
        host_title = str(graph.nodes[pid].label or "").lower()
        for root_type in ("Algorithm", "Benchmark"):
            for n in graph.by_type(root_type):
                # 本论文自己的方法名出现在标题里时不建 source（自引用噪声）
                if n.label and n.label.lower() in host_title:
                    continue
                for refno in find_root_refs(md, n.label):
                    cid = by_no.get(refno)
                    if not cid:
                        continue
                    sid = f"sourcepaper:{aid}:{root_type}:{refno}"
                    cit = graph.nodes[cid]
                    matched_id = str(cit.attrs.get("matched_paper_id") or "")
                    graph.node(sid, "SourcePaper",
                               f"source[{refno}] of {n.label[:36]}",
                               root_type=root_type, root_id=n.id, ref_no=refno,
                               needs_expansion=not bool(matched_id),
                               resolved_paper_id=matched_id,
                               match_kind=cit.attrs.get("match_status", ""),
                               match_score=cit.attrs.get("match_score", 0),
                               host_paper=pid,
                               source=f"data/docx/{aid}.md#[{refno}]",
                               provenance="citation_source")
                    graph.assert_rel(n.id, sid, "SOURCED_FROM")
                    graph.assert_rel(sid, cid, "REFERS_TO")
                    rep["totals"]["source_papers"] += 1
                    if matched_id:
                        graph.assert_rel(sid, _graph_paper(graph, matched_id),
                                         "RESOLVED_TO")
                        rep["totals"]["source_resolved"] += 1
                    else:
                        rep["csv_rows"].append({
                            "host_arxiv_id": aid, "root_type": root_type,
                            "root_id": n.id, "ref_no": refno,
                            "cited_title": cit.attrs.get("title", ""),
                            "cited_arxiv_id": cit.attrs.get("arxiv_id", ""),
                            "cited_doi": cit.attrs.get("doi", ""),
                            "cited_year": cit.attrs.get("year", ""),
                            "raw": cit.attrs.get("raw", ""),
                            "match_status": "unmatched", "added_paper_id": "",
                            "suggested_action":
                                f"扩充论文库以便深挖 {root_type} 的出处"})
                    host["sources"].append({"root": n.id,
                                           "root_type": root_type,
                                           "ref_no": refno,
                                           "resolved": bool(matched_id)})
        rep["papers"][aid] = host

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write_csv(CSV_OUT, rep["csv_rows"])
        (out / "CITATION_INDEX.json").write_text(
            json.dumps({k: v for k, v in rep.items() if k != "csv_rows"},
                       ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    return rep


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """未命中引用落盘供用户扩充；保留既有人工填写的 added_paper_id。

    局部 run / 测试可能只带 1 篇论文甚至 0 行，此时**不得覆盖**全局清单，
    否则用户待扩充的条目会被静默抹掉。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv as _csv
    if not rows:
        if not path.exists():
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                _csv.DictWriter(fh, fieldnames=CSV_FIELDS).writeheader()
        return
    prev: Dict[Tuple[str, str, str], str] = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("added_paper_id") or "").strip():
                    prev[(r.get("host_arxiv_id", ""), r.get("root_id", ""),
                          r.get("ref_no", ""))] = r["added_paper_id"].strip()
    seen: set = set()
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            k = (r["host_arxiv_id"], r["root_id"], r["ref_no"])
            if k in seen:
                continue
            seen.add(k)
            row = {f: r.get(f, "") for f in CSV_FIELDS}
            row["added_paper_id"] = prev.get(k, "")
            w.writerow(row)


def resolve_pending_sources(graph: Any, *, csv_path: Optional[str | Path] = None
                            ) -> Dict[str, Any]:
    """用户扩充 CSV（填 added_paper_id）后回填 RESOLVED_TO 与 RESOLVES_TO。"""
    path = Path(csv_path or CSV_OUT)
    if not path.exists():
        return {"resolved": 0, "rows": 0, "csv": str(path)}
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        pid = (r.get("added_paper_id") or "").strip()
        if not pid:
            continue
        target = _graph_paper(graph, pid)
        if target in graph.nodes and graph.nodes[target].attrs.get("from_citation"):
            graph.nodes[target].attrs["from_citation"] = False
            graph.nodes[target].attrs["in_graph"] = True
        rid = r.get("root_id", "")
        if rid.startswith("sourcepaper:"):
            cand = f"sourcepaper:{r['host_arxiv_id']}:{r['root_type']}:{r['ref_no']}"
            if cand in graph.nodes:
                graph.nodes[cand].attrs["needs_expansion"] = False
                graph.nodes[cand].attrs["resolved_paper_id"] = pid
                graph.assert_rel(cand, target, "RESOLVED_TO")
                n += 1
        else:
            if rid in graph.nodes:
                graph.nodes[rid].attrs["match_status"] = "csv_resolved"
                graph.nodes[rid].attrs["matched_paper_id"] = pid
                graph.assert_rel(rid, target, "RESOLVES_TO")
                n += 1
    return {"resolved": n, "rows": len(rows), "csv": str(path)}


def deep_dive_targets(graph: Any) -> List[Dict[str, Any]]:
    """可继续深挖的引用论文：已解析 + 待扩充，按根节点分组。"""
    out: List[Dict[str, Any]] = []
    for s in graph.by_type("SourcePaper"):
        out.append({"source": s.id, "root_type": s.attrs.get("root_type"),
                    "root_id": s.attrs.get("root_id"),
                    "ref_no": s.attrs.get("ref_no"),
                    "resolved_paper_id": s.attrs.get("resolved_paper_id"),
                    "needs_expansion": s.attrs.get("needs_expansion")})
    return out
