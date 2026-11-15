"""语义层溯源：节点 → 论文的追踪、审计、缺失清单导出与自动修复。

溯源证据优先级（从强到弱）：
  1. 图内关系（PROPOSES_METHOD / EVALUATED_ON / RELATED_TO / SUBCLASS_OF）
  2. 节点 `paper_id` 属性（谱系补建时写入）
  3. 抽取报告 `semantic_extraction/<aid>.json`（E2/E3/E6 的 evidence）
  4. `model_results[].paper_id` + `provenance`（表格单元格级）
  5. 向量检索建议（按标题相似度，只作为 suggested，不算已溯源）
"""
from __future__ import annotations
import os
import csv, json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SEM_GRAPH = Path("storage_cf/sciforge/batch10_semantic_v4.json")
EXTRACT_DIR = Path("storage_cf/sciforge/semantic_extraction")
PAPERS_CSV = Path(os.environ.get("CAPFACTORY_PAPERS_CSV",
                                "data/papers.csv"))
OUT_DIR = Path("storage_cf/sciforge/provenance")
INDEX = OUT_DIR / "provenance_index.json"

BACK_RELS = {"Algorithm": ("PROPOSES_METHOD", "RELATED_TO",
                           "SUBCLASS_OF"),
             "Benchmark": ("EVALUATED_ON",),
             "AlgorithmModule": ("HAS_MODULE",),
             "CodeFunction": ("HAS_FUNCTION", "MODULE_IMPLEMENTED_BY"),
             "CodeRepository": ("HAS_CODE",)}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _reports() -> Dict[str, Dict[str, Any]]:
    out = {}
    for p in sorted(EXTRACT_DIR.glob("*.json")):
        if not re.match(r"\d{4}\.\d{4,5}\.json", p.name):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out[d["arxiv_id"]] = d
        except Exception:  # noqa: BLE001
            pass
    return out


def _paper_index(graph) -> Dict[str, Any]:
    out = {}
    for p in graph.by_type("Paper"):
        out[p.id] = {"id": p.id, "arxiv_id": str(p.attrs.get("arxiv_id") or ""),
                     "title": p.label}
    return out


def _paper_catalog() -> List[Dict[str, str]]:
    if not PAPERS_CSV.exists():
        return []
    rows = []
    with PAPERS_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            t = (r.get("title") or "").strip()
            a = (r.get("arxiv_id") or "").strip()
            if t:
                rows.append({"arxiv_id": a, "title": t})
    return rows


def suggest_paper(name: str, catalog: List[Dict[str, str]],
                  *, limit: int = 1) -> List[Dict[str, str]]:
    """按标题 token 重合给建议（只作 suggested，不自动认定）。"""
    toks = set(re.findall(r"[a-z0-9]{3,}", (name or "").lower()))
    if not toks:
        return []
    scored = []
    for r in catalog:
        tt = set(re.findall(r"[a-z0-9]{3,}", r["title"].lower()))
        s = len(toks & tt) / max(len(toks | tt), 1)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [{"suggested_arxiv_id": r["arxiv_id"],
             "suggested_title": r["title"][:110],
             "similarity": round(s, 3)} for s, r in scored[:limit]
            if s >= 0.15]


