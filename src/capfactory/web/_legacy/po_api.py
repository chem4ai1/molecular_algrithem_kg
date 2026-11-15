"""v4 Web API：问题导向本体的词表、概念、导入、可比性与 CQ 查询.

显式 ``register(app)`` 挂载（兼容 FastAPI 0.135–0.162+）。
``/api/v4/import`` 只读取本地报告包 CSV/JSON，不访问网络、不执行任何模型。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ...config import REPO_ROOT
from ...po import (
    CONCEPT_CLASSES, ComparabilityKey, POGraph, compare_observations,
    default_registry, import_report_bundle, load_report_vocab,
)
from ...po.concepts import DIMENSIONS, RELATION_DOMAIN_RANGE, concept_class_fields
from ...po.benchmark import apply_all as apply_benchmarks
from ...po.benchmark import sota_report, to_markdown
from ...po.mapper import capability_to_po, metric_profile_to_po
from ...po.prompts import build_prompt, prompt_catalog
from ...po.reasoning import discover_gaps, infer, stats_report, summarize
from ...po.semantics import build_bundle, bundle_summary, context_pack
from ...po.taxonomy import (
    apply_taxonomy, classify_with_evidence, taxonomy_for_paper, taxonomy_matrix,
    taxonomy_spec,
)
from ...po.validation import validate_po_graph
from ...utils import now_iso

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_REPORT_DIR = REPO_ROOT.parent / "问题导向本体与知识图谱架构_20261109"
_GRAPH: Optional[POGraph] = None
_IMPORT_STATS: Dict[str, Any] = {}


class NormalizeRequest(BaseModel):
    name: str
    value: Any


class ImportRequest(BaseModel):
    report_dir: str = ""
    with_cq: bool = True
    with_taxonomy: bool = True


class TaxonomyApplyRequest(BaseModel):
    overwrite: bool = True


class ClassifyRequest(BaseModel):
    text: str
    kind: str = "domain"          # domain | algo
    limit: int = 3


class ContextRequest(BaseModel):
    task: str = "reasoning"
    focus: str = ""
    max_nodes: int = 40
    max_edges: int = 80


class PromptRequest(BaseModel):
    text: str = ""
    paper_id: str = ""
    paper_version_id: str = ""
    evidence_locator: str = ""
    question: str = ""
    focus: str = ""
    scope: str = "all"


class ReasonRequest(BaseModel):
    top_k: int = 20


class CompareRequest(BaseModel):
    a: Dict[str, Any]
    b: Dict[str, Any]


class CapabilityMapRequest(BaseModel):
    capability: Dict[str, Any]
    paper_id: str = ""
    paper_version_id: str = ""


class ValidateRequest(BaseModel):
    graph: Optional[Dict[str, Any]] = None


def _graph() -> POGraph:
    if _GRAPH is None:
        raise HTTPException(404, "尚未导入报告包；请先 POST /api/v4/import")
    return _GRAPH


# ---------------------------------------------------------------------------
def health() -> Dict[str, Any]:
    return {"ok": True, "api": "v4", "imported": _GRAPH is not None,
            "n_vocabularies": default_registry.summary()["n_vocabularies"],
            "n_concept_classes": len(CONCEPT_CLASSES), "ts": now_iso()}


def vocab_all() -> Dict[str, Any]:
    return {"summary": default_registry.summary(),
            "vocabularies": default_registry.to_dict()}


def vocab_one(name: str) -> Dict[str, Any]:
    v = default_registry.get(name)
    if not v:
        raise HTTPException(404, f"词表 {name} 不存在")
    return v.to_dict()


def normalize(req: NormalizeRequest) -> Dict[str, Any]:
    canonical, ok = default_registry.normalize(req.name, req.value)
    return {"name": req.name, "input": req.value, "canonical": canonical,
            "ok": ok, "problems": [] if ok else default_registry.validate(req.name, req.value)}


def concepts() -> Dict[str, Any]:
    return {
        "dimensions": DIMENSIONS,
        "n_classes": len(CONCEPT_CLASSES),
        "classes": {k: concept_class_fields(k) for k in CONCEPT_CLASSES},
    }


def relations() -> Dict[str, Any]:
    return {"n_relations": len(RELATION_DOMAIN_RANGE),
            "relations": {k: {"domain": list(v[0]), "range": list(v[1])}
                          for k, v in RELATION_DOMAIN_RANGE.items()}}


def do_import(req: ImportRequest) -> Dict[str, Any]:
    global _GRAPH, _IMPORT_STATS
    root = Path(req.report_dir) if req.report_dir else DEFAULT_REPORT_DIR
    if not root.is_dir():
        raise HTTPException(400, f"报告包目录不存在：{root}")
    g, stats = import_report_bundle(root)
    _GRAPH, _IMPORT_STATS = g, stats
    tax: Dict[str, Any] = {}
    if req.with_taxonomy:
        tax = apply_taxonomy(g, overwrite=True)
    bench = apply_benchmarks(g, overwrite=True)
    out = {"report_dir": str(root), "files": stats.get("files"),
           "backfilled": stats.get("backfilled"),
           "n_validation_problems": stats.get("n_validation_problems"),
           "validation_problems": stats.get("validation_problems", [])[:20],
           "stats": g.stats(),
           "vocab_summary": default_registry.summary(),
           "taxonomy": {k: v for k, v in tax.items() if k != "matrix"},
           "benchmark": bench}
    if req.with_cq:
        out["competency_questions"] = g.competency_questions()
    return out


def taxonomy() -> Dict[str, Any]:
    g = _GRAPH
    spec = taxonomy_spec()
    if g is None:
        return {"spec": spec, "imported": False}
    papers = [{"number": p.attrs.get("number") or p.id.split(":")[-1],
               "label": p.label,
               "domains": p.attrs.get("domain_codes", []),
               "algorithms": p.attrs.get("algo_codes", []),
               "source": p.attrs.get("taxonomy_source", ""),
               "rationale": p.attrs.get("taxonomy_rationale", "")}
              for p in g.by_type("Paper")]
    return {"spec": spec, "imported": True, "papers": papers,
            "matrix": taxonomy_matrix(g),
            "n_domain_nodes": len(g.by_type("Domain")),
            "n_algofamily_nodes": len(g.by_type("AlgorithmFamily"))}


def taxonomy_apply(req: TaxonomyApplyRequest) -> Dict[str, Any]:
    g = _graph()
    stats = apply_taxonomy(g, overwrite=req.overwrite)
    return {"stats": {k: v for k, v in stats.items() if k != "matrix"},
            "matrix": stats.get("matrix", {})}


def taxonomy_m() -> Dict[str, Any]:
    return taxonomy_matrix(_graph())


def taxonomy_classify(req: ClassifyRequest) -> Dict[str, Any]:
    kind = "algo" if req.kind in ("algo", "algorithm") else "domain"
    codes, evidence = classify_with_evidence(req.text, kind, limit=max(1, min(req.limit, 5)))
    names = (taxonomy_spec()["algorithms"] if kind == "algo"
             else taxonomy_spec()["domains"])
    name_map = {x["code"]: x["name"] for x in names}
    return {"kind": kind, "codes": codes,
            "names": [name_map.get(c, c) for c in codes],
            "evidence": evidence}


def taxonomy_paper(number: str) -> Dict[str, Any]:
    g = _graph()
    for p in g.by_type("Paper"):
        if str(p.attrs.get("number") or p.id.split(":")[-1]) == str(number):
            return {"number": number, "label": p.label,
                    "domains": p.attrs.get("domain_codes", []),
                    "domain_names": p.attrs.get("domain_names", []),
                    "algorithms": p.attrs.get("algo_codes", []),
                    "algorithm_names": p.attrs.get("algo_names", []),
                    "source": p.attrs.get("taxonomy_source", ""),
                    "rationale": p.attrs.get("taxonomy_rationale", ""),
                    "static_mapping": taxonomy_for_paper(number)}
    raise HTTPException(404, f"未找到论文 {number}")


def graph_stats() -> Dict[str, Any]:
    g = _graph()
    return {"meta": g.meta, "stats": g.stats(),
            "sample_nodes": [n.to_dict() for n in list(g.nodes.values())[:12]]}


def cq() -> Dict[str, Any]:
    return {"version_id": _graph().graph_id, **_graph().competency_questions()}


def compare(req: CompareRequest) -> Dict[str, Any]:
    return compare_observations(req.a, req.b)


def validate(req: ValidateRequest) -> Dict[str, Any]:
    g = POGraph.from_dict(req.graph) if req.graph else _graph()
    problems = validate_po_graph(g, default_registry)
    return {"n_problems": len(problems), "problems": problems[:100],
            "stats": g.stats()}


def mapping() -> Dict[str, Any]:
    return {
        "direction": "现有 CapFactory schema → 问题导向 PO 概念",
        "rows": [
            {"from": "PaperRecord", "to": "Paper + PaperVersion"},
            {"from": "Capability.name/summary", "to": "CapabilityClaim.statement/scope"},
            {"from": "Capability.task/inputs/outputs", "to": "Task"},
            {"from": "Capability.method/algorithm_family", "to": "Algorithm + Workflow"},
            {"from": "Capability.constraints", "to": "Limitation (QUALIFIES)"},
            {"from": "MetricSpec / MetricProfile", "to": "MetricDefinition + MetricObservation"},
            {"from": "MetricProfile.reported=None", "to": "MetricObservation.missing_state"},
            {"from": "Evidence / DomainEvidence", "to": "Evidence (+ version/hash/attribution)"},
            {"from": "Artifact", "to": "CodeArtifact / WeightArtifact / DataArtifact"},
            {"from": "Lesson", "to": "NegativeOutcome"},
            {"from": "ResearchDirection", "to": "ResearchProblem (P01–P11)"},
            {"from": "AlgoGraph 函数/块", "to": "Workflow.steps / CodeArtifact"},
            {"from": "MetricProfile.comparable_key()", "to": "comparable_key_v2()（15 维）"},
        ],
    }


def map_capability(req: CapabilityMapRequest) -> Dict[str, Any]:
    from ..domain.bio_schema import ProteinCapability
    cap = ProteinCapability.from_dict(req.capability)
    g = capability_to_po(cap, paper_id=req.paper_id,
                         paper_version_id=req.paper_version_id)
    return {"capability_id": cap.id, "stats": g.stats(),
            "validation_problems": g.validate()[:30],
            "concepts": [n.to_dict() for n in g.nodes.values()][:40]}


# ---------------------------------------------------------------------------
# v5：统计 / 语义包 / 推理 / 缺口 / 总结 / prompt
# ---------------------------------------------------------------------------
_KG_CACHE: Optional[Any] = None


def _kg() -> Any:
    global _KG_CACHE
    if _KG_CACHE is None:
        from ..kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.load()
        _KG_CACHE = kg
    return _KG_CACHE


def _target_graph(source: str) -> Any:
    return _kg() if source in ("kg", "knowledge", "main") else _graph()


def v5_stats(source: str = "po") -> Dict[str, Any]:
    g = _target_graph(source)
    return {"source": source, **stats_report(g)}


def v5_semantics(format: str = "json"):
    bundle = build_bundle()
    if format == "jsonld":
        return bundle.to_jsonld_context()
    if format in ("owl", "ttl", "turtle"):
        return PlainTextResponse(bundle.to_owl_turtle(), media_type="text/turtle")
    return {"summary": bundle_summary(bundle), "bundle": bundle.to_dict()}


def v5_context(req: ContextRequest) -> Dict[str, Any]:
    return context_pack(_graph(), task=req.task, focus=req.focus,
                        max_nodes=req.max_nodes, max_edges=req.max_edges)


def v5_reason(req: ReasonRequest) -> Dict[str, Any]:
    g = _graph()
    return {"inference": infer(g), "gaps": discover_gaps(g, top_k=req.top_k),
            "stats": stats_report(g)["totals"]}


def v5_gaps(top_k: int = 30, source: str = "po") -> Dict[str, Any]:
    return discover_gaps(_target_graph(source), top_k=top_k)


def v5_summary(scope: str = "all") -> Dict[str, Any]:
    return summarize(_graph(), scope=scope)


def v5_prompts() -> Dict[str, Any]:
    return {"catalog": prompt_catalog(),
            "semantics": bundle_summary(build_bundle(include_vocab=False))}


def v5_prompt(task: str, req: PromptRequest) -> Dict[str, Any]:
    g = _graph()
    if task == "extraction":
        text = build_prompt("extraction", text=req.text, paper_id=req.paper_id,
                            paper_version_id=req.paper_version_id,
                            evidence_locator=req.evidence_locator)
    elif task == "reasoning":
        pack = context_pack(g, task="reasoning", focus=req.focus)
        text = build_prompt("reasoning", pack=pack, question=req.question)
    elif task in ("gap_discovery", "gaps"):
        text = build_prompt("gap_discovery", stats=stats_report(g),
                            gaps=discover_gaps(g, top_k=20))
    elif task in ("summarization", "summary"):
        text = build_prompt("summarization", stats=stats_report(g), scope=req.scope)
    else:
        raise HTTPException(400, f"未知任务 {task}；可选 extraction/reasoning/"
                                 f"gap_discovery/summarization")
    return {"task": task, "chars": len(text), "prompt": text,
            "protocol": prompt_catalog()["tasks"].get(
                "gap_discovery" if task == "gaps" else task, {})}


def benchmarks() -> Dict[str, Any]:
    g = _graph()
    items = []
    for b in g.by_type("Benchmark"):
        items.append({
            "id": b.id, "name": b.label,
            "dataset_id": b.attrs.get("dataset_id"),
            "input_schema": b.attrs.get("input_schema"),
            "output_schema": b.attrs.get("output_schema"),
            "research_object": b.attrs.get("research_object"),
            "task_family": b.attrs.get("task_family"),
            "split_rule": b.attrs.get("split_rule"),
            "metric_ids": b.attrs.get("metric_ids", []),
            "problem_ids": b.attrs.get("problem_ids", []),
            "tested_by_papers": b.attrs.get("tested_by_papers", []),
            "tested_by_codes": b.attrs.get("tested_by_codes", []),
            "n_observations": b.attrs.get("n_observations", 0),
        })
    sota = sota_report(g)
    return {"n_benchmarks": len(items), "n_entries": len(g.by_type("LeaderboardEntry")),
            "sota": {"n_groups": sota["n_groups"],
                     "n_claimable": sota["n_claimable"],
                     "n_single": sota["n_single"]},
            "items": items}


def benchmark_one(benchmark_id: str) -> Dict[str, Any]:
    g = _graph()
    if benchmark_id not in g.nodes:
        raise HTTPException(404, f"未找到基准 {benchmark_id}")
    b = g.nodes[benchmark_id]
    entries = []
    for e in g.outgoing(benchmark_id, "HAS_LEADERBOARD"):
        n = g.nodes.get(e.target)
        if n:
            entries.append({"id": n.id, "metric": n.attrs.get("metric_id"),
                            "value": n.attrs.get("value"), "unit": n.attrs.get("unit"),
                            "direction": n.attrs.get("direction"),
                            "rank": n.attrs.get("rank"),
                            "is_sota": n.attrs.get("is_sota"),
                            "sota_claimable": n.attrs.get("sota_claimable"),
                            "group_size": n.attrs.get("group_size"),
                            "subject": n.attrs.get("subject"),
                            "paper": n.attrs.get("paper_id"),
                            "code": n.attrs.get("code_id")})
    entries.sort(key=lambda x: (str(x["metric"]), x["rank"] or 99))
    return {"id": b.id, "label": b.label,
            "attrs": {k: b.attrs.get(k) for k in
                      ("dataset_id", "input_schema", "output_schema", "research_object",
                       "task_family", "split_rule", "version", "license_status",
                       "metric_ids", "problem_ids", "tested_by_papers",
                       "tested_by_codes", "n_observations", "source_evidence_ids")},
            "leaderboard": entries}


def sota() -> Dict[str, Any]:
    g = _graph()
    rep = sota_report(g)
    return {**rep, "markdown": to_markdown(rep)}


def po_page() -> HTMLResponse:
    p = STATIC_DIR / "po.html"
    if not p.exists():
        raise HTTPException(500, "PO 工作台页面缺失")
    return HTMLResponse(p.read_text(encoding="utf-8"))


_V4_ROUTES = [
    ("/api/v4/health", health, "GET", True),
    ("/api/v4/vocab", vocab_all, "GET", True),
    ("/api/v4/vocab/{name}", vocab_one, "GET", True),
    ("/api/v4/normalize", normalize, "POST", True),
    ("/api/v4/concepts", concepts, "GET", True),
    ("/api/v4/relations", relations, "GET", True),
    ("/api/v4/import", do_import, "POST", True),
    ("/api/v4/taxonomy", taxonomy, "GET", True),
    ("/api/v4/benchmarks", benchmarks, "GET", True),
    ("/api/v4/benchmarks/{benchmark_id}", benchmark_one, "GET", True),
    ("/api/v4/sota", sota, "GET", True),
    ("/api/v4/taxonomy/apply", taxonomy_apply, "POST", True),
    ("/api/v4/taxonomy/matrix", taxonomy_m, "GET", True),
    ("/api/v4/taxonomy/classify", taxonomy_classify, "POST", True),
    ("/api/v4/taxonomy/paper/{number}", taxonomy_paper, "GET", True),
    ("/api/v4/graph", graph_stats, "GET", True),
    ("/api/v4/cq", cq, "GET", True),
    ("/api/v4/compare", compare, "POST", True),
    ("/api/v4/validate", validate, "POST", True),
    ("/api/v4/mapping", mapping, "GET", True),
    ("/api/v4/map-capability", map_capability, "POST", True),
    # v5：语义层与大模型交互
    ("/api/v5/stats", v5_stats, "GET", True),
    ("/api/v5/semantics", v5_semantics, "GET", True),
    ("/api/v5/context", v5_context, "POST", True),
    ("/api/v5/reason", v5_reason, "POST", True),
    ("/api/v5/gaps", v5_gaps, "GET", True),
    ("/api/v5/summary", v5_summary, "GET", True),
    ("/api/v5/prompts", v5_prompts, "GET", True),
    ("/api/v5/prompts/{task}", v5_prompt, "POST", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V4_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
