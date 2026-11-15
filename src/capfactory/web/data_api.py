"""P1 数据工作台：三库本体树 + 节点卡片。

  paper     : 领域码 D → 论文 → 问题 / 方法 / 基准 / 代码
  algorithm : 算法族码 A → 算法 → 步骤 → 公式/工具/代码函数
  dataset   : 基准 → 指标 / 观测值 / 数据契约
"""
from __future__ import annotations
import collections
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .extraction_api import GRAPH_PATH

_CACHE: Dict[str, Any] = {}


def _graph() -> Any:
    from .graph_source import path_of, load as _load_source
    src = path_of("application")
    stamp = src.stat().st_mtime_ns if src.exists() else 0
    # 图重建后缓存按 mtime 自动失效，不必重启服务
    if "g" not in _CACHE or _CACHE.get("stamp") != stamp:
        _CACHE["g"] = _load_source("application")
        _CACHE["stamp"] = stamp
    return _CACHE["g"]


def _out(g: Any, nid: str) -> List[Any]:
    return list(g.outgoing(nid))


def _papers_of(g: Any, aid: str) -> List[str]:
    return [n.id for n in g.by_type("Paper")
            if aid in n.id or aid in str(n.attrs.get("arxiv_id", ""))]


def _by_paper(g: Any, aid: str, rels: tuple, typ: Optional[str] = None
              ) -> List[str]:
    out: List[str] = []
    for pid in _papers_of(g, aid):
        for a in _out(g, pid):
            if a.relation in rels and a.target in g.nodes and \
                    (typ is None or g.nodes[a.target].type == typ):
                out.append(a.target)
    return sorted(set(out))


def _leaf(g: Any, nid: str) -> Dict[str, Any]:
    n = g.nodes[nid]
    return {"id": nid, "label": n.label[:52], "type": n.type}


def _paper_meta_map() -> Dict[str, Dict[str, str]]:
    import csv as _csv
    from .extraction_api import PAPERS_CSV, MD_DIR
    out: Dict[str, Dict[str, str]] = {}
    if not PAPERS_CSV.exists():
        return out
    with open(PAPERS_CSV, encoding="utf-8-sig") as fh:
        for r in _csv.DictReader(fh):
            aid = (r.get("arxiv_id") or "").strip()
            if aid:
                out[aid] = {"title": r.get("title") or "",
                            "abstract": r.get("abstract") or "",
                            "year": r.get("year") or "",
                            "venue": r.get("venue") or ""}
    return out


