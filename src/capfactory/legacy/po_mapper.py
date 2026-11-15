"""现有 CapFactory schema ⇄ 问题导向本体（PO）的双向映射.

报告 §5.3 指出当前 schema 的根本问题是「一个 Capability 同时充当主张、任务、
算法、流程与评测」。本模块把一条扁平的 ``Capability/ProteinCapability``
**拆开**成 PO 的五维概念，并可从 ``CapabilityClaim`` 反向组装回可执行能力。

映射表：

| 现有 | PO |
|---|---|
| ``PaperRecord`` | ``Paper`` + ``PaperVersion`` |
| ``Capability.name/summary`` | ``CapabilityClaim.statement`` |
| ``Capability.task/inputs/outputs`` | ``Task`` |
| ``Capability.method/algorithm_family`` | ``Algorithm`` + ``Workflow`` |
| ``Capability.constraints`` | ``Limitation``（QUALIFIES 主张） |
| ``MetricSpec / MetricProfile`` | ``MetricDefinition`` + ``MetricObservation`` |
| ``Evidence / DomainEvidence`` | ``Evidence``（+ PaperVersion/hash/attribution） |
| ``Artifact`` | ``CodeArtifact`` / ``WeightArtifact`` / ``DataArtifact`` |
| ``Lesson`` | ``NegativeOutcome``（区分阴性/合成失败/未测） |
| ``ResearchDirection`` | ``ResearchProblem``（挂 P01–P11 问题树） |
| ``AlgoGraph`` 函数/块 | ``Workflow.steps`` / ``CodeArtifact`` 关联 |
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..po.comparability import comparability_key
from ..po.concepts import Concept
from ..po.store import POGraph


def _cid(prefix: str, *parts: Any) -> str:
    return f"{prefix}::" + "::".join(str(p) for p in parts if p not in (None, ""))


def evidence_to_po(evidence: Any, *, paper_version_id: str = "",
                   source_text: str = "", attribution: str = "author_explicit") -> Concept:
    """``Evidence`` / ``DomainEvidence`` → PO ``Evidence``。"""
    quote = str(getattr(evidence, "quote", "") or "")
    locator = str(getattr(evidence, "locator", "") or "")
    source_id = str(getattr(evidence, "source_id", "") or "")
    kind = str(getattr(evidence, "kind", "paper") or "paper")
    anchored = bool(getattr(evidence, "anchored", False))
    if not anchored and quote and source_text:
        import re
        anchored = (re.sub(r"\s+", " ", quote).strip()
                    in re.sub(r"\s+", " ", source_text))
    return Concept(
        id=_cid("evidence", source_id or "src", locator or "loc", quote[:24]),
        type="Evidence", label=f"{source_id} · {locator or quote[:40]}",
        attribution=attribution,
        source_version=paper_version_id,
        attrs={"paper_version_id": paper_version_id, "locator": locator or "(unlocated)",
               "quote": quote[:500], "kind": kind, "anchored": anchored,
               "section": locator, "attribution_kind": kind},
    )


def metric_profile_to_po(mp: Any, *, observation_value: Optional[float] = None,
                         evidence_ids: Sequence[str] = (),
                         condition: Optional[Dict[str, Any]] = None,
                         stage: str = "", numerator: Any = None,
                         denominator: Any = None) -> Tuple[Concept, Concept]:
    """``MetricSpec`` / ``MetricProfile`` → ``MetricDefinition`` + ``MetricObservation``。

    关键升级：定义与观测分离；观测带单位/条件/分母/阶段/证据；
    值缺失时写 ``missing_state`` 而不是把 ``None`` 当 0。
    """
    name = str(getattr(mp, "name", "") or "unknown_metric")
    direction = str(getattr(mp, "direction", "higher") or "higher")
    dataset = str(getattr(mp, "dataset", "") or "")
    split = str(getattr(mp, "split", "") or "")
    protocol = str(getattr(mp, "protocol", "") or "")
    unit = str(getattr(mp, "unit", "") or "see observation unit")
    definition = str(getattr(mp, "note", "") or getattr(mp, "definition", "") or "")
    definition_id = _cid("metric", name)
    defn = Concept(
        id=definition_id, type="MetricDefinition", label=name,
        attrs={"name": name, "direction": direction, "definition": definition,
               "unit_scale": "see observation unit", "value_type": "number"},
    )
    value = observation_value if observation_value is not None else getattr(mp, "reported", None)
    obs_id = _cid("observation", name, dataset, split, protocol, stage)
    attrs: Dict[str, Any] = {
        "metric": name, "metric_definition_id": definition_id,
        "unit": unit, "dataset_id": dataset, "split_rule": split or protocol,
        "input_condition": protocol, "stage": stage, "direction": direction,
        "condition": condition or {}, "evidence_ids": list(evidence_ids),
        "comparability_key": comparability_key({
            "metric": name, "dataset_id": dataset, "split_rule": split or protocol,
            "input_condition": protocol, "stage": stage, "condition": condition or {},
            "direction": direction,
        }).key(),
    }
    if numerator is not None:
        attrs["numerator"] = numerator
    if denominator is not None:
        attrs["denominator"] = denominator
        attrs["aggregation"] = "derived_fraction"
    if value is None:
        attrs["missing_state"] = "not_reported"
        attrs["missing_reasons"] = {"reported": "not_reported"}
    else:
        attrs["value"] = float(value)
        attrs["aggregation"] = attrs.get("aggregation", "reported_value")
    obs = Concept(id=obs_id, type="MetricObservation", label=f"{name} @ {dataset or 'n/a'}",
                  attrs=attrs, evidence_ids=list(evidence_ids),
                  missing_states={"reported": "not_reported"} if value is None else {})
    return defn, obs


def capability_to_po(cap: Any, *, paper_id: str = "",
                     paper_version_id: str = "",
                     graph: Optional[POGraph] = None,
                     source_text: str = "") -> POGraph:
    """把一条扁平能力拆成 PO 五维概念，返回（可增量的）POGraph。"""
    g = graph or POGraph("po::capability::" + str(getattr(cap, "id", "cap")))
    cid = str(getattr(cap, "id", "cap"))
    name = str(getattr(cap, "name", "") or cid)
    attribution = str(getattr(cap, "attribution", "evidence_bounded_synthesis"))
    evidence_level = str(getattr(cap, "evidence_grade", "") or "mixed; consult individual evaluations")
    if evidence_level in ("A", "B", "C", "D"):
        evidence_level = {"A": "computational", "B": "biochemical",
                          "C": "computational", "D": "mixed; consult individual evaluations"}[evidence_level]

    # 主张（不是算法布尔属性）
    claim_id = _cid("claim", cid)
    g.node(claim_id, "CapabilityClaim", name,
           attribution=attribution, source_version=paper_version_id,
           statement=name, scope=str(getattr(cap, "summary", "") or ""),
           evidence_level=evidence_level,
           capability_id=cid, confidence=float(getattr(cap, "confidence", 0.5)))

    # 任务
    task_family = "property_prediction"
    if hasattr(cap, "task_family"):
        task_family = str(cap.task_family)
    task_id = _cid("task", cid)
    inputs = [i.to_dict() if hasattr(i, "to_dict") else (i if isinstance(i, dict) else {"name": str(i)})
              for i in (getattr(cap, "inputs", []) or [])]
    outputs = [o.to_dict() if hasattr(o, "to_dict") else (o if isinstance(o, dict) else {"name": str(o)})
               for o in (getattr(cap, "outputs", []) or [])]
    g.node(task_id, "Task", str(getattr(cap, "task", "") or name),
           task_family=task_family, input_output={"inputs": inputs, "outputs": outputs},
           input_condition=str(getattr(cap, "bio_spec", None).text()
                               if hasattr(getattr(cap, "bio_spec", None), "text") else ""),
           capability_id=cid)

    # 算法 + 流程
    algo_id = _cid("algorithm", cid)
    arch = str(getattr(cap, "algorithm_family", "") or "other")
    g.node(algo_id, "Algorithm", name, name=name, architecture=arch,
           version_status="as described by cited paper", capability_id=cid)
    wf_id = _cid("workflow", cid)
    g.node(wf_id, "Workflow", name + " workflow",
           steps=str(getattr(cap, "method", "") or ""),
           human_contribution="not_reported", scope=str(getattr(cap, "summary", "") or ""),
           algorithm_ids=[algo_id])
    g.assert_rel(claim_id, wf_id, "ABOUT_METHOD", attribution=attribution)
    g.assert_rel(task_id, algo_id, "ADDRESSED_BY", attribution=attribution)
    g.assert_rel(wf_id, algo_id, "IMPLEMENTS", attribution=attribution)

    # 局限（QUALIFIES 主张）
    for i, c in enumerate(getattr(cap, "constraints", []) or []):
        lid = _cid("limitation", cid, i)
        g.node(lid, "Limitation", str(c)[:120], statement=str(c),
               attribution=attribution, scope="capability")
        g.assert_rel(lid, claim_id, "QUALIFIES", attribution=attribution)

    # 数据与切分
    datasets = (getattr(cap, "provenance", {}) or {}).get("datasets", []) or []
    for i, ds in enumerate(datasets):
        did = _cid("dataset", cid, i)
        sid = _cid("split", cid, i)
        g.node(did, "Dataset", str(ds), name=str(ds), version_status="unknown")
        g.node(sid, "DatasetSplit", f"{ds} split", rule="not_reported",
               overlap_risk="not_independently_rerun")
        g.assert_rel(did, sid, "HAS_SPLIT", attribution=attribution)

    # 证据
    ev_ids: List[str] = []
    for e in (getattr(cap, "evidence", []) or []):
        ec = evidence_to_po(e, paper_version_id=paper_version_id,
                            source_text=source_text, attribution=attribution)
        g.add(ec)
        ev_ids.append(ec.id)
        if paper_version_id:
            g.node(paper_version_id, "PaperVersion", paper_version_id,
                   paper_id=paper_id or f"paper::{cid}",
                   source_kind="published_article")
            g.assert_rel(ec.id, paper_version_id, "EXTRACTED_FROM", attribution=attribution)

    # 指标定义 + 观测 + 条件 + 评测
    for i, m in enumerate(getattr(cap, "metrics", []) or []):
        defn, obs = metric_profile_to_po(m, evidence_ids=ev_ids)
        defn.id, obs.id = _cid("metric", cid, i), _cid("observation", cid, i)
        obs.attrs["metric_definition_id"] = defn.id
        g.add(defn)
        g.add(obs)
        cond_id = _cid("condition", cid, i)
        g.node(cond_id, "ExperimentalCondition", f"condition {i}",
               protocol=str(getattr(m, "protocol", "") or ""),
               split=str(getattr(m, "split", "") or ""))
        run_id = _cid("evaluation", cid, i)
        g.node(run_id, "EvaluationRun", f"eval {i}",
               evaluation_kind="author_reported_not_rerun",
               protocol=str(getattr(m, "protocol", "") or ""),
               modality="computational", source_paper=paper_id)
        g.assert_rel(run_id, defn.id, "USES_METRIC", attribution=attribution)
        g.assert_rel(run_id, obs.id, "PRODUCES_OBSERVATION", attribution=attribution)
        g.assert_rel(obs.id, defn.id, "OF_METRIC", attribution=attribution)
        g.assert_rel(obs.id, cond_id, "HAS_CONDITION", attribution=attribution)
        for evid in ev_ids:
            g.assert_rel(obs.id, evid, "SUPPORTED_BY", attribution=attribution,
                         evidence_ids=[evid])
        g.assert_rel(claim_id, run_id, "EVALUATED_IN", attribution=attribution)
        for evid in ev_ids:
            g.assert_rel(claim_id, evid, "SUPPORTED_BY", attribution=attribution,
                         evidence_ids=[evid])

    # 代码资源（多轴开放性）
    for i, aid in enumerate(getattr(cap, "artifact_ids", []) or []):
        code_id = _cid("code", cid, i)
        g.node(code_id, "CodeArtifact", str(aid),
               availability="open_licensed", license="license_unverified",
               artifact_kind="core", scope="core_implementation",
               url=str(aid), checked_date="", capability_id=cid)
        if paper_id:
            g.assert_rel(paper_id, code_id, "HAS_CODE", attribution=attribution)

    # 问题树挂接
    for pid in (getattr(cap, "problem_ids", []) or []):
        if pid not in g.nodes:
            g.node(str(pid), "ResearchProblem", str(pid),
                   label=str(pid), question=f"研究子问题 {pid}（可检验问题待补录）",
                   status="open_or_partially_addressed",
                   attribution="analyst_synthesis")
        if paper_id:
            g.assert_rel(paper_id, str(pid), "ANALYST_RELEVANT_TO",
                         attribution="analyst_synthesis")
    return g


def po_to_capability(claim: Concept, graph: Optional[POGraph] = None) -> Any:
    """从 ``CapabilityClaim`` 组装回 ``ProteinCapability``（保留 PO 语义字段）。"""
    from ..domain.bio_schema import ProteinCapability

    a = claim.attrs
    problem_ids = [e.target for e in (graph.outgoing(claim.id, "ANALYST_RELEVANT_TO")
                                      if graph else [])]
    return ProteinCapability(
        id=str(a.get("capability_id") or claim.id),
        name=str(a.get("statement") or claim.label),
        summary=str(a.get("scope") or ""),
        task=str(a.get("task") or ""),
        confidence=float(a.get("confidence", 0.5)),
        evidence_grade=str(a.get("evidence_grade") or "D"),
        problem_ids=problem_ids,
        claim_scope=str(a.get("scope") or ""),
        evidence_level=str(a.get("evidence_level") or ""),
        attribution=claim.attribution,
        provenance={"po_claim_id": claim.id, "schema": "po_v1"},
    )