def trace(graph, node_id: str, reports=None) -> Dict[str, Any]:
    """单节点溯源详情。"""
    reports = reports if reports is not None else _reports()
    n = graph.nodes.get(node_id)
    if not n:
        return {"node_id": node_id, "found": False}
    papers = _paper_index(graph)
    rels: List[Dict[str, str]] = []
    for a in graph.assertions:
        if a.target != node_id and a.source != node_id:
            continue
        other = a.source if a.target == node_id else a.target
        o = graph.nodes.get(other)
        if o and o.type == "Paper":
            rels.append({"paper_id": o.id,
                         "arxiv_id": str(o.attrs.get("arxiv_id") or ""),
                         "title": o.label[:110], "relation": a.relation,
                         "direction": "in" if a.target == node_id else "out"})
    attr_pid = n.attrs.get("paper_id")
    # 抽取报告里作为算法/基准/谱系出现
    report_hits = []
    label_norm = _norm(n.label)
    for aid, rep in reports.items():
        e2 = (rep["stages"].get("E2_algorithm") or {}).get("data") or {}
        e3 = (rep["stages"].get("E3_benchmark") or {}).get("data") or {}
        lin = rep.get("lineage", {}).get("all") or []
        hit = []
        if any(_norm(a.get("name")) == label_norm
               for a in e2.get("algorithms") or []):
            hit.append("E2_algorithm")
        if any(_norm(b.get("name")) == label_norm
               for b in e3.get("benchmarks") or []):
            hit.append("E3_benchmark")
        if any(_norm(x.get("from")) == label_norm
               or _norm(x.get("to")) == label_norm for x in lin):
            hit.append("E6_lineage")
        if hit:
            report_hits.append({"arxiv_id": aid, "stages": hit,
                                "report": str(EXTRACT_DIR / (aid + ".json"))})
    # 单元格级溯源：图内行 + 抽取报告的 provenance/evidence join
    report_cells: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for _aid, rep in reports.items():
        for r in ((rep.get("model_results") or {}).get("rows") or []):
            key = (str(r.get("model_name") or r.get("model") or ""),
                   str(r.get("metric_name") or r.get("metric") or ""),
                   str(r.get("value_raw") or r.get("value") or ""))
            report_cells[key] = r
    cells: List[Dict[str, Any]] = []
    for i, r in enumerate(n.attrs.get("model_results") or []):
        model = str(r.get("model_name") or r.get("model") or "")
        metric = str(r.get("metric_name") or r.get("metric") or "")
        value = str(r.get("value_raw") or r.get("value") or "")
        src = report_cells.get((model, metric, value), {})
        if not (r.get("paper_id") or src.get("paper_id")
                or src.get("provenance")):
            continue
        cells.append({
            "cell_id": f"{node_id}#cell:{i}",
            "model": model, "metric": metric, "value": value,
            "unit": r.get("unit") or src.get("unit") or "",
            "paper_id": (r.get("paper_id") or src.get("paper_id") or ""),
            "source": (r.get("source") or src.get("source") or ""),
            "provenance": (src.get("provenance")
                           or r.get("provenance") or ""),
            "evidence": (src.get("evidence") or r.get("evidence") or ""),
            "table_ref": (src.get("table_id") or src.get("source")
                          or r.get("table_ref") or "")})
    return {"node_id": node_id, "found": True, "type": n.type,
            "label": n.label, "relations": rels,
            "paper_id_attr": attr_pid,
            "report_hits": report_hits,
            "model_result_sources": cells[:10],
            "cells": cells,
            "n_cells": len(cells),
            "traced": bool(rels or attr_pid or report_hits or cells)}


def _audit_index(graph, reports):
    """一次遍历建索引，避免 audit 对每个节点全扫断言（O(N^2)）。"""
    import collections as _c
    paper_rels = _c.defaultdict(set)
    for a in graph.assertions:
        src = graph.nodes.get(a.source)
        dst = graph.nodes.get(a.target)
        if not src or not dst:
            continue
        if dst.type == "Paper":
            paper_rels[src.id].add(dst.id)
        if src.type == "Paper":
            paper_rels[dst.id].add(src.id)
    hits = _c.defaultdict(list)
    for aid, rep in (reports or {}).items():
        st = rep.get("stages") or {}
        for a in ((st.get("E2_algorithm") or {}).get("data") or {}).get("algorithms") or []:
            n = _norm(a.get("name"))
            if n:
                hits[n].append(aid)
        for b in ((st.get("E3_benchmark") or {}).get("data") or {}).get("benchmarks") or []:
            n = _norm(b.get("name"))
            if n:
                hits[n].append(aid)
        for x in (rep.get("lineage") or {}).get("all") or []:
            for k in ("from", "to"):
                n = _norm(x.get(k))
                if n:
                    hits[n].append(aid)
    return paper_rels, hits


def audit(graph, reports=None) -> Dict[str, Any]:
    """全图溯源审计：覆盖率 + 孤儿分类。"""
    reports = reports if reports is not None else _reports()
    catalog = _paper_catalog()
    out: Dict[str, Any] = {"by_type": {}, "catalog_size": len(catalog),
                           "n_reports": len(reports)}
    paper_rels, rep_hits = _audit_index(graph, reports)
    for typ in ("Algorithm", "Benchmark"):
        nodes = graph.by_type(typ)
        traced_relation = traced_attr = traced_report = preset = no_clue = 0
        rows = []
        for n in nodes:
            pids = paper_rels.get(n.id) or set()
            attr = str(n.attrs.get("paper_id") or "")
            rh = rep_hits.get(_norm(n.label)) or []
            if pids:
                traced_relation += 1
                continue
            if attr:
                traced_attr += 1
            elif rh:
                traced_report += 1
            elif n.id.startswith("benchmark:kb:"):
                preset += 1
            else:
                no_clue += 1
            sug = suggest_paper(n.label, catalog)
            rows.append({
                "node_id": n.id, "label": n.label, "type": typ,
                "reason": ("有 paper_id 属性但缺关系" if attr
                           else "抽取报告命中但缺关系" if rh
                           else "预置知识库基准（设计如此）"
                           if n.id.startswith("benchmark:kb:")
                           else "无来源线索"),
                "paper_id_attr": attr,
                "report_hits": ";".join(rh),
                "model_result_sources": len(n.attrs.get("model_results") or []),
                "suggested_arxiv_id": (sug[0]["suggested_arxiv_id"]
                                       if sug else ""),
                "suggested_title": (sug[0]["suggested_title"]
                                    if sug else ""),
                "suggested_similarity": (sug[0]["similarity"] if sug else ""),
                "action": ("自动补关系" if (attr or rh)
                           else "人工确认建议论文" if sug else "待补抽取"),
                "priority": ("high" if (attr or rh) else
                             "low" if n.id.startswith("benchmark:kb:")
                             else "medium")})
        out["by_type"][typ] = {
            "total": len(nodes), "traced_by_relation": traced_relation,
            "traced_by_attr_only": traced_attr,
            "traced_by_report_only": traced_report, "preset_kb": preset,
            "no_clue": no_clue,
            "coverage": round(traced_relation / max(len(nodes), 1), 3),
            "repairable": traced_attr + traced_report, "missing": rows}
    return out


