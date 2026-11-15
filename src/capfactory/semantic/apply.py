"""把 10 篇的抽取结果回填到语义层图，并重建应用层图。

- E1/E2/E3 写节点属性（按名称对齐已有实例，缺则新建语义层节点）
- E4 追加 Benchmark.model_results（去重）
- E6 只把谱系类（extends/replaces/improves）建 SUBCLASS_OF，带 evidence
- E5 不建语义层节点，只写 application_hints.json（留应用层任务）
"""
from __future__ import annotations
import os
import json, re
from pathlib import Path
from typing import Any, Dict, List

from .tbox_v4 import check_domain_range

EXTRACT_DIR = Path("storage_cf/sciforge/semantic_extraction")
SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")
HINTS = Path("storage_cf/sciforge/semantic_extraction/application_hints.json")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:60]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _find(g, typ, name):
    key = _norm(name)
    for n in g.by_type(typ):
        if _norm(n.attrs.get("name") or n.label) == key:
            return n
    return None


DOMAIN_CN = {"D0": "通用", "D1": "分子生成与从头设计", "D2": "分子优化",
             "D3": "反应/逆合成", "D4": "性质预测", "D5": "多肽与抗菌肽",
             "D6": "蛋白/抗体/RNA", "D7": "材料/晶体/分子动力学",
             "D8": "表征学习/数据集/基准", "D9": "表征学习",
             "D10": "力场/分子模拟"}


def _domain_cn(code: str) -> str:
    return DOMAIN_CN.get(str(code or "").strip().upper(), "")


def _title_of(aid: str) -> str:
    """从 md 首个标题行取论文标题，兜底用 arxiv_id。"""
    f = Path(os.environ.get("CAPFACTORY_PAPERS_DIR", "data/docx")) / (aid + ".md")
    if not f.exists():
        return aid
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
            t = line.strip().lstrip("#").strip()
            if len(t) > 12:
                return t[:200]
    except Exception:  # noqa: BLE001
        pass
    return aid


def _ensure_paper(g, aid: str):
    """找到或创建 Paper 节点（783 篇里多数不在初始图内）。"""
    p = _paper_by_aid(g, aid)
    if p:
        return p
    pid = "paper:" + aid
    if pid in g.nodes:
        return g.nodes[pid]
    g.node(pid, "Paper", _title_of(aid), arxiv_id=aid, title=_title_of(aid))
    return g.nodes[pid]


def _paper_by_aid(g, aid):
    for p in g.by_type("Paper"):
        if str(p.attrs.get("arxiv_id") or "") == aid:
            return p
    return None


