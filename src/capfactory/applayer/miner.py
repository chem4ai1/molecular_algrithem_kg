"""应用层挖掘器：从语义层 v4 图确定性生成应用层节点（不调 LLM、不造事实）。"""
from __future__ import annotations
import collections, json, re
from pathlib import Path
from typing import Any, Dict, List

OUT = Path("storage_cf/sciforge/batch10_app_v1.json")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:60]


# 内置：领域证据规范与失败模式（来自 docs/question_knowledge_skills/new/02、07）
_ACCEPTED: Dict[str, List[str]] = {
    "simulational": ["validity", "uniqueness", "novelty", "diversity", "fid",
                     "convergence", "loss"],
    "experimental": ["accuracy", "f1", "precision", "recall", "auc", "p_value"],
    "causal_inference": ["ate", "ci", "robustness", "placebo"],
    "derivational": ["theorem", "proof", "bound", "complexity"],
    "correlational": ["correlation", "r2", "coefficient"],
    "interpretive": ["coherence", "coverage"],
}
_NORM: Dict[str, Dict[str, Any]] = {
    "simulational": {"sample_size": "≥3 seeds, mean±std", "control": "同条件 baseline ≥3（含 naive）",
                     "effect": "报效应量与 between-seed std", "negative": "失败案例须报告",
                     "venues": ["NeurIPS", "ICML", "ICLR"]},
    "experimental": {"sample_size": "power analysis", "control": "随机对照 + 盲法",
                     "effect": "效应量 + CI", "negative": "阴性结果须报告",
                     "venues": ["Nature", "Science", "Cell"]},
    "causal_inference": {"sample_size": "识别所需样本", "control": "识别策略 + 稳健性",
                         "effect": "ATE + CI", "negative": "placebo/预趋势",
                         "venues": ["AER", "QJE", "Econometrica"]},
    "derivational": {"sample_size": "N/A", "control": "假设台账",
                     "effect": "定理陈述", "negative": "反例搜素",
                     "venues": ["Annals", "JAMS"]},
    "correlational": {"sample_size": "样本量 + 缺失处理", "control": "混杂控制",
                      "effect": "相关系数 + CI", "negative": "幸存者偏差检查",
                      "venues": ["JF", "RFS"]},
    "interpretive": {"sample_size": "N/A", "control": "替代解释",
                     "effect": "论证强度", "negative": "反例讨论",
                     "venues": ["Critical Inquiry"]},
}
_MIN_FID: Dict[str, str] = {
    "simulational": "numerical", "experimental": "numerical",
    "causal_inference": "numerical", "derivational": "symbolic",
    "correlational": "numerical", "interpretive": "qualitative",
}
_FAILURE_MODES: Dict[str, List[Dict[str, Any]]] = {
    "simulational": [
        {"name": "convergence_failure", "severity": "fatal",
         "detection": "报收敛曲线与多起点", "tags": ["optimization", "ML"]},
        {"name": "data_leakage", "severity": "fatal",
         "detection": "检查划分脚本与重复样本", "tags": ["ML"]},
        {"name": "baseline_misconfiguration", "severity": "fatal",
         "detection": "同条件、同搜索预算", "tags": ["ML"]},
        {"name": "metric_mismatch", "severity": "fatal",
         "detection": "指标与贡献的对应关系", "tags": ["ML"]},
        {"name": "seed_cherry_picking", "severity": "fatal",
         "detection": "要求 mean±std 与全部 seed", "tags": ["ML"]},
        {"name": "toy_overreach", "severity": "high",
         "detection": "声明「在测试的 regime 内」", "tags": ["ML"]},
    ],
    "experimental": [
        {"name": "underpowered", "severity": "fatal",
         "detection": "power analysis / 最小可检测效应", "tags": ["bio", "med"]},
        {"name": "no_blinding", "severity": "high",
         "detection": "盲法状态", "tags": ["med"]},
        {"name": "post_hoc_exclusion", "severity": "high",
         "detection": "排除标准是否事前声明", "tags": ["med"]},
    ],
    "derivational": [
        {"name": "unstated_assumption", "severity": "fatal",
         "detection": "假设台账", "tags": ["math"]},
        {"name": "proof_gap", "severity": "fatal",
         "detection": "逐步机器验证", "tags": ["math"]},
    ],
    "causal_inference": [
        {"name": "omitted_variable", "severity": "fatal",
         "detection": "识别策略与稳健性", "tags": ["econ"]},
        {"name": "reverse_causality", "severity": "fatal",
         "detection": "时序与外生性检验", "tags": ["econ"]},
    ],
    "correlational": [
        {"name": "survivorship_bias", "severity": "fatal",
         "detection": "纳入失败样本", "tags": ["finance"]},
    ],
    "interpretive": [
        {"name": "selective_citation", "severity": "high",
         "detection": "替代解释是否讨论", "tags": ["humanities"]},
    ],
}


