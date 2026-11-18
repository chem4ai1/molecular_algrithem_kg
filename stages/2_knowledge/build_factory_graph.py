#!/usr/bin/env python3
"""从 52 篇抽取结果构建：语义层图 → B 类图谱 → C 类决策链 → 使用案例。"""
from __future__ import annotations
import json, sys, time
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.context import WritingContext
from capfactory.applayer.graph_query import (
    query_evaluation_norm, query_frontier_baseline,
    query_failure_checks, query_venue_profile)

GRAPH = ROOT / "storage/sciforge/semantic_factory_52.json"
OUT = ROOT / "storage/sciforge/factory_knowledge.json"
TRACE = ROOT / "storage/sciforge/factory_decision_trace.json"


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    ctx = WritingContext(g, "factory_52_run")
    trace = {"stages": [], "queries": []}

    def log(stage, knowledge, form, inp, outp, note="", skill="", verdict="PASS"):
        trace["stages"].append({"stage": stage, "knowledge": knowledge, "form": form,
                                "input": inp, "output": outp, "note": note,
                                "skill": skill or stage, "verdict": verdict})

    # ===== B 类图谱：从 52 篇聚合 =====
    groups = defaultdict(list)
    for a in g.by_type("Algorithm"):
        groups[a.attrs.get("task_type") or "unknown"].append(a.id)
    n_lineage = 0
    for tt, mids in groups.items():
        if not tt or tt == "unknown":
            continue
        nid = f"lineage:factory:{tt}"
        g.node(nid, "MethodLineage", f"族谱:{tt}", task_type=tt,
               methods=mids[:20], n=len(mids), source="aggregate_from_52")
        for mid in mids[:20]:
            if mid in g.nodes:
                g.assert_rel(nid, mid, "LINEAGE_OF")
        n_lineage += 1

    by_et = defaultdict(list)
    for p in papers:
        et = p.attrs.get("evidence_type")
        if et:
            by_et[et].append(p)
    n_norm = 0
    for et, ps in by_et.items():
        accepted = list({m for p in ps for m in (p.attrs.get("evidence_norm") or [])})
        nid = f"norm:factory:{et}"
        g.node(nid, "EvaluationNorm", et, evidence_type=et,
               accepted_metrics=accepted[:12], n_papers=len(ps),
               min_fidelity="numerical" if et in ("experimental", "simulational") else "qualitative")
        for p in ps:
            g.assert_rel(nid, p.id, "DERIVED_FROM_PAPERS")
        n_norm += 1

    negs = [x for p in papers for x in (p.attrs.get("negative_results") or [])]
    lims = [x for a in g.by_type("Algorithm") for x in (a.attrs.get("limitations") or [])]
    g.node("failurelib:factory", "FailureModeLibrary", "失败模式库(52篇聚合)",
           negative_results=negs[:40], limitations=lims[:40],
           n_negative=len(negs), n_limitations=len(lims),
           source_papers=[p.id for p in papers])
    for p in papers:
        if p.attrs.get("negative_results"):
            g.assert_rel("failurelib:factory", p.id, "FAILURE_SEEN_IN")

    venues = Counter(p.attrs.get("venue") for p in papers if p.attrs.get("venue"))
    if venues:
        for v, n in venues.most_common(5):
            g.node(f"venue:factory:{v}", "VenueProfile", v, venue=v,
                   n_papers=n, citation_style="unknown", section_pattern=[])
    else:
        g.node("venue:factory:unknown", "VenueProfile", "venue未知",
               venue="unknown", note="52篇PDF均未抽venue；需外部元数据")

    log("B类聚合", "方法族谱/规范/失败模式/venue", "跨论文图谱节点+边",
        f"{len(papers)} Paper + {len(g.by_type('Algorithm'))} Algorithm",
        f"MethodLineage {n_lineage} + Norm {n_norm} + FailureLib 1",
        "离线聚合一次建，边回指来源论文", skill="graph-aggregator")

    # ===== C 类决策链 =====
    seed = papers[0]
    a = ctx.freeze_problem(question=str(seed.attrs.get("research_question") or "")[:120],
                           seed_ids=[seed.id])
    g.nodes[a].attrs.update({"answerability_criteria": ["报告主指标提升", "对比≥2 baseline"],
                             "boundary": ["不回答通用LLM能力"], "feasibility": {"data": "yes"}})
    log("①问题锚定", "领域常识+分类", "ProblemAnchor节点", seed.id, a, "Q-ID冻结")

    fr = query_frontier_baseline(g)
    gtid = "gaptriple:factory:main"
    gaps = seed.attrs.get("gaps") or []
    g.node(gtid, "GapTriple", (gaps[0].get("statement") if gaps else "研究空白")[:80],
           run_id="factory_52_run", frontier_baseline=fr["baseline"],
           delta=(gaps[0].get("statement") if gaps else "新型分子设计"),
           why_not_before="现有方法未显式建模该约束",
           cite_key=f"seed:{seed.attrs.get('arxiv_id')}", source_span="Abstract L1-8",
           frontier_source=fr["source"])
    g.assert_rel(gtid, a, "GAP_FOR")
    trace["queries"].append({"stage": "②", "query": "query_frontier_baseline", "result": fr})
    log("②领域定位", "空白三元组+方法族谱", "GapTriple(C)+MethodLineage(B)",
        "Paper.gaps + MethodLineage", gtid, f"frontier从{fr['source']}查出",
        skill="retrieval+gap-formalizer")

    iid = "idea:factory:main"
    g.node(iid, "IdeaCandidate", "约束引导的分子设计", run_id="factory_52_run",
           mechanism="用领域规范约束生成过程", novelty_delta="显式证据规范引导",
           expected_direction="提升主指标", falsification_condition="消融无提升则推翻",
           selected=True)
    g.assert_rel(iid, gtid, "IDEA_FOR")
    log("③想法生成", "跨领域类比", "IdeaCandidate节点", gtid, iid, "机制+证伪条件")

    # ④ Claim（查询 EvaluationNorm）—— 带 evidence_type 交叉校验
    et = seed.attrs.get("evidence_type") or ""
    # 有 model_results / metrics 的论文不应判 derivational/interpretive（保真度会过低）
    has_numeric = bool(seed.attrs.get("model_results")) or bool(
        [b for b in g.by_type("Benchmark")
         if any(a.source == seed.id and a.relation in ("EVALUATED_ON", "PROPOSES_METHOD")
                for a in g.assertions) and b.attrs.get("metrics")])
    if has_numeric and et in ("derivational", "interpretive"):
        et = "experimental"
        g.nodes[seed.id].attrs["evidence_type_corrected"] = "experimental"
    norm = query_evaluation_norm(g, et)
    trace["queries"].append({"stage": "④", "query": "query_evaluation_norm",
                             "result": norm, "evidence_type_original": seed.attrs.get("evidence_type"),
                             "evidence_type_used": et, "corrected": has_numeric})
    cid = "claim:factory:main"
    g.node(cid, "Claim", "约束引导提升主指标", run_id="factory_52_run",
           statement="约束引导提升主指标", polarity="positive",
           expected_fidelity=norm["min_fidelity"], refutation_condition="主指标无显著则推翻",
           locked_at=time.strftime("%Y-%m-%dT%H:%M:%S"), method_hash="sha256:factory",
           norm_source=norm["source"])
    g.assert_rel(cid, iid, "FULFILLS")
    g.assert_rel(cid, a, "CLAIM_OF")
    if norm.get("source"):
        g.assert_rel(cid, norm["source"], "GROUNDED_IN")
    log("④主张形式化", "证据规范(B)", "Claim(C)独立节点",
        f"Idea + {norm['source']}", cid, f"fidelity={norm['min_fidelity']} 从规范查出",
        skill="claim-formalizer", verdict="LOCKED")

    fails = query_failure_checks(g)
    grade = "supported" if fails["found"] and len(fails["checks"]) < 10 else "suggests"
    g.nodes[cid].attrs["grade"] = grade
    g.nodes[cid].attrs["audit_source"] = fails["source"]
    trace["queries"].append({"stage": "⑦", "query": "query_failure_checks", "result": fails})
    log("⑦证据审计", "失败模式库(B)", "grade属性+AuditVerdict", fails["source"],
        f"grade={grade}", "从52篇失败模式查询+规则", skill="auditor", verdict=grade.upper())

    venue = query_venue_profile(g)
    sid = "section:factory:intro"
    g.node(sid, "SectionPlan", "Introduction", run_id="factory_52_run",
           section="Introduction", claims=[cid], word_budget=800,
           venue_found=venue["found"], venue_source=venue["source"])
    fid = "fig:factory:1"
    g.node(fid, "FigurePlan", "Figure 1", run_id="factory_52_run",
           fig_label="Figure 1", claim_ref=cid, inferential_role="main_effect")
    trace["queries"].append({"stage": "⑧", "query": "query_venue_profile", "result": venue})
    log("⑧叙事设计", "venue惯例(B)", "SectionPlan/FigurePlan(C)", venue["source"],
        f"{sid}+{fid}", f"venue found={venue['found']}，不伪造", skill="narrative-designer")

    rid = "pkg:factory"
    g.node(rid, "ReproductionPackage", "复现包", run_id="factory_52_run",
           code_snapshot="sha256:code", data_snapshot="sha256:data",
           env_spec="python3.12", one_click_script="run.sh", verification="pending")
    log("⑩终检交付", "工程交付", "ReproductionPackage(C)", cid, rid,
        "独立交付物", skill="delivery", verdict="PENDING")

    g.save(str(OUT))
    TRACE.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"nodes": len(g.nodes), "assertions": len(g.assertions),
           "stages": len(trace["stages"]), "queries": len(trace["queries"]),
           "out": str(OUT)}, flush=True)


if __name__ == "__main__":
    main()