def _facet_of(p: Any, facet: str, meta: Dict[str, Dict[str, str]]
              ) -> List[Dict[str, str]]:
    """返回该论文在指定 facet 下的分组键（可能多个，如多个算法族）。"""
    from ..sciforge.taxonomy import classify, domain_label, family_label
    aid = str(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
    m = meta.get(aid, {})
    if facet == "domain":
        return [{"id": str(c), "label": domain_label(str(c))}
                for c in (p.attrs.get("domain_codes") or ["未分类"])]
    if facet == "algorithm":
        return [{"id": str(c), "label": family_label(str(c))}
                for c in (p.attrs.get("algo_codes") or ["未分类"])]
    tx = classify(m.get("title") or p.label, m.get("abstract", ""),
                  domain_code=str((p.attrs.get("domain_codes") or [""])[0]),
                  paper_type=str(p.attrs.get("paper_type") or ""))
    key = {"object": ("object_kind", "object_label"),
           "task": ("task_kind", "task_label"),
           "modality": ("modality", "modality_label")}[facet]
    return [{"id": tx[key[0]], "label": tx[key[1]]}]


def tree(library: str = "paper", facet: str = "domain") -> Dict[str, Any]:
    g = _graph()
    if library == "paper":
        PAPER_FACETS = {"domain": "所属领域",
                        "problem_type": "研究问题",
                        "algorithm_family": "算法族"}
        groups: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        FACET_FIELD = {"domain": "domain",
                       "problem_type": "problem_type",
                       "algorithm_family": "algorithm_family"}
        if facet not in FACET_FIELD:
            facet = "domain"
        for p in g.by_type("Paper"):
            aid = str(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
            key = str(p.attrs.get(FACET_FIELD[facet]) or "未分类")
            if key in ("unknown", "Unknown", "UNKNOWN", ""):
                key = "待补全（关系线索）"
            if facet == "problem_type":
                from ..sciforge.algorithm_problem import TASK_TYPES
                key = TASK_TYPES.get(key, key)
            node = {"id": p.id, "label": p.label, "type": "Paper",
                    "meta": {"research_problem": (
                                 p.attrs.get("research_problem")
                                 or p.attrs.get("research_question")),
                             "domain": p.attrs.get("domain"),
                             "algorithm_family": (
                                 p.attrs.get("algorithm_family")
                                 or p.attrs.get("flow_family"))}}
            # 应用层 ResearchQuestion 只在复现/生成任务层构建；
            # 语义层论文树不混入应用节点，也避免 O(N^2) 扫描。
            kids = []
            for rel, label in (("PROPOSES_METHOD", "方法"),
                               ("EVALUATED_ON", "基准"), ("HAS_CODE", "代码")):
                leaves = [_leaf(g, a.target)
                          for a in g.outgoing(p.id, rel)
                          if a.target in g.nodes]
                if "canonical:" in str(leaves):
                    pass
                kids.append({"id": f"{rel[:2]}:{p.id}", "label":
                             f"{label}（{len(leaves)}）", "type": "group",
                             "children": leaves})
            node["children"] = kids
            groups[key].append(node)
        return {"library": library, "facet": facet,
                "facet_labels": PAPER_FACETS, "groups": [
                    {"id": k, "label": k, "count": len(v),
                     "type": "group", "children": v}
                    for k, v in sorted(groups.items(),
                        key=lambda x: (x[0].startswith("待补全"), x[0]))]}

    if library == "algorithm":
        from ..sciforge.facets_v7 import classify_algorithm, ALGO_FACET_LABELS
        groups: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        default_facet = "family"
        for a in g.by_type("Algorithm"):
            f = classify_algorithm(g, a.id)
            key = f.get(facet, f.get(default_facet)) if facet in ALGO_FACET_LABELS \
                else f.get(default_facet)
            key = key or "未分类"
            steps = []
            for pid in [x.source for x in g.incoming(a.id)
                        if x.relation == "PROPOSES_METHOD"]:
                for e in _out(g, pid):
                    if e.target in g.nodes and \
                            g.nodes[e.target].type == "AlgorithmStep":
                        kids = [_leaf(g, x.target) for x in _out(g, e.target)
                                if x.relation in ("HAS_FORMULA", "USES_TOOL",
                                                  "REALIZED_BY")]
                        steps.append({"id": e.target,
                                      "label": g.nodes[e.target].label[:52],
                                      "type": "AlgorithmStep",
                                      "children": kids})
            code = [_leaf(g, e.target) for e in _out(g, a.id)
                    if e.relation in ("REALIZED_BY", "HAS_MODULE_IMPL",
                                      "IMPLEMENTS_MODULE")
                    and e.target in g.nodes]
            groups[key].append({
                "id": a.id, "label": a.label, "type": "Algorithm",
                "meta": f,
                "children": [
                    {"id": f"s:{a.id}", "label": f"步骤（{len(steps)}）",
                     "type": "group", "children": steps},
                    {"id": f"k:{a.id}", "label": f"代码（{len(code)}）",
                     "type": "group", "children": code}]})
        return {"library": library, "facet": facet, "groups": [
            {"id": k, "label": k, "count": len(v), "type": "group",
             "children": v}
            for k, v in sorted(groups.items(),
                        key=lambda x: (x[0].startswith("待补全"), x[0]))]}

    from ..sciforge.facets_v7 import classify_benchmark, DATA_FACET_LABELS
    try:
        from ..sciforge.pgstore import overview as _ov
        with_result = {b["id"] for b in _ov()["benchmarks"]}
    except Exception:  # noqa: BLE001
        with_result = set()
    groups2: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for b in g.by_type("Benchmark"):
        if "canonical:" in b.id:
            continue                       # 规范化副本不再重复显示
        f = classify_benchmark(g, b.id, has_result=b.id in with_result)
        key = f.get(facet) if facet in DATA_FACET_LABELS else f.get("task")
        key = key or "未分类"
        metrics = [_leaf(g, a.target) for a in _out(g, b.id)
                   if a.relation in ("USES_METRIC", "OF_METRIC")
                   and a.target in g.nodes]
        # 观测值直接从 PG result 取，不再依赖图上不存在的 REPORTS_VALUE 边
        obs: List[Dict[str, Any]] = []
        if b.id in with_result:
            try:
                from ..sciforge.pgstore import leaderboard as _lb
                lb = _lb(b.id)
                for m in lb["models"][:12]:
                    cells = ", ".join(
                        f"{k}={v['value']}" for k, v in
                        list(m["cells"].items())[:3])
                    obs.append({"id": f"result:{b.id}:{m['name']}",
                                "label": f"{m['name']} · {cells}"[:72],
                                "type": "Result"})
            except Exception:  # noqa: BLE001
                pass
        contracts = [_leaf(g, a.target) for a in _out(g, b.id)
                     if a.relation in ("HAS_DATA_CONTRACT", "HAS_INPUT_FORM",
                                       "HAS_INPUT_OBJECT")
                     and a.target in g.nodes]
        groups2[key].append({
            "id": b.id, "label": b.label, "type": "Benchmark", "meta": f,
            "children": [
                {"id": f"m:{b.id}", "label": f"指标（{len(metrics)}）",
                 "type": "group", "children": metrics},
                {"id": f"o:{b.id}", "label": f"榜单值（{len(obs)} 模型）",
                 "type": "group", "children": obs},
                {"id": f"d:{b.id}", "label": f"数据契约（{len(contracts)}）",
                 "type": "group", "children": contracts}]})
    return {"library": library, "facet": facet, "groups": [
        {"id": k, "label": k, "count": len(v), "type": "group",
         "children": v}
        for k, v in sorted(groups2.items())]}


METRIC_NAMES = {"mae":"MAE","rmse":"RMSE","rmsd":"RMSD","r2":"R²",
    "pearson_r":"Pearson r","spearman":"Spearman ρ","qed":"QED",
    "amp_hit_percent":"AMP 命中率","validity":"Validity","uniqueness":"Uniqueness",
    "novelty":"Novelty","diversity":"Diversity","precision":"Precision",
    "recall":"Recall","frag_ratio":"Frag. ratio","percentage":"Percentage"}
STAGE_CN={"test":"测试集","simulation":"模拟","in_silico":"计算",
          "ablation":"消融","train":"训练"}


def _fmt_metric(m):
    k=str(m or "").strip()
    return METRIC_NAMES.get(k.lower(), k.upper() if len(k)<=4 else k)


def _fmt_unit(u):
    u=str(u or "").strip()
    return "%" if u.lower() in ("percent","%") else u


def _fmt_value(v):
    try:
        f=float(str(v)); return str(int(f)) if f==int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


def _obs_groups(g, obs_ids):
    seen, merged = {}, 0
    for oid in obs_ids:
        o=g.nodes.get(oid)
        if not o or o.attrs.get("value") is None: continue
        a=o.attrs
        key=(str(a.get("metric") or "").lower(), _fmt_unit(a.get("unit")),
             _fmt_value(a.get("value")))
        if key not in seen:
            seen[key]={"metric":a.get("metric"),"unit":_fmt_unit(a.get("unit")),
                       "value":_fmt_value(a.get("value")),
                       "subject":a.get("subject") or "","stage":a.get("stage") or "",
                       "benchmark":a.get("benchmark") or "","ids":[oid]}
        else:
            merged+=1
            r=seen[key]
            if not r["subject"] and a.get("subject"): r["subject"]=a["subject"]
            if not r["stage"] and a.get("stage"): r["stage"]=a["stage"]
            r["ids"].append(oid)
    groups={}
    for r in seen.values():
        k=(r["metric"],r["unit"],r["subject"],r["stage"],r["benchmark"])
        grp=groups.setdefault(k,{"metric":r["metric"],"unit":r["unit"],
            "subject":r["subject"],"stage":r["stage"],"benchmark":r["benchmark"],
            "values":[],"ids":[]})
        grp["values"].append(r["value"]); grp["ids"]+=r["ids"]
    import collections as _c
    subj=_c.defaultdict(set); stage=_c.defaultdict(set)
    out=[]
    for grp in groups.values():
        nums=[]
        for v in grp["values"]:
            try: nums.append(float(v))
            except ValueError: pass
        x={**grp,"n":len(grp["values"]),"min":min(nums) if nums else None,
           "max":max(nums) if nums else None,
           "label":_fmt_metric(grp["metric"])}
        if x["subject"]: subj[(x["metric"],x["unit"])].add(x["subject"])
        if x["stage"]: stage[(x["metric"],x["unit"])].add(x["stage"])
        out.append(x)
    for x in out:
        k=(x["metric"],x["unit"])
        if not x["subject"] and len(subj.get(k,()))==1:
            x["subject"]=next(iter(subj[k])); x["subject_inferred"]=True
        if not x["stage"] and len(stage.get(k,()))==1:
            x["stage"]=next(iter(stage[k])); x["stage_inferred"]=True
    out.sort(key=lambda x:(-x["n"],x["label"]))
    notes=[]
    if merged: notes.append(f"合并了 {merged} 条重复观测（同一数值被抽两遍）")
    if any(x["n"]>1 for x in out):
        notes.append("同一指标下多组值来自论文里不同测试体系，原文未给体系名")
    return {"groups":out,"n_groups":len(out),"merged":merged,"notes":notes}


def _viz(g, node):
    t, nid = node.type, node.id
    if t in ("MetricObservation","Observation"):
        val=node.attrs.get("value")
        try: num=float(str(val).rstrip("%"))
        except (TypeError,ValueError): num=None
        return {"kind":"scalar","value":val,"unit":node.attrs.get("unit"),
                "metric":node.attrs.get("metric"),"num":num}
    if t=="Paper":
        # 语义层已删 Observation/REPORTS；Paper 卡片改为「三核心 + 关系链」
        a=node.attrs
        core={
            "research_question": (a.get("research_problem")
                                  or a.get("research_question")),
            "domain": a.get("domain"),
            "problem_category": a.get("problem_type")
                                or a.get("problem_category"),
            "flow_family": a.get("algorithm_family") or a.get("flow_family"),
            "why_hard": a.get("why_hard"),
            "keywords": a.get("keywords") or []}
        core={k:v for k,v in core.items()
              if v and str(v).lower() not in ("unknown","none")}
        chains=[]
        for rel,label in (("PROPOSES_METHOD","方法"),
                          ("EVALUATED_ON","基准"), ("HAS_CODE","代码"),
                          ("RELATED_TO","相关")):
            items=[g.nodes[x.target].label[:40] for x in _out(g,nid)
                   if x.relation==rel and x.target in g.nodes]
            if items:
                chains.append({"label":label,"count":len(items),
                               "items":list(dict.fromkeys(items))[:6]})
        return ({"kind":"paper_core","core":core,"chains":chains}
                if core or chains else {"kind":"none"})
    if t=="Algorithm":
        steps=[g.nodes[a.target].label[:46] for a in _out(g,nid)
               if a.target in g.nodes and
               g.nodes[a.target].type=="AlgorithmStep"]
        if not steps:
            for pid in [a.source for a in g.incoming(nid)
                        if a.relation=="PROPOSES_METHOD"]:
                for a in _out(g,pid):
                    if a.target in g.nodes and \
                            g.nodes[a.target].type=="AlgorithmStep":
                        steps.append(g.nodes[a.target].label[:46])
        return {"kind":"pipeline" if steps else "none","steps":steps[:12]}
    if t=="Benchmark":
        ids=[a.target for a in _out(g,nid)
             if a.relation in ("REPORTS","REPORTS_VALUE")]
        for pid in [a.source for a in g.incoming(nid)
                    if a.relation=="EVALUATED_ON"]:
            ids+=[a.target for a in _out(g,pid) if a.relation=="REPORTS"]
        grp=_obs_groups(g,sorted(set(ids)))
        if grp["groups"]:
            return {"kind":"metrics","n_observations":len(set(ids)),
                    "scope":"基准上各方法的评测值",**grp}
        mets=[g.nodes[a.target].label[:30] for a in _out(g,nid)
              if a.relation in ("USES_METRIC","OF_METRIC") and a.target in g.nodes]
        return {"kind":"chips" if mets else "none","items":sorted(set(mets))[:12]}
    return {"kind":"none"}


def node_card(node_id: str) -> Dict[str, Any]:
    g=_graph(); n=g.nodes.get(node_id)
    if not n: raise HTTPException(404, f"节点不存在：{node_id}")
    ins=[{"rel":a.relation,"id":a.source,
          "label":g.nodes[a.source].label[:40] if a.source in g.nodes else "",
          "type":g.nodes[a.source].type if a.source in g.nodes else ""}
         for a in g.incoming(node_id)]
    outs=[{"rel":a.relation,"id":a.target,
           "label":g.nodes[a.target].label[:40] if a.target in g.nodes else "",
           "type":g.nodes[a.target].type if a.target in g.nodes else ""}
          for a in g.outgoing(node_id)]
    return {"id":n.id,"type":n.type,"label":n.label,"attrs":dict(n.attrs),
            "in":ins[:60],"out":outs[:60],"viz":_viz(g,n),
            "graph_link":"/relations"}


def _page_v7(name: str):
    from fastapi.responses import HTMLResponse
    from .extraction_api import STATIC_DIR
    p = STATIC_DIR / name
    if not p.exists():
        raise HTTPException(500, f"页面缺失：{name}")
    return HTMLResponse(p.read_text(encoding="utf-8"))


def data_page_v7():
    return _page_v7("data.html")


_V7_ROUTES = [
    ("/api/v6/data/tree", tree, "GET", True),
    ("/api/v6/data/node/{node_id}", node_card, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V7_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
