"""P3 关系层：三库只存属性，关系单独按「链类型」组织。

设计原则：不画节点连线图谱，改成「一个实例 + 它和其它实例的各项关系」；
论文视图：论文-论文（相关文献）、论文-算法、论文-数据；
算法视图：算法-代码、算法-数据、算法-论文；
数据视图：数据-论文（去哪篇论文查更详细解释）、数据-算法、数据-指标。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

OUT = Path("storage_cf/sciforge/relation_index.json")
DATA_SOURCE = Path("storage_cf/sciforge/data_source_relations.json")

CHAIN_SPECS: Dict[str, Dict[str, Any]] = {
    "paper": {"label": "论文视图", "root_type": "Paper", "chains": {
        "paper_paper": {"label": "论文 → 论文（相关文献 / 科技树）",
                        "color": "#ffb35c", "target_types": ["Paper", "SourcePaper"]},
        "paper_algorithm": {"label": "论文 → 算法（提出方法 / 基线）",
                            "color": "#63d9a0", "target_types": ["Algorithm"]},
        "paper_data": {"label": "论文 → 数据（评测基准 / 数据集）",
                       "color": "#f58ac0", "target_types": ["Benchmark"]},
        "paper_code": {"label": "论文 → 代码（仓库）",
                       "color": "#5fd0d8", "target_types": ["CodeRepository"]},
    }},
    "algorithm": {"label": "算法视图", "root_type": "Algorithm", "chains": {
        "algorithm_code": {"label": "算法 → 代码（实现 / 模块）",
                           "color": "#5fd0d8", "target_types": ["CodeFunction"]},
        "algorithm_data": {"label": "算法 → 数据（有评测结果的基准）",
                           "color": "#f58ac0", "target_types": ["Benchmark"]},
        "algorithm_paper": {"label": "算法 → 论文（出处）",
                            "color": "#7aa8ff", "target_types": ["Paper"]},
    }},
    "data": {"label": "数据视图", "root_type": "Benchmark", "chains": {
        "data_paper": {"label": "数据 → 论文（到哪篇论文查更详细解释）",
                       "color": "#7aa8ff", "target_types": ["Paper"]},
        "data_algorithm": {"label": "数据 → 算法（有结果的模型）",
                           "color": "#63d9a0", "target_types": ["Algorithm"]},
        "data_metric": {"label": "数据 → 指标（测试指标）",
                        "color": "#ffd166", "target_types": ["MetricDefinition"]},
    }},
}

RELATION_LABELS = {
    "RELATED_TO": "相关", "PROPOSES_METHOD": "提出方法",
    "EVALUATED_ON": "评测于", "HAS_CODE": "关联代码仓库",
    "REALIZED_BY": "代码实现", "IMPLEMENTS_MODULE": "模块实现",
    "SOURCE_PAPER": "来源论文", "HAS_RESULT": "有评测结果",
    "USES_METRIC": "使用指标", "OF_METRIC": "指标观测",
    "REPORTS": "报告观测", "HAS_DATA_CONTRACT": "数据契约",
    "CITES_RELATED": "相关文献", "USES_BASELINE": "使用基线",
}


def _pg_results() -> Dict[str, List[str]]:
    try:
        from .pgstore import connect
        c = connect()
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT benchmark_id, model_name FROM kg.result
                               WHERE value IS NOT NULL""")
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, List[str]] = {}
    for r in rows:
        lst = out.setdefault(r["benchmark_id"], [])
        if r["model_name"] not in lst:
            lst.append(r["model_name"])
    return out


