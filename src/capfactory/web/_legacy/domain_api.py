"""v2 Web API：领域 Schema / 抽取 / 推理 / 验证 / SciForge 门.

挂载方式（``capfactory/web/server.py``）::

    from .domain_api import router as domain_router
    app.include_router(domain_router)

所有接口均为纯计算或只读图谱访问，不触发 LLM 计费；``/api/v2/validate``
会在带超时的隔离子进程中执行用户提交的代码，请勿在未加鉴权的公网直接暴露
（部署见 ``docs/LINUX_DEPLOY.md``）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...domain.bio_schema import json_schema, owl_turtle
from ...domain.contracts import DOMAIN_CONTRACTS, DOMAIN_EVALUATION
from ...domain.extract import DomainExtractor
from ...domain.ontology import ontology_document
from ...domain.reasoning import DomainReasoner
from ...domain.validation import DomainDataset, verify_domain_code
from ...integration import get_bridge
from ...kg import KnowledgeGraph
from ...utils import read_json

router = APIRouter(prefix="/api/v2")
STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="论文/仓库原文")
    source_id: str = ""
    locator: str = ""
    title: str = ""
    llm_output: Optional[Any] = Field(default=None, description="可选：LLM 原始 JSON，做证据锚定后处理")
    code_source: str = Field(default="", description="可选：同仓库的 Python 源码，用于代码反推")


class RerankRequest(BaseModel):
    query: str
    task_family: str = ""
    entity: str = ""
    modality: str = ""
    n_samples: int = 0
    cpu_only: bool = True
    top_k: int = 8


class ChainRequest(BaseModel):
    start_id: str
    goal_task_family: str = ""
    max_depth: int = 4
    beam: int = 4


class GapsRequest(BaseModel):
    needs: List[str] = Field(default_factory=list)
    required_families: Dict[str, str] = Field(default_factory=dict)


class LadderRequest(BaseModel):
    baseline_subset: float
    candidate_subset: float
    baseline_full: float
    candidate_full: float
    direction: str = "maximize"
    metric: str = "roc_auc"
    problem_id: str = ""
    engineer_rounds: int = 0
    min_gain: float = 0.0


class AuditRequest(BaseModel):
    method_text: str
    code_text: str
    protocol_text: str = "held-out test split, fixed seed 42"


class ValidateRequest(BaseModel):
    code: str
    task_type: str = "protein_sequence_regression"
    method_text: str = ""
    baseline_value: Optional[float] = None
    n_train: int = 200
    n_test: int = 80
    seed: int = 42


# ---------------------------------------------------------------------------
# Schema / 本体
# ---------------------------------------------------------------------------
@router.get("/schema")
def get_schema() -> Dict[str, Any]:
    """返回蛋白质/分子能力 JSON Schema 与受控词表。"""
    return {"schema_version": "protein_v1", "json_schema": json_schema(),
            "ontology": ontology_document()}


@router.get("/schema/owl", response_class=HTMLResponse)
def get_owl() -> HTMLResponse:
    """返回轻量 OWL 本体（Turtle，text/plain）。"""
    return HTMLResponse(owl_turtle(), media_type="text/turtle")


@router.get("/contracts")
def get_contracts() -> Dict[str, Any]:
    return {"count": len(DOMAIN_CONTRACTS),
            "items": {k: {"task_type": c.task_type, "title": c.title,
                          "required_functions": c.required_functions,
                          "primary_metric": c.primary_metric,
                          "metric_threshold": c.metric_threshold,
                          "evaluation": DOMAIN_EVALUATION.get(k)}
                      for k, c in DOMAIN_CONTRACTS.items()}}


@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "api": "v2", "bridge": get_bridge().status()["backend"]}


# ---------------------------------------------------------------------------
# 抽取
# ---------------------------------------------------------------------------
@router.post("/extract")
def extract(req: ExtractRequest) -> Dict[str, Any]:
    ext = DomainExtractor()
    if req.llm_output is not None:
        signals = ext.extract_from_code(req.code_source) if req.code_source.strip() else None
        result = ext.refine_llm_output(req.llm_output, req.text,
                                       source_id=req.source_id, locator=req.locator,
                                       code_signals=signals)
    else:
        result = ext.extract(req.text, source_id=req.source_id,
                             locator=req.locator, title=req.title)
        if req.code_source.strip():
            signals, cap = ext.capability_from_code(req.code_source,
                                                    source_id=req.source_id or "code")
            merged = ext.merge([result, type(result)(
                source_id=signals.source_id, capabilities=[cap])])
            result.capabilities = merged.capabilities
            result.diagnostics += [{
                "level": "info", "code": "code_signals_merged",
                "message": f"代码反推 {len(signals.functions)} 个公开函数、"
                           f"{len(signals.imports)} 个依赖"}]
    return {"summary": result.summary(), **result.to_dict()}


# ---------------------------------------------------------------------------
# 推理
# ---------------------------------------------------------------------------
def _load_reasoner() -> DomainReasoner:
    return DomainReasoner(graph=KnowledgeGraph().load())


@router.post("/reason/rerank")
def rerank(req: RerankRequest) -> Dict[str, Any]:
    graph = KnowledgeGraph().load()
    reasoner = DomainReasoner(graph=graph)
    hits = graph.search_capabilities(req.query, top_k=max(req.top_k * 3, 12))
    context = {"task_family": req.task_family, "entity": req.entity,
               "modality": req.modality, "n_samples": req.n_samples,
               "cpu_only": req.cpu_only}
    return {"query": req.query, "n_candidates": len(hits),
            "ranked": reasoner.rerank(req.query, hits, top_k=req.top_k, context=context)}


@router.post("/reason/chain")
def chain(req: ChainRequest) -> Dict[str, Any]:
    reasoner = _load_reasoner()
    return {"start_id": req.start_id,
            "chains": reasoner.compose_chains(req.start_id,
                                              goal_task_family=req.goal_task_family,
                                              max_depth=min(req.max_depth, 6),
                                              beam=min(req.beam, 8)),
            "n_capabilities": len(reasoner.views)}


@router.post("/reason/gaps")
def gaps(req: GapsRequest) -> Dict[str, Any]:
    reasoner = _load_reasoner()
    return reasoner.infer_gaps(req.needs, required_families=req.required_families)


@router.get("/reason/explain/{cap_id}")
def explain(cap_id: str) -> Dict[str, Any]:
    reasoner = _load_reasoner()
    if cap_id not in reasoner.views:
        raise HTTPException(404, "能力不存在")
    return {"id": cap_id, "explanation": reasoner.explain(cap_id)}


# ---------------------------------------------------------------------------
# SciForge 机制
# ---------------------------------------------------------------------------
@router.get("/sciforge/status")
def sciforge_status() -> Dict[str, Any]:
    return get_bridge().status()


@router.get("/sciforge/phasegraph")
def sciforge_phasegraph() -> Dict[str, Any]:
    return get_bridge().phasegraph()


@router.post("/sciforge/ladder")
def sciforge_ladder(req: LadderRequest) -> Dict[str, Any]:
    return get_bridge().evaluate_candidate(
        baseline_subset=req.baseline_subset, candidate_subset=req.candidate_subset,
        baseline_full=req.baseline_full, candidate_full=req.candidate_full,
        direction=req.direction, metric=req.metric, problem_id=req.problem_id,
        engineer_rounds=req.engineer_rounds, min_gain=req.min_gain)


@router.post("/sciforge/audit")
def sciforge_audit(req: AuditRequest) -> Dict[str, Any]:
    return get_bridge().audit_experiment(method_text=req.method_text,
                                         code_text=req.code_text,
                                         protocol_text=req.protocol_text)


# ---------------------------------------------------------------------------
# v2 验证
# ---------------------------------------------------------------------------
@router.post("/validate")
def validate(req: ValidateRequest) -> Dict[str, Any]:
    if req.task_type not in DOMAIN_CONTRACTS:
        raise HTTPException(400, f"未知任务类型，可选：{sorted(DOMAIN_CONTRACTS)}")
    dataset = DomainDataset.synthetic(req.task_type,
                                      n_train=max(20, min(req.n_train, 2000)),
                                      n_test=max(10, min(req.n_test, 1000)),
                                      seed=req.seed)
    return verify_domain_code(req.code, req.task_type, dataset=dataset,
                              method_text=req.method_text,
                              baseline_value=req.baseline_value)


# ---------------------------------------------------------------------------
# 领域工作台页面
# ---------------------------------------------------------------------------
@router.get("/domain", response_class=HTMLResponse, include_in_schema=False)
def domain_page() -> HTMLResponse:
    # 另在 app 层注册无前缀的 /domain 入口；此处保留为 API 前缀下的别名
    path = STATIC_DIR / "domain.html"
    if not path.exists():
        raise HTTPException(500, "领域工作台页面缺失")
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 版本无关的显式挂载
# ---------------------------------------------------------------------------
# 不用 app.include_router：实测 FastAPI 0.162.x 在该用法下不会挂载带 prefix 的
# APIRouter 路由（最小复现同样失败），而 0.135.x 正常。为了在用户机器上无论装到
# 哪个版本都保持一致，这里显式把 endpoint 注册到 app。
_V2_ROUTES = [
    ("/api/v2/schema", get_schema, "GET", True),
    ("/api/v2/schema/owl", get_owl, "GET", True),
    ("/api/v2/contracts", get_contracts, "GET", True),
    ("/api/v2/health", health, "GET", True),
    ("/api/v2/extract", extract, "POST", True),
    ("/api/v2/reason/rerank", rerank, "POST", True),
    ("/api/v2/reason/chain", chain, "POST", True),
    ("/api/v2/reason/gaps", gaps, "POST", True),
    ("/api/v2/reason/explain/{cap_id}", explain, "GET", True),
    ("/api/v2/sciforge/status", sciforge_status, "GET", True),
    ("/api/v2/sciforge/phasegraph", sciforge_phasegraph, "GET", True),
    ("/api/v2/sciforge/ladder", sciforge_ladder, "POST", True),
    ("/api/v2/sciforge/audit", sciforge_audit, "POST", True),
    ("/api/v2/validate", validate, "POST", True),
    ("/api/v2/domain", domain_page, "GET", False),
]


def register(app) -> int:
    """把 v2 路由注册到 FastAPI app，返回注册数量。"""
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V2_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
