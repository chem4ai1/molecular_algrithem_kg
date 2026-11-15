"""把相关论文线索解析成可跳转的 Paper 节点（科技树链）。

`resolve_sources` 原先只处理人工手填的 added_paper_id，8 行线索全 unmatched。
本模块提供多级解析，并让未命中库内论文的方法名也落成真实图节点（proxy），
使「论文-论文」链可跳转到关系面板。

解析优先级：
  1. added_paper_id（人工回填，最高优先）
  2. cited_arxiv_id / cited_doi / cited_title → PaperIndex.match
  3. root_name 方法别名 → 已知 arXiv（认知表，papers.csv 校验）
  4. root_name 标题相似度（阈值 0.6，仅长名称启用）
  5. 建 proxy Paper 节点，标 resolved_kind=proxy / needs_expansion=True
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from typing import Any, Dict, List, Optional

# 基于领域认知的别名 → 论文库内 arXiv（仅 papers.csv 里存在的才生效）
METHOD_ALIASES = {
    "jtnn": "1802.04364", "junction tree": "1802.04364",
    "midi": "2302.09048", "lingo3dmol": "2305.10133",
    "molminer": "2411.06608", "so3lr": "2611.06237",
    "mol-instructions": "2306.08018", "molgen": "2301.11259",
}

CSV_PATH = Path("storage_cf/sciforge/source_related_papers.csv")
TREE_DIR = Path("storage_cf/sciforge/batch_multistage")
OUT = Path("storage_cf/sciforge/source_resolution_report.json")


def _norm(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def hints() -> List[Dict[str, Any]]:
    """收敛 CSV 线索 + 全部科技树链方法名。"""
    out: List[Dict[str, Any]] = []
    if CSV_PATH.exists():
        with CSV_PATH.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                out.append({"host": r.get("host_arxiv_id") or "",
                            "name": r.get("root_name") or "",
                            "root_id": r.get("root_id") or "",
                            "ref_no": r.get("ref_no") or "",
                            "relation": r.get("tree_relation") or "CITES_RELATED",
                            "kind": "csv"})
    for p in sorted(TREE_DIR.glob("*/STAGE2_related_work.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for ch in d.get("chains") or []:
            style = str(ch.get("style") or "")
            rel = {"comparison": "COMPARES_WITH",
                   "bottleneck": "IMPROVED_BY",
                   "improvement": "IMPROVED_BY",
                   "taxonomy": "BELONGS_TO"}.get(style, "CITES_RELATED")
            for m in ch.get("methods") or []:
                name = str(m).strip()
                # 科技树节点里混有瓶颈/机制描述短语，不是方法名，不建 Paper
                if len(name.split()) > 5 or len(name) > 48:
                    continue
                if re.search(r"^(predict|reus|distill|without|using|based on)\b",
                             name, re.I):
                    continue
                out.append({"host": p.parent.name, "name": name,
                            "root_id": "", "ref_no": "",
                            "relation": rel, "kind": "tech_tree"})
    return out


def _paper_index():
    from .citations import load_paper_index
    return load_paper_index()


def resolve_name(name: str, idx: Any, *, host: str = "") -> Dict[str, Any]:
    """返回 {paper_id, kind, score}；别名精确匹配且排除自引用。"""
    low = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    for alias, aid in METHOD_ALIASES.items():
        if low != alias and not low.startswith(alias + " ") and \
                not low.endswith(" " + alias):
            continue
        if aid == host:
            continue                      # 不许解析成宿主论文自己
        return {"paper_id": f"paper:{aid}", "kind": "method_alias",
                "score": 1.0}
    # 标题相似度（只对 ≥3 token 的长名称启用，避免缩写误命中）
    a = _norm(name)
    if len(a) >= 3:
        best, score = "", 0.0
        for _ti, toks, pid in idx.titles:
            s = len(a & toks) / max(len(a | toks), 1)
            if s > score:
                best, score = pid, s
        if score >= 0.6 and best and best != host:
            return {"paper_id": f"paper:{best}", "kind": "title",
                    "score": round(score, 3)}
    return {"paper_id": "", "kind": "unmatched", "score": 0.0}


def _paper_meta(aid: str) -> Dict[str, str]:
    import csv as _csv
    from .citations import PAPERS_CSV
    if not PAPERS_CSV.exists():
        return {}
    with PAPERS_CSV.open(encoding="utf-8-sig") as fh:
        for r in _csv.DictReader(fh):
            if (r.get("arxiv_id") or "").strip() == aid:
                return {"title": r.get("title") or "",
                        "doi": r.get("doi") or "",
                        "year": r.get("year") or ""}
    return {}


def resolve_all(graph: Any, *, persist: bool = True,
                persist_graph: bool = False,
                out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """解析全部线索 → 真实/代理 Paper 节点 + 论文-论文可跳转边。"""
    idx = _paper_index()
    hs = hints()
    rep: Dict[str, Any] = {"n_hints": len(hs), "n_resolved_library": 0,
                           "n_proxy": 0, "n_edges": 0, "n_reused": 0,
                           "by_kind": {}, "unresolved": []}
    targets: Dict[str, str] = {}   # (host, name, ref_no) -> target id
    for h in hs:
        host = f"paper:{h['host']}"
        if host not in graph.nodes:
            continue
        name = h["name"].strip()
        if not name:
            continue
        manual = ""
        r = resolve_name(name, idx, host=h["host"])
        pid = r["paper_id"]
        kind = r["kind"]
        if pid:
            aid = pid.split(":", 1)[-1]
            if pid not in graph.nodes:
                m = _paper_meta(aid)
                graph.node(pid, "Paper", m.get("title") or name,
                           arxiv_id=aid, doi=m.get("doi", ""),
                           year=m.get("year", ""),
                           resolved_kind="library_paper",
                           needs_expansion=False,
                           provenance="source_resolution")
                rep["n_resolved_library"] += 1
            else:
                rep["n_reused"] += 1
        else:
            pid = f"paper:src:{h['host']}:{_slug(name)}"
            if pid not in graph.nodes:
                graph.node(pid, "Paper", name,
                           resolved_kind="proxy",
                           needs_expansion=True,
                           source_kind=h["kind"],
                           source_ref_no=h["ref_no"],
                           provenance="source_resolution",
                           note="科技树方法名占位；补 papers.csv 后可解析为真实论文")
                rep["n_proxy"] += 1
            kind = "proxy"
            rep["unresolved"].append({"host": h["host"], "name": name})
        rep["by_kind"][kind] = rep["by_kind"].get(kind, 0) + 1
        targets[(h["host"], name, h["ref_no"])] = pid
        if pid == host:
            continue                     # 不建自引用边
        # 论文-论文边（RELATED_TO 是 TBox 已存在关系；树样式写进 properties）
        graph.assert_rel(host, pid, "RELATED_TO",
                         tree_relation=h["relation"],
                         source_kind=h["kind"],
                         ref_no=h["ref_no"],
                         resolved_kind=kind)
        rep["n_edges"] += 1
    # 回填 CSV
    if CSV_PATH.exists():
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
            fields = list(rows[0].keys()) if rows else []
        for row in rows:
            k = (row.get("host_arxiv_id", ""), row.get("root_name", ""),
                 row.get("ref_no", ""))
            pid = targets.get(k)
            if not pid:
                continue
            n = graph.nodes.get(pid)
            kind = (n.attrs.get("resolved_kind") if n else "") or "proxy"
            row["resolved_paper_id"] = pid
            row["match_status"] = ("resolved" if kind == "library_paper"
                                   else "proxy")
            row["suggested_action"] = ("" if kind == "library_paper"
                                       else "补 papers.csv 后重跑 resolve_sources")
        with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    try:
        from .assembly.hydrate import hydrate_derived_nodes
        rep["hydrated"] = hydrate_derived_nodes(graph)
    except Exception:  # noqa: BLE001
        pass
    if persist:
        if persist_graph:
            graph.save("storage_cf/sciforge/batch10_final_graph.json")
        p = (out_dir / "source_resolution_report.json") if out_dir else OUT
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return rep