def _related_paper_hints(graph: Any = None) -> List[Dict[str, str]]:
    """三类出处 CSV 的相关论文线索 + 科技树链（未匹配到库内论文也保留）。"""
    import csv
    out: List[Dict[str, str]] = []
    f = Path("storage_cf/sciforge/source_related_papers.csv")
    if f.exists():
        with f.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                host = r.get("host_arxiv_id") or ""
                name = (r.get("root_name") or r.get("cited_title") or "相关文献")
                out.append({"host": host, "name": name,
                            "target_id": r.get("resolved_paper_id") or "",
                            "relation": r.get("tree_relation") or "CITES_RELATED",
                            "ref_no": r.get("ref_no") or "",
                            "status": r.get("match_status") or ""})
    root = Path("storage_cf/sciforge/batch_multistage")
    for d in sorted(root.glob("*/STAGE2_related_work.json")):
        aid = d.parent.name
        try:
            tree = json.loads(d.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for ch in tree.get("chains") or []:
            rel = str(ch.get("style") or "")
            for m in ch.get("methods") or []:
                out.append({"host": aid, "name": str(m),
                            "relation": f"科技树·{rel}",
                            "ref_no": "", "status": "tech_tree"})
    return out


def _data_sources() -> Dict[str, List[str]]:
    if not DATA_SOURCE.exists():
        return {}
    d = json.loads(DATA_SOURCE.read_text(encoding="utf-8"))
    return {k: v.get("source_papers") or [] for k, v in d.items()}


def build_relations(graph: Any, *, persist: bool = True) -> Dict[str, Any]:
    """构建按实例 × 链类型 的关系索引。"""
    idx: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    nodes = graph.nodes

    def add(src, chain, rel, tgt, note="", evidence=""):
        t = nodes.get(tgt)
        idx.setdefault(src, {}).setdefault(chain, []).append({
            "relation": rel,
            "relation_label": RELATION_LABELS.get(rel, rel),
            "target_id": tgt,
            "target_label": (t.label if t else tgt),
            "target_type": (t.type if t else "外部"),
            "note": note, "evidence": evidence})

    for a in graph.assertions:
        s, t = a.source, a.target
        if s not in nodes or t not in nodes:
            continue
        st, tt = nodes[s].type, nodes[t].type
        if st == "Paper" and tt == "Paper":
            add(s, "paper_paper", a.relation, t)
        elif st == "Paper" and tt == "Algorithm":
            add(s, "paper_algorithm", a.relation, t)
            add(t, "algorithm_paper", a.relation, s)
        elif st == "Paper" and tt == "Benchmark":
            add(s, "paper_data", a.relation, t)
            add(t, "data_paper", a.relation, s,
                "该基准的详细说明见此论文")
        elif st == "Paper" and tt == "CodeRepository":
            add(s, "paper_code", a.relation, t)
        elif st in ("Algorithm", "AlgorithmStep") and tt in (
                "CodeFunction", "CodeRepository", "AlgorithmStep"):
            add(s, "algorithm_code", a.relation, t)
        elif st == "Benchmark" and tt in ("MetricDefinition", "Observation"):
            add(s, "data_metric", a.relation, t)
        elif st == "Algorithm" and tt == "Paper":
            add(s, "algorithm_paper", a.relation, t)
    # HAS_CODE 是论文→仓库，按「论文提出的方法」派生 算法→代码
    for a in graph.assertions:
        if a.relation != "HAS_CODE":
            continue
        for a2 in graph.assertions:
            if a2.source == a.source and a2.relation == "PROPOSES_METHOD":
                add(a2.target, "algorithm_code", "HAS_CODE", a.target,
                    "本论文提出的算法对应的代码仓库")
    # 数据→论文（来源解释）与 算法↔数据（评测结果）
    srcs, res = _data_sources(), _pg_results()
    for bid, papers in srcs.items():
        for pid in papers:
            add(bid, "data_paper", "SOURCE_PAPER", pid,
                "到该论文查找该数据集的更详细解释")
    alg_by_name = {n.label.lower(): n.id for n in graph.by_type("Algorithm")}
    for bid, models in res.items():
        for m in models:
            aid = alg_by_name.get(m.lower())
            if aid:
                add(aid, "algorithm_data", "HAS_RESULT", bid,
                    "该模型在此基准上有评测结果")
                add(bid, "data_algorithm", "HAS_RESULT", aid,
                    "该基准上此模型有结果")
            else:
                add(bid, "data_algorithm", "HAS_RESULT", m,
                    "模型来自论文表格抽取，图中暂无算法节点")
    # 论文-论文：相关文献线索（含未匹配到库内论文的外部条目）
    for h in _related_paper_hints(graph):
        pid = f"paper:{h['host']}"
        tgt = h.get("target_id") or h["name"]
        resolved = bool(h.get("target_id"))
        add(pid, "paper_paper", h["relation"], tgt,
            note=("已解析为库内/代理论文节点，可跳转" if resolved
                  else f"相关文献线索 [ {h['ref_no']} ]，未匹配到库内论文"))
    if persist:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(idx, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return {"n_instances": len(idx),
            "n_relations": sum(len(v) for d in idx.values()
                               for v in d.values()),
            "path": str(OUT)}


def _summary(n: Any) -> str:
    a = n.attrs
    if n.type == "Paper":
        return str(a.get("research_problem") or "")[:90]
    if n.type == "Algorithm":
        return str((a.get("problems_solved") or [""])[0])[:90]
    if n.type == "Benchmark":
        return f"{a.get('input_form','')} → {a.get('output_form','')}"
    return ""


def instances(graph: Any, view: str, q: str = "", limit: int = 200
              ) -> Dict[str, Any]:
    spec = CHAIN_SPECS.get(view) or CHAIN_SPECS["paper"]
    out = []
    for n in graph.by_type(spec["root_type"]):
        if view == "data" and "canonical:" in n.id:
            continue
        if q and q.lower() not in (n.label + n.id).lower():
            continue
        out.append({"id": n.id, "label": n.label[:90], "type": n.type,
                    "summary": _summary(n)})
    return {"view": view, "label": spec["label"],
            "count": len(out), "instances": out[:limit]}


def relations_for(node_id: str, view: str = "") -> Dict[str, Any]:
    if not OUT.exists():
        return {"id": node_id, "chains": [], "n_relations": 0}
    idx = json.loads(OUT.read_text(encoding="utf-8"))
    d = idx.get(node_id) or {}
    spec = CHAIN_SPECS.get(view) or CHAIN_SPECS["paper"]
    chains = []
    for cid, cspec in spec["chains"].items():
        items, seen, uniq = d.get(cid) or [], set(), []
        for x in items:
            k = (x["relation"], x["target_id"])
            if k not in seen:
                seen.add(k)
                uniq.append(x)
        chains.append({"id": cid, "label": cspec["label"],
                       "color": cspec["color"], "count": len(uniq),
                       "items": uniq[:60],
                       "empty_hint": "暂无此类关系（可从论文抽取补入）"
                       if not uniq else ""})
    return {"id": node_id, "view": view, "chains": chains,
            "n_relations": sum(c["count"] for c in chains)}
