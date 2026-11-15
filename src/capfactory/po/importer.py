"""把报告交付包导入 POGraph（幂等、可复现）.

读取 ``nodes.csv / edges.csv / problems.csv / 指标观测表.csv / 证据定位表.csv /
论文问题算法评测矩阵.csv / ontology.json``，做三件事：

1. 字段名 camelCase → snake_case，并补齐「label/statement/name/title」类必填字段；
2. 把 ``OF_METRIC / SUPPORTED_BY / EXTRACTED_FROM`` 等边反填为节点属性
   （``metric_definition_id`` / ``evidence_ids`` / ``paper_version_id``），满足 SHACL 约束；
3. 证据 ID 归一到节点 ID，边保留 ``Assertion`` reification 的 attribution。

导入后调用 ``graph.validate()`` 复核，统计写进 ``meta.import_stats``。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .concepts import CONCEPT_SPECS, Concept
from .store import Assertion, POGraph
from .vocab import default_registry, load_report_vocab

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")
_FIELD_MAP = {
    "evidenceLevel": "evidence_level", "sourcePaper": "source_paper",
    "unitScale": "unit_scale", "valueType": "value_type",
    "evaluationKind": "evaluation_kind", "stageType": "stage_type",
    "outcomeType": "outcome_type", "versionId": "paper_version_id",
    "extractionFileSha256": "extraction_file_sha256", "extractionFile": "extraction_file",
    "sourceUrl": "source_url", "readDate": "read_date", "sourceId": "source_id",
    "paperNumber": "paper_number", "taskFamily": "task_family",
    "leakageAudit": "leakage_audit", "identifierStatus": "identifier_status",
    "externalIdStatus": "external_id_status", "versionStatus": "version_status",
    "coverageLevel": "coverage_level", "readingCoverage": "reading_coverage",
    "coverageGap": "coverage_gap", "sourceEvidenceIds": "source_evidence_ids",
    "humanContribution": "human_contribution", "inputOutput": "input_output",
    "protocolCompletion": "protocol_completion", "evidenceBasis": "evidence_basis",
    "missingReason": "missing_reason", "nextResearchQuestion": "next_research_question",
    "missingReasons": "missing_states", "checkedDate": "checked_date",
    "versionDate": "version_date", "sampleBudget": "sample_budget",
    "sampleCount": "sample_count", "inputCondition": "input_condition",
    "independentExperiments": "independent_experiments", "nBiological": "n_biological",
    "topK": "top_k", "protocolCompletion": "protocol_completion",
}
_LABEL_FIELDS = {"label", "name", "title", "statement", "question"}


def _rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _props(raw: str) -> Dict[str, Any]:
    try:
        d = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = _FIELD_MAP.get(k, k)
        if key not in _FIELD_MAP and any(c.isupper() for c in k):
            key = _CAMEL.sub("_", k).lower()
        out[key] = v
    return out


def _evidence_ids(raw: str, node_ids: set) -> List[str]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        items = [x.strip() for x in (raw or "").split(",") if x.strip()]
    out = []
    for x in items:
        s = str(x)
        if s in node_ids:
            out.append(s)
        elif f"evidence:{s}" in node_ids:
            out.append(f"evidence:{s}")
        else:
            out.append(s)
    return out


def import_report_bundle(report_dir: str | Path, *,
                         graph: Optional[POGraph] = None,
                         load_vocab: bool = True) -> Tuple[POGraph, Dict[str, Any]]:
    """导入交付包，返回 ``(POGraph, 统计)``。"""
    root = Path(report_dir)
    g = graph or POGraph(f"po::report::{root.name}")
    stats: Dict[str, Any] = {"root": str(root), "files": {}}
    if load_vocab:
        stats["vocab"] = load_report_vocab(root, default_registry)

    node_rows = _rows(root / "nodes.csv")
    edge_rows = _rows(root / "edges.csv")
    stats["files"]["nodes.csv"] = len(node_rows)
    stats["files"]["edges.csv"] = len(edge_rows)
    if not node_rows:
        return g, {**stats, "error": "nodes.csv 不存在或为空"}

    node_ids = {r["id"] for r in node_rows}
    # 先建节点
    for r in node_rows:
        ctype = r["type"]
        props = _props(r.get("properties", ""))
        spec = CONCEPT_SPECS.get(ctype)
        if spec:
            for fld in spec.required:
                if fld in _LABEL_FIELDS and fld not in props:
                    props[fld] = r["label"]
        attribution = str(props.pop("attribution", "analyst_synthesis"))
        missing_states = props.pop("missing_states", {}) or {}
        if not isinstance(missing_states, dict):
            missing_states = {}
        evidence_ids = props.pop("evidence_ids", []) or []
        source_version = str(props.pop("paper_version_id", "") or "")
        g.node(r["id"], ctype, r["label"],
               attribution=attribution, missing_states=missing_states,
               evidence_ids=list(evidence_ids), source_version=source_version,
               **props)

    # 再建断言
    for r in edge_rows:
        ev = _evidence_ids(r.get("evidenceIds", ""), node_ids)
        g.assert_rel(r["source"], r["target"], r["relation"],
                     attribution=r.get("attribution") or "analyst_synthesis",
                     evidence_ids=ev, assertion_id=r.get("id", ""))

    # 边反填：满足 SHACL 与字段契约
    filled = {"metric_definition_id": 0, "evidence_ids": 0, "paper_version_id": 0}
    for o in g.by_type("MetricObservation"):
        for e in g.outgoing(o.id, "OF_METRIC"):
            o.attrs.setdefault("metric_definition_id", e.target)
            m = g.nodes.get(e.target)
            if m:
                o.attrs.setdefault("metric", m.label)
            filled["metric_definition_id"] += 1
        sup = [e.target for e in g.outgoing(o.id, "SUPPORTED_BY")]
        if sup and not o.evidence_ids:
            o.evidence_ids = sup
            filled["evidence_ids"] += 1
        if o.attrs.get("value") is not None and not isinstance(o.attrs["value"], (int, float)):
            try:
                o.attrs["value"] = float(o.attrs["value"])
            except (TypeError, ValueError):
                o.attrs.pop("value", None)
                o.attrs["missing_state"] = "not_extracted"
    for pv in g.by_type("PaperVersion"):
        # HAS_VERSION 的反边：把 work-level 论文身份回填到版本节点
        for e in g.incoming(pv.id, "HAS_VERSION"):
            pv.attrs.setdefault("paper_id", e.source)
            filled["paper_id"] = filled.get("paper_id", 0) + 1
    for ev in g.by_type("Evidence"):
        for e in g.outgoing(ev.id, "EXTRACTED_FROM"):
            ev.attrs.setdefault("paper_version_id", e.target)
            if not ev.source_version:
                ev.source_version = e.target
            filled["paper_version_id"] += 1
    for c in g.by_type("CapabilityClaim"):
        sup = [e.target for e in g.outgoing(c.id, "SUPPORTED_BY")]
        if sup and not c.evidence_ids:
            c.evidence_ids = sup
    stats["backfilled"] = filled

    # problems.csv 补充问题树
    probs = _rows(root / "problems.csv")
    for r in probs:
        n = g.nodes.get(r["id"]) or g.nodes.get(f"problem:{r['id']}")
        if not n:
            continue
        n.attrs.setdefault("parent", r["parent"])
        n.attrs.setdefault("question", r["question"])
        n.attrs.setdefault("suggested_solution", r["suggestedSolution"])
        n.attrs.setdefault("related_papers", r["relatedPapers"])
        n.attrs.setdefault("attribution", r["attribution"])
        n.attrs.setdefault("status", "open_or_partially_addressed")
    stats["files"]["problems.csv"] = len(probs)

    # 证据定位表：结构化 section / hash（报告 §9 要求 hash 而非旧绝对路径）
    evrows = _rows(root / "证据定位表.csv")
    for r in evrows:
        n = g.nodes.get(f"evidence:{r['sourceId']}") or g.nodes.get(r["sourceId"])
        if not n:
            continue
        n.attrs.setdefault("section", r.get("section", ""))
        n.attrs.setdefault("source_url", r.get("sourceUrl", ""))
        n.attrs.setdefault("extraction_file_sha256", r.get("extractionFileSha256", ""))
        n.attrs.setdefault("read_date", r.get("readDate", ""))
        n.attrs.setdefault("paper_version_id", r.get("versionId", ""))
    stats["files"]["证据定位表.csv"] = len(evrows)

    # 指标观测表：补齐 modality / unit / stage / 分母等（CSV 是更细的观测源）
    obsrows = _rows(root / "指标观测表.csv")
    for r in obsrows:
        n = g.nodes.get(r["observationId"])
        if not n:
            continue
        n.attrs.setdefault("metric", r["metric"])
        n.attrs.setdefault("unit", r["unit"])
        n.attrs.setdefault("modality", r["modality"])
        n.attrs.setdefault("subject", r["subject"])
        n.attrs.setdefault("target", r["system"])
        n.attrs.setdefault("context", r["context"])
        try:
            extra = json.loads(r.get("extra") or "{}")
        except json.JSONDecodeError:
            extra = {}
        for k, v in extra.items():
            key = _FIELD_MAP.get(k, _CAMEL.sub("_", k).lower())
            n.attrs.setdefault(key, v)
        try:
            mr = json.loads(r.get("missingReasons") or "{}")
        except json.JSONDecodeError:
            mr = {}
        for k, v in mr.items():
            n.missing_states.setdefault(k, str(v))
    stats["files"]["指标观测表.csv"] = len(obsrows)

    # 论文矩阵：代码/许可/切分等
    matrix = _rows(root / "论文问题算法评测矩阵.csv")
    for r in matrix:
        for prefix, ctype in (("paper", "Paper"),):
            pid = f"{prefix}:{r['paperNumber']}"
            n = g.nodes.get(pid)
            if not n:
                continue
            n.attrs.setdefault("code_status", r.get("codeStatus", ""))
            n.attrs.setdefault("license", r.get("license", ""))
            n.attrs.setdefault("dataset", r.get("dataset", ""))
            n.attrs.setdefault("split", r.get("split", ""))
            n.attrs.setdefault("problem_ids", r.get("problemIds", ""))
    stats["files"]["论文问题算法评测矩阵.csv"] = len(matrix)

    problems = g.validate()
    stats["validation_problems"] = problems
    stats["n_validation_problems"] = len(problems)
    stats["stats"] = g.stats()
    g.meta["import_stats"] = {k: v for k, v in stats.items()
                              if k not in ("vocab", "stats", "validation_problems")}
    return g, stats
