"""应用层挖掘器：从语义层 v4 图确定性生成应用层节点（不调 LLM、不造事实）。"""
from __future__ import annotations
import collections, json, re
from pathlib import Path
from typing import Any, Dict, List

OUT = Path("storage_cf/sciforge/batch10_app_v1.json")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:60]


def mine_all(sem_g: Any, *, task: str | None = None,
             out: Path | None = None, persist: bool = True
             ) -> Dict[str, Any]:
    """task=None → 纯语义层快照（页面默认图，零应用节点）；
    task="reproduction"/"generation" → 只构建该任务 spec 内的应用节点与关系。
    """
    from ..po import POGraph
    from .tasks import spec, out_path
    sp = spec(task) if task else None
    allowed_c = set(sp["classes"]) if sp else set()
    allowed_r = set(sp["relations"]) if sp else set()
    out = out or out_path(task)
    g = POGraph("app_v1")
    rep: Dict[str, Any] = {"by_type": {}, "n_relations": 0, "miners": {},
                           "n_semantic_nodes": 0, "task": task}
    # 底层：复制语义层节点（标 layer=semantic）**与其断言**，应用层叠加其上
    for n in sem_g.nodes.values():
        a = {k: v for k, v in n.attrs.items() if k != "label"}
        g.node(n.id, n.type, n.label, layer="semantic", **a)
        rep["n_semantic_nodes"] += 1
    for a in sem_g.assertions:
        g.assert_rel(a.source, a.target, a.relation,
                     layer="semantic", **(dict(a.properties or {})))
    rep["n_semantic_assertions"] = len(sem_g.assertions)

    # 抽取/回填期（task=None）：只输出语义层快照，应用节点一个都不建，
    # 连挖掘器都不跑 —— 避免「抽取过程中混入应用层」的暧昧。
    if sp is None:
        rep.update({"nodes": len(g.nodes), "assertions": len(g.assertions)})
        if persist:
            g.save(str(out)); rep["path"] = str(out)
        return rep

    def add(nid, typ, label, **attrs):
        if typ not in allowed_c or nid in g.nodes:
            return False
        g.node(nid, typ, label, layer="application", task=task, **attrs)
        rep["by_type"][typ] = rep["by_type"].get(typ, 0) + 1
        return True

    def rel(s, r, t, **props):
        if r not in allowed_r or s not in g.nodes or t not in g.nodes:
            return
        g.assert_rel(s, t, r, layer="application", task=task, **props)
        rep["n_relations"] += 1

    papers = sem_g.by_type("Paper")
    # 1) 研究问题
    n1 = 0
    for p in papers:
        q = str(p.attrs.get("research_question") or "").strip()
        if not q or q.startswith("unknown"):
            continue
        qid = "appq:" + _slug(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
        add(qid, "ResearchQuestion", q[:100], question=q,
            paper_id=p.id, problem_category=p.attrs.get("problem_category"),
            derived_from=[p.id], miner="questions")
        rel(p.id, "FORMULATES", qid); n1 += 1
    rep["miners"]["questions"] = n1
    # 2) 问题类别（聚类）
    cats = collections.Counter()
    for p in papers:
        c = str(p.attrs.get("problem_category") or "").strip()
        if c and not c.startswith("unknown"):
            cats[c] += 1
    for c, n in cats.items():
        cid = "appcat:" + _slug(c)
        add(cid, "ProblemCategory", c, code=_slug(c)[:12],
            n_papers=n, derived_from=[], miner="categories")
    for p in papers:
        c = str(p.attrs.get("problem_category") or "").strip()
        if not c or c.startswith("unknown"):
            continue
        qid = "appq:" + _slug(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
        rel(qid, "IN_CATEGORY", "appcat:" + _slug(c))
    rep["miners"]["categories"] = len(cats)
    # 3) 指标定义（去重归一）
    metrics: Dict[str, Dict[str, Any]] = {}
    for b in sem_g.by_type("Benchmark"):
        for m in (b.attrs.get("metrics") or []):
            name = str(m.get("name") or "").strip()
            if not name:
                continue
            d = metrics.setdefault(name, {"direction": m.get("direction"),
                                          "unit": m.get("unit"),
                                          "n": 0, "sota": "",
                                          "from": []})
            d["n"] += 1
            if b.id not in d["from"]:
                d["from"].append(b.id)
            if m.get("sota_model"):
                d["sota"] = m["sota_model"]
    for name, d in metrics.items():
        mid = "appmetric:" + _slug(name)
        add(mid, "MetricDefinition", name, name=name,
            direction=d["direction"], unit=d["unit"],
            n_benchmarks=d["n"], sota_model=d["sota"],
            derived_from=d["from"][:20], miner="metrics")
    rep["miners"]["metrics"] = len(metrics)
    # 4) 榜单行 + 数据契约 + 指标关系
    n4 = n5 = 0
    for b in sem_g.by_type("Benchmark"):
        bis = b.id
        for i, e in enumerate(b.attrs.get("model_results") or []):
            model = str(e.get("model") or "").strip()
            metric = str(e.get("metric") or "").strip()
            if not model or not metric:
                continue
            eid = f"applb:{_slug(bis)}:{i}"
            add(eid, "LeaderboardEntry", f"{model} · {metric}",
                benchmark=b.label, model=model, metric=metric,
                value=str(e.get("value")), unit=e.get("unit") or "",
                is_sota=bool(e.get("is_sota")), paper_id=e.get("paper_id"),
                derived_from=[bis], miner="leaderboard")
            rel(bis, "HAS_ENTRY", eid)
            mid = "appmetric:" + _slug(metric)
            if mid in g.nodes:
                rel(eid, "USES_METRIC", mid)
            n4 += 1
        # 数据契约
        if b.attrs.get("input_form") or b.attrs.get("output_form"):
            cid = "appcontract:" + _slug(bis)
            add(cid, "DataContract", "契约 · " + b.label,
                benchmark=b.label,
                input_form=b.attrs.get("input_form"),
                output_form=b.attrs.get("output_form"),
                n_samples=b.attrs.get("n_samples"),
                scale=b.attrs.get("scale"),
                modality=b.attrs.get("modality"),
                derived_from=[bis], miner="contracts")
            rel(bis, "HAS_CONTRACT", cid); n5 += 1
    rep["miners"]["leaderboard"] = n4
    rep["miners"]["contracts"] = n5
    # 5) 指标 ↔ 基准
    for b in sem_g.by_type("Benchmark"):
        for m in (b.attrs.get("metrics") or []):
            mid = "appmetric:" + _slug(str(m.get("name") or ""))
            if mid in g.nodes:
                rel(b.id, "HAS_METRIC", mid)
    # 6) 证据（表格单元格溯源：数值 + 出处）
    n6 = 0
    for b in sem_g.by_type("Benchmark"):
        for i, e in enumerate(b.attrs.get("model_results") or []):
            val = str(e.get("value") or "")
            mt = str(e.get("metric") or "")
            model = str(e.get("model") or "")
            if not val or not mt:
                continue
            qid = f"appev:{_slug(b.id)}:{i}"
            add(qid, "Evidence", f"{model} {mt}={val}",
                quote=f"{model} {mt}={val}", kind="table_cell",
                paper_id=e.get("paper_id"),
                source=e.get("source") or e.get("provenance") or "",
                derived_from=[b.id], miner="evidence")
            rel(qid, "SUPPORTED_BY", qid) if False else None
            # 反向：榜单行 → 证据（同 benchmark 同序）
            eid = f"applb:{_slug(b.id)}:{i}"
            if eid in g.nodes:
                rel(eid, "SUPPORTED_BY", qid)
            n6 += 1
    rep["miners"]["evidence"] = n6
    # 7) 局限
    n7 = 0
    for a in sem_g.by_type("Algorithm"):
        lims = a.attrs.get("limitations") or []
        if isinstance(lims, str):
            lims = [lims] if lims.strip() else []
        for i, s in enumerate(lims):
            s = str(s).strip()
            if not s or s == "unknown":
                continue
            lid = f"applim:{_slug(a.id)}:{i}"
            add(lid, "Limitation", s[:90], statement=s,
                algorithm=a.label, kind="stated",
                derived_from=[a.id], miner="limitations")
            rel(a.id, "HAS_LIMITATION", lid); n7 += 1
    rep["miners"]["limitations"] = n7
    # 8) 出处论文（论文-论文链）
    n8 = 0
    for a in sem_g.assertions:
        if a.relation != "RELATED_TO":
            continue
        s = sem_g.nodes.get(a.source)
        t = sem_g.nodes.get(a.target)
        if not s or not t or s.type != "Paper" or t.type != "Paper":
            continue
        sid = "appsrc:" + _slug(f"{a.source}:{a.target}")
        add(sid, "SourcePaper", t.label[:90],
            title=t.label, ref_paper=t.id, relation="RELATED_TO",
            resolved=t.attrs.get("resolved_kind") or "library",
            derived_from=[a.source, a.target], miner="source_papers")
        rel(a.source, "SITUATED_IN", sid); n8 += 1
    rep["miners"]["source_papers"] = n8
    rep["nodes"] = len(g.nodes)
    rep["assertions"] = len(g.assertions)
    rep["n_relations"] = len(g.assertions) - rep["n_semantic_assertions"]
    rep["miners"] = {k: v for k, v in rep["miners"].items()
                     if k in sp["miners"]}
    if persist:
        g.save(str(out))
        rep["path"] = str(out)
    return rep
