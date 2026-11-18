#!/usr/bin/env python3
"""V2：C 类决策节点全部走 WritingContext 类型化接口。

对比 V1（脚本 g.node 硬写）：
  - 每个 C 节点由专用方法创建（formulate_gap / formalize_claim / ...）
  - B 类查询内置在方法里，自动写 source/via/verdict
  - 输出 append-only decisions log（Decision Ledger）
"""
from __future__ import annotations
import json, sys, time
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.context import WritingContext

GRAPH = ROOT / "storage/sciforge/semantic_factory_52.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_v2.json"
TRACE = ROOT / "storage/sciforge/factory_decision_trace_v2.json"


def build_b_graph(g):
    """B 类图谱聚合（与 V1 相同，一次建长期复用）。"""
    papers = g.by_type("Paper")
    groups = defaultdict(list)
    for a in g.by_type("Algorithm"):
        groups[a.attrs.get("task_type") or "unknown"].append(a.id)
    for tt, mids in groups.items():
        if not tt or tt == "unknown":
            continue
        nid = f"lineage:factory:{tt}"
        g.node(nid, "MethodLineage", f"族谱:{tt}", task_type=tt,
               methods=mids[:20], n=len(mids), source="aggregate_from_52")
        for mid in mids[:20]:
            if mid in g.nodes:
                g.assert_rel(nid, mid, "LINEAGE_OF")
    by_et = defaultdict(list)
    for p in papers:
        et = p.attrs.get("evidence_type")
        if et:
            by_et[et].append(p)
    for et, ps in by_et.items():
        accepted = list({m for p in ps for m in (p.attrs.get("evidence_norm") or [])})
        nid = f"norm:factory:{et}"
        g.node(nid, "EvaluationNorm", et, evidence_type=et,
               accepted_metrics=accepted[:12], n_papers=len(ps),
               min_fidelity="numerical" if et in ("experimental", "simulational") else "qualitative",
               title=f"{et} 证据规范",
               summary=f"从 {len(ps)} 篇论文聚合的 {et} 类证据规范",
               findings=[{"summary": f"认可指标：{', '.join(accepted[:4])}",
                          "explanation": f"在 {len(ps)} 篇 {et} 论文中反复出现"}],
               rating=min(len(ps)/20.0, 1.0),
               rating_explanation=f"基于 {len(ps)} 篇论文的支持度",
               community_level=1)
        for p in ps:
            g.assert_rel(nid, p.id, "DERIVED_FROM_PAPERS")
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
            g.node(f"venue:factory:{v}", "VenueProfile", v, venue=v, n_papers=n)
    else:
        g.node("venue:factory:unknown", "VenueProfile", "venue未知",
               venue="unknown", note="52篇PDF均未抽venue")


def main():
    g = POGraph.load(str(GRAPH))
    build_b_graph(g)
    ctx = WritingContext(g, "factory_v2")
    papers = g.by_type("Paper")
    seed = papers[0]

    # ① 问题锚（接口）
    a = ctx.freeze_problem(
        question=str(seed.attrs.get("research_question") or "")[:120],
        seed_ids=[seed.id])
    g.nodes[a].attrs.update({"answerability_criteria": ["报告主指标", "对比≥2 baseline"],
                             "boundary": ["不回答通用LLM能力"], "feasibility": {"data": "yes"}})

    # ② GapTriple（接口：内置 frontier 查询）
    gaps = seed.attrs.get("gaps") or []
    gid = ctx.formulate_gap(
        statement=(gaps[0].get("statement") if gaps else "研究空白")[:80],
        anchor_id=a,
        task_type=str(seed.attrs.get("problem_category") or ""),
        cite_key=f"seed:{seed.attrs.get('arxiv_id')}",
        source_span="Abstract L1-8",
        delta="显式约束引导的分子设计",
        why_not_before="现有方法未显式建模该约束")

    # ③ Idea（接口）
    iid = ctx.propose_idea(
        gap_id=gid, mechanism="用领域规范约束生成过程",
        novelty_delta="显式证据规范引导", expected_direction="提升主指标",
        falsification_condition="消融无提升则推翻")

    # ④ Claim（接口：内置 Norm 查询；无推翻条件会 BLOCKED）
    et = seed.attrs.get("evidence_type") or ""
    has_numeric = bool(seed.attrs.get("model_results")) or bool(
        [b for b in g.by_type("Benchmark") if b.attrs.get("metrics")])
    if has_numeric and et in ("derivational", "interpretive"):
        et = "experimental"
    cid = ctx.formalize_claim(
        idea_id=iid, anchor_id=a, statement="约束引导提升主指标",
        polarity="positive", evidence_type=et,
        refutation_condition="主指标无显著则推翻")

    # 演示门控：故意调用一次无推翻条件的 Claim，应被 BLOCKED
    blocked = ctx.formalize_claim(
        idea_id=iid, anchor_id=a, statement="不完整的claim",
        refutation_condition="")

    # ⑦ 定档（接口：内置 FailureModeLibrary 查询）
    grade = ctx.grade_claim(claim_id=cid, has_numeric_evidence=True, n_checks=8)

    # ⑧ 叙事（接口：内置 VenueProfile 查询）
    sid = ctx.design_narrative(claim_id=cid, section="Introduction", fig_label="Figure 1")

    # ⑩ 交付（接口：verification=pending 应 BLOCKED）
    pid = ctx.deliver(claim_id=cid, code_snapshot="sha256:code",
                      data_snapshot="sha256:data", env_spec="python3.12",
                      one_click_script="run.sh", verification="pending")

    g.save(str(OUT))
    trace = {"decisions": ctx.decisions,
             "summary": {"nodes": len(g.nodes), "assertions": len(g.assertions),
                         "n_decisions": len(ctx.decisions),
                         "blocked": [d for d in ctx.decisions if "BLOCKED" in d["verdict"]]}}
    TRACE.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(trace["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