CSV_FIELDS = ("node_id", "label", "type", "reason", "paper_id_attr",
              "report_hits", "model_result_sources",
              "suggested_arxiv_id", "suggested_title",
              "suggested_similarity", "action", "priority")


def export_missing_csv(graph, *, out_dir: Path = OUT_DIR,
                       reports=None) -> Dict[str, Any]:
    """输出「缺论文」的 CSV 清单（算法/基准各一份）+ 审计报告。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    a = audit(graph, reports)
    paths = {}
    for typ, fname in (("Algorithm", "missing_paper_algorithms.csv"),
                       ("Benchmark", "missing_paper_benchmarks.csv")):
        p = out_dir / fname
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            w.writeheader()
            for r in a["by_type"][typ]["missing"]:
                w.writerow({k: r.get(k, "") for k in CSV_FIELDS})
        paths[typ] = str(p)
    (out_dir / "provenance_report.json").write_text(
        json.dumps({k: v for k, v in a.items()},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return {"report": a, "csv": paths,
            "n_missing": {k: len(a["by_type"][k]["missing"])
                          for k in ("Algorithm", "Benchmark")},
            "report_path": str(out_dir / "provenance_report.json")}


def repair(graph, *, persist: bool = False) -> Dict[str, Any]:
    """把「有 paper_id 属性但缺关系」的节点自动补上溯源关系。"""
    from .tbox_v4 import check_domain_range
    out: Dict[str, Any] = {"added": {}, "skipped": [], "n": 0}
    reports = _reports()
    for n in list(graph.by_type("Algorithm")) + list(graph.by_type("Benchmark")):
        t = trace(graph, n.id, reports)
        if t["relations"]:
            continue
        pid = str(t["paper_id_attr"] or "")
        if not pid and t["report_hits"]:
            aid = t["report_hits"][0]["arxiv_id"]
            pid = "paper:" + aid
        if not pid or pid not in graph.nodes:
            continue
        rel = "PROPOSES_METHOD" if n.type == "Algorithm" else "EVALUATED_ON"
        if not check_domain_range("Paper", rel, n.type):
            out["skipped"].append(n.id)
            continue
        graph.assert_rel(pid, n.id, rel, provenance="provenance_repair")
        out["added"][rel] = out["added"].get(rel, 0) + 1
        out["n"] += 1
    if persist:
        graph.save(str(SEM_GRAPH))
    return out


def build_index(graph, *, persist: bool = True) -> Dict[str, Any]:
    """节点 → 论文 正反向索引，供后续溯源修正快速查询。"""
    reports = _reports()
    idx: Dict[str, Any] = {"node_to_papers": {}, "paper_to_nodes": {},
                           "n_nodes": 0}
    for n in graph.nodes.values():
        t = trace(graph, n.id, reports)
        pids = sorted({x["paper_id"] for x in t["relations"]}
                      | ({t["paper_id_attr"]} if t["paper_id_attr"] else set())
                      | {x["arxiv_id"] and ("paper:" + x["arxiv_id"])
                         for x in t["report_hits"] if x["arxiv_id"]})
        if pids:
            idx["node_to_papers"][n.id] = [p for p in pids if p]
            for p in idx["node_to_papers"][n.id]:
                idx["paper_to_nodes"].setdefault(p, []).append(n.id)
            idx["n_nodes"] += 1
    if persist:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return {"n_nodes": idx["n_nodes"],
            "n_papers": len(idx["paper_to_nodes"]), "path": str(INDEX)}