_SECTION_PLANS: Dict[str, List[Dict[str, Any]]] = {
    "simulational": [
        {"section": "Introduction", "word_budget": 900, "claims": ["problem", "why_hard", "contribution"]},
        {"section": "Method", "word_budget": 1800, "claims": ["mechanism", "module_roles"]},
        {"section": "Experimental Setup", "word_budget": 700, "claims": ["protocol", "baselines"]},
        {"section": "Results", "word_budget": 1600, "claims": ["main_result", "ablation"]},
        {"section": "Discussion", "word_budget": 700, "claims": ["limitation", "future_work"]},
    ],
    "experimental": [
        {"section": "Introduction", "word_budget": 900, "claims": ["problem", "contribution"]},
        {"section": "Methods", "word_budget": 1500, "claims": ["protocol", "power_analysis"]},
        {"section": "Results", "word_budget": 1600, "claims": ["statistical_test"]},
        {"section": "Discussion", "word_budget": 700, "claims": ["limitation"]},
    ],
    "derivational": [
        {"section": "Introduction", "word_budget": 900, "claims": ["problem", "contribution"]},
        {"section": "Main Results", "word_budget": 1800, "claims": ["theorem", "lemma"]},
        {"section": "Proofs", "word_budget": 2000, "claims": ["proof"]},
    ],
    "causal_inference": [
        {"section": "Introduction", "word_budget": 900, "claims": ["problem", "contribution"]},
        {"section": "Identification Strategy", "word_budget": 1500, "claims": ["assumption", "estimator"]},
        {"section": "Results", "word_budget": 1500, "claims": ["ate", "ci"]},
        {"section": "Robustness Checks", "word_budget": 900, "claims": ["placebo", "sensitivity"]},
    ],
    "interpretive": [
        {"section": "Introduction", "word_budget": 900, "claims": ["problem", "claim"]},
        {"section": "Argument", "word_budget": 2000, "claims": ["claim", "counterargument"]},
        {"section": "Analysis", "word_budget": 1200, "claims": ["evidence_weighting"]},
    ],
}
_REVIEW_AXES: List[Dict[str, str]] = [
    {"axis": "novelty", "attack": "这就是 A + B，A 和 B 都是现成的",
     "response": "给出 why-not-before 的三类理由", "severity": "fatal"},
    {"axis": "validity", "attack": "涨点可能在 seed 噪声范围内",
     "response": "报 mean±std 与种子数", "severity": "fatal"},
    {"axis": "comparability", "attack": "baseline 没调参 / 没复现",
     "response": "同条件、同搜索预算", "severity": "fatal"},
    {"axis": "attribution", "attack": "没做消融，不知道是哪部分起作用",
     "response": "leave-one-component-out", "severity": "high"},
    {"axis": "generalization", "attack": "只在一个数据集上验证",
     "response": "补第二个基准或声明 regime", "severity": "high"},
    {"axis": "clarity", "attack": "前两页没讲清问题与贡献",
     "response": "摘要五句 + 引言四段", "severity": "medium"},
]


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
    # ===== S2：写作方法论节点 =====
    # 9) 贡献（S1 落库才有；缺失不造）
    n9 = 0
    for p in papers:
        for i, c in enumerate(p.attrs.get("contributions") or []):
            if not isinstance(c, dict):
                continue
            cid = f"appcon:{_slug(p.attrs.get('arxiv_id') or p.id)}:{i}"
            if add(cid, "Contribution", str(c.get("statement") or "")[:80],
                   statement=c.get("statement"), kind=c.get("kind"),
                   novelty_basis=c.get("novelty_basis"),
                   section=c.get("section"),
                   claimed_strength=c.get("claimed_strength"),
                   evidence=c.get("evidence"), paper_id=p.id,
                   derived_from=[p.id], miner="contributions"):
                rel(p.id, "DECLARES", cid); n9 += 1
    rep["miners"]["contributions"] = n9
    # 10) 实验组（按 outcome_class 分组；无该字段则不建）
    n10 = 0
    for b in sem_g.by_type("Benchmark"):
        groups: Dict[str, list] = collections.defaultdict(list)
        for r in b.attrs.get("model_results") or []:
            oc = str(r.get("outcome_class") or "").strip()
            if oc in ("main", "baseline", "ablation", "hyperparam"):
                groups[oc].append(r)
        for kind, rows in groups.items():
            aid_ = f"apparm:{_slug(b.id)}:{kind}"
            seeds = [r.get("seeds") for r in rows if r.get("seeds")]
            if add(aid_, "ExperimentArm", f"{b.label} · {kind}",
                   kind=kind, name=kind, n_seeds=max(seeds) if seeds else None,
                   benchmark=b.label, config=f"{len(rows)} 行",
                   derived_from=[b.id], miner="experiment_arms"):
                rel(b.id, "ON", aid_) if False else None
                n10 += 1
    rep["miners"]["experiment_arms"] = n10
    # 11) 假设（Algorithm.assumptions 文本提升）
    n11 = 0
    for a in sem_g.by_type("Algorithm"):
        for i, st in enumerate(a.attrs.get("assumptions") or []):
            st = str(st).strip()
            if not st:
                continue
            sid = f"appasm:{_slug(a.id)}:{i}"
            if add(sid, "Assumption", st[:80], statement=st, scope="global",
                   derived_from=[a.id], miner="assumptions"):
                rel(a.id, "ASSUMES", sid); n11 += 1
    rep["miners"]["assumptions"] = n11
    # 12) 证据规范 + 失败模式（内置规则，不依赖抽取）
    n12 = 0
    for p in papers:
        et = str(p.attrs.get("evidence_type") or "").strip()
        if not et:
            continue
        nid = "appnorm:" + _slug(et)
        if add(nid, "EvidenceNorm", et, evidence_type=et,
               accepted_metrics=_ACCEPTED.get(et, []),
               min_fidelity=_MIN_FID.get(et, "qualitative"),
               sample_size_norm=_NORM.get(et, {}).get("sample_size"),
               control_design_norm=_NORM.get(et, {}).get("control"),
               effect_reporting_norm=_NORM.get(et, {}).get("effect"),
               negative_result_norm=_NORM.get(et, {}).get("negative"),
               exemplar_venues=_NORM.get(et, {}).get("venues", []),
               miner="evidence_norms"):
            rel(p.id, "CONFORMS_TO", nid)
        for k, fm in enumerate(_FAILURE_MODES.get(et, [])):
            fid = f"appfail:{_slug(et)}:{k}"
            if add(fid, "FailureMode", fm["name"], name=fm["name"],
                   severity=fm["severity"], detection=fm["detection"],
                   domain_tags=fm.get("tags", []), miner="failure_modes"):
                rel(nid, "APPLIES", fid)
                rep["miners"]["failure_modes"] = rep["miners"].get(
                    "failure_modes", 0) + 1
        n12 += 1
    rep["miners"]["evidence_norms"] = n12
    # 13) 图表资产（S1 落库才有）
    n13 = 0
    for p in papers:
        for i, f in enumerate(p.attrs.get("figures") or []):
            if not isinstance(f, dict):
                continue
            fid = f"appfig:{_slug(p.attrs.get('arxiv_id') or p.id)}:{i}"
            if add(fid, "FigureAsset", str(f.get("caption") or f.get("label"))[:80],
                   fig_label=f.get("label"), caption=f.get("caption"),
                   kind=f.get("kind"),
                   for_contribution=f.get("for_contribution"),
                   placement="body" if f.get("kind") in
                   ("main", "ablation") else "appendix",
                   derived_from=[p.id], miner="figures"):
                n13 += 1
    rep["miners"]["figures"] = n13
    # 14) 引用与空白：**不在这里建**
    # CitedPaper / ResearchGap 是任务级实例，由 applayer.context.WritingContext
    # 在本次写作真正引用时才实例化（见 md/APP_LAYER_S2.md §9）。
    rep["miners"]["cited_papers"] = 0
    rep["miners"]["gaps"] = 0
    # 15) 章节计划（按 evidence_type 的内置骨架，不依赖抽取）
    n15 = 0
    for p in papers:
        et = str(p.attrs.get("evidence_type") or "").strip()
        if not et:
            continue
        for k, sec in enumerate(_SECTION_PLANS.get(et, [])):
            sid = f"appsec:{_slug(p.attrs.get('arxiv_id') or p.id)}:{k}"
            if add(sid, "SectionPlan", sec["section"],
                   section=sec["section"], claims=sec.get("claims", []),
                   word_budget=sec.get("word_budget"),
                   derived_from=[p.id], miner="section_plans"):
                rel(p.id, "OUTLINES", sid); n15 += 1
    rep["miners"]["section_plans"] = n15
    # 16) 审稿关注点（6 维 × 每条贡献，内置模板）
    n16 = 0
    for p in papers:
        cons = [x for x in g.nodes.values()
                if x.type == "Contribution" and x.attrs.get("paper_id") == p.id]
        for c in cons:
            for k, rp in enumerate(_REVIEW_AXES):
                rid = f"apprev:{_slug(c.id)}:{k}"
                if add(rid, "ReviewPoint", f"{rp['axis']} · {rp['attack'][:24]}",
                       axis=rp["axis"], attack=rp["attack"],
                       response=rp.get("response"),
                       severity=rp.get("severity", "high"),
                       derived_from=[c.id], miner="review_points"):
                    rel(c.id, "CHALLENGED_BY", rid); n16 += 1
    rep["miners"]["review_points"] = n16
    rep["nodes"] = len(g.nodes)
    rep["assertions"] = len(g.assertions)
    rep["n_relations"] = len(g.assertions) - rep["n_semantic_assertions"]
    rep["miners"] = {k: v for k, v in rep["miners"].items()
                     if k in sp["miners"]}
    if persist:
        g.save(str(out))
        rep["path"] = str(out)
    return rep