def apply_one(g, rep) -> Dict[str, Any]:
    aid = rep["arxiv_id"]
    out: Dict[str, Any] = {"arxiv_id": aid, "updated": {},
                           "created": {}, "relations": {}, "gaps": []}
    # E1 → Paper
    paper = _ensure_paper(g, aid)
    e1 = (rep["stages"].get("E1_paper") or {}).get("data") or {}
    if paper and e1:
        for k in ("research_question", "problem_category", "domain_code",
                  "why_hard", "relation_hints"):
            if e1.get(k):
                paper.attrs[k] = e1[k]
        if rep.get("domain_calibrated"):
            paper.attrs["domain_code"] = rep["domain_calibrated"]
        _cn = _domain_cn(paper.attrs.get("domain_code")
                         or e1.get("domain_code") or "")
        if _cn:
            paper.attrs["domain"] = _cn
        out["updated"]["Paper"] = 1
    # E2 → Algorithm + AlgorithmModule
    e2 = (rep["stages"].get("E2_algorithm") or {}).get("data") or {}
    n_alg = n_mod = n_code = 0
    for a in e2.get("algorithms") or []:
        name = a.get("name")
        if not name:
            continue
        alg = _find(g, "Algorithm", name)
        if not alg:
            g.node("algorithm:" + _slug(name), "Algorithm", name, name=name)
            alg = g.nodes["algorithm:" + _slug(name)]
            n_alg += 1
        for k in ("task_type", "problems_solved", "mechanism",
                  "why_it_works", "applicable_to", "limitations"):
            if a.get(k):
                alg.attrs[k] = a[k]
        if paper and check_domain_range("Paper", "PROPOSES_METHOD", "Algorithm"):
            g.assert_rel(paper.id, alg.id, "PROPOSES_METHOD",
                         paper_id=paper.id)
        for i, m in enumerate(a.get("modules") or []):
            mname = m.get("name")
            if not mname:
                continue
            mid = f"algorithmmodule:{aid}:{_slug(mname)}"
            if mid not in g.nodes:
                g.node(mid, "AlgorithmModule", mname, name=mname,
                       mechanism=m.get("mechanism") or "",
                       formula=m.get("formula") or "",
                       inputs=m.get("inputs") or "",
                       outputs=m.get("outputs") or "")
                n_mod += 1
            else:
                for k in ("mechanism", "formula", "inputs", "outputs"):
                    if m.get(k):
                        g.nodes[mid].attrs[k] = m[k]
            if check_domain_range("Algorithm", "HAS_MODULE",
                                  "AlgorithmModule"):
                g.assert_rel(alg.id, mid, "HAS_MODULE")
            # 代码联系建立：code_symbols 对齐真实 CodeFunction
            for sym in m.get("code_symbols") or []:
                fn = _find(g, "CodeFunction", str(sym))
                if fn:
                    g.assert_rel(mid, fn.id, "MODULE_IMPLEMENTED_BY",
                                 paper_id="paper:" + aid)
                    n_code += 1
                else:
                    out["gaps"].append({"code_symbol": str(sym),
                                        "module": mname,
                                        "reason": "not_in_code_functions"})
    out["created"]["Algorithm"] = n_alg
    out["created"]["AlgorithmModule"] = n_mod
    out["relations"]["MODULE_IMPLEMENTED_BY"] = n_code
    # E3 → Benchmark 结构
    e3 = (rep["stages"].get("E3_benchmark") or {}).get("data") or {}
    n_bm = 0
    for b in e3.get("benchmarks") or []:
        if not b.get("name"):
            continue
        bm = _find(g, "Benchmark", b["name"])
        if not bm:
            bid = "benchmark:" + _slug(b["name"])
            g.node(bid, "Benchmark", b["name"], name=b["name"])
            bm = g.nodes[bid]
            n_bm += 1
        for k in ("input_form", "output_form", "n_samples", "scale",
                  "modality", "research_object", "metrics"):
            if b.get(k):
                bm.attrs[k] = b[k]
        if paper and check_domain_range("Paper", "EVALUATED_ON", "Benchmark"):
            g.assert_rel(paper.id, bm.id, "EVALUATED_ON")
    out["created"]["Benchmark"] = n_bm
    # E4 → model_results 追加（去重）
    rows = rep.get("model_results", {}).get("rows") or []
    if rows and paper:
        bms = [a.target for a in g.outgoing(paper.id)
               if a.relation == "EVALUATED_ON" and a.target in g.nodes]
        target = g.nodes[bms[0]] if bms else None
        if target:
            cur = target.attrs.get("model_results") or []
            seen = {(str(x.get("model_name") or x.get("model")),
                     str(x.get("metric_name") or x.get("metric")),
                     str(x.get("value_raw") or x.get("value")))
                    for x in cur}
            added = 0
            for r in rows:
                key = (str(r.get("model_name") or r.get("model")),
                       str(r.get("metric_name") or r.get("metric")),
                       str(r.get("value_raw") or r.get("value")))
                if key not in seen:
                    cur.append(r); seen.add(key); added += 1
            target.attrs["model_results"] = cur
            out["updated"]["model_results_added"] = added
    # E6 → SUBCLASS_OF（只有谱系类）
    n_sub = n_alg_lineage = 0
    for x in rep.get("lineage", {}).get("subclass_of") or []:
        src = _find(g, "Algorithm", x["from"])
        if not src and x.get("from"):
            # 本文方法名来自谱系抽取（dataset_benchmark/theory 论文不跑 E2）
            aid_ = "algorithm:" + _slug(x["from"])
            g.node(aid_, "Algorithm", x["from"], name=x["from"],
                   origin="lineage", paper_id="paper:" + aid)
            src = g.nodes[aid_]
            n_alg_lineage += 1
        dst = _find(g, "Algorithm", x["to"])
        if not dst and x.get("to"):
            # 基线/被继承方法来自原文且带 evidence，补建为真实算法节点
            bid_ = "algorithm:" + _slug(x["to"])
            g.node(bid_, "Algorithm", x["to"], name=x["to"],
                   origin="lineage_baseline", paper_id="paper:" + aid)
            dst = g.nodes[bid_]
            n_alg_lineage += 1
        if not src or not dst or src.id == dst.id:
            out["gaps"].append({"lineage": x,
                                "reason": "algorithm_name_unresolvable"})
            continue
        g.assert_rel(src.id, dst.id, "SUBCLASS_OF",
                     kind=x["kind"], evidence=x.get("evidence") or "",
                     paper_id=("paper:" + aid))
        n_sub += 1
    out["relations"]["SUBCLASS_OF"] = n_sub
    out["created"]["AlgorithmFromLineage"] = n_alg_lineage
    return out


def apply_all(*, rebuild_app: bool = False) -> Dict[str, Any]:
    from ..po import POGraph
    g = POGraph.load(str(SEM))
    reps, hints = [], []
    import re as _re
    for p in sorted(EXTRACT_DIR.glob("*.json")):
        # 只处理抽取报告 <arxiv_id>.json；排除 vocab/state/_SUMMARY/hints
        if not _re.match(r"\d{4}\.\d{4,5}\.json", p.name):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict) or not d.get("arxiv_id"):
            continue
        reps.append(d)
        hints.append({"arxiv_id": d.get("arxiv_id"),
                      "hints": d.get("application_hints") or {}})
    # 幂等：语义层现在只保留真抽的谱系边，重跑时全清再建
    g.assertions = [a for a in g.assertions
                    if a.relation != "SUBCLASS_OF"]
    report = {"n_papers": len(reps), "per_paper": [], "totals": {}}
    for d in reps:
        report["per_paper"].append(apply_one(g, d))
    HINTS.write_text(json.dumps(hints, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    g.save(str(SEM))
    report["totals"] = {
        "nodes": len(g.nodes), "assertions": len(g.assertions),
        "subclass_of": sum(1 for a in g.assertions
                           if a.relation == "SUBCLASS_OF"),
        "hints": sum(len(h["hints"].get("tools_formulas") or [])
                     for h in hints)}
    # 关系索引也基于语义层图重建（关系浏览器读它）
    try:
        from ..sciforge.relation_layer import build_relations
        report["relation_index"] = build_relations(g, persist=True)
    except Exception as exc:  # noqa: BLE001
        report["relation_index"] = {"error": str(exc)[:120]}
    if rebuild_app:
        from ..applayer.miner import mine_all
        report["semantic_snapshot"] = mine_all(g, task=None, persist=True)
    return report
