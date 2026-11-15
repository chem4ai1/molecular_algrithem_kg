"""v3 Web API：细粒度算法图的构建、检索、对齐、修复定位与导出.

挂载方式与 v2 一致：用 ``register(app)`` 显式注册，避免不同 FastAPI 版本
``include_router(prefix=...)`` 的行为差异。

安全说明：``/api/v3/build`` **只做 AST 静态解析，绝不执行提交的源码**；
但图数据与源码会落盘，公网部署仍建议加鉴权（见 deploy/nginx.conf）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ...algograph import (
    ABSTRACTIONS, CAUSAL_TYPES, EDGE_TYPES, NODE_TYPES, AlgoGraph,
    CapabilityVersion, GroundingEngine, RepairLocator, build_capability_version,
    mermaid_to_graph, node_json_schema, to_mermaid,
)
from ...config import get_settings
from ...utils import now_iso

STATIC_DIR = Path(__file__).parent / "static"
_VERSIONS: Dict[str, CapabilityVersion] = {}

DEMO_SOURCE = '''import numpy as np

def load_peptide_fasta(path):
    seqs = []
    with open(path) as fh:
        for line in fh:
            if not line.startswith(">"):
                seqs.append(line.strip())
    return seqs

def encode_sequence(sequences):
    AA = "ACDEFGHIKLMNPQRSTVWY"
    out = np.zeros((len(sequences), len(AA)))
    for i, s in enumerate(sequences):
        for ch in s:
            if ch in AA:
                out[i, AA.index(ch)] += 1
    return out

def model_forward(features):
    weights = np.ones(features.shape[1]) * 0.1
    return features @ weights

def apply_threshold(scores, threshold=0.5):
    labels = []
    for s in scores:
        if s >= threshold:
            labels.append(1)
        else:
            labels.append(0)
    return labels

def format_output(labels):
    return [{"toxic": bool(x)} for x in labels]

def predict_toxicity(path):
    seqs = load_peptide_fasta(path)
    feats = encode_sequence(seqs)
    scores = model_forward(feats)
    labels = apply_threshold(scores)
    return format_output(labels)
'''

DEMO_PAPERS = [
    {"title": "Sequence loading", "locator": "Sec.3.1", "source_id": "toxipep_paper",
     "text": "Peptide sequences are loaded from FASTA files and cleaned before encoding.",
     "quote": "Peptide sequences are loaded from FASTA files", "anchored": True},
    {"title": "Amino-acid composition encoding", "locator": "Sec.3.2", "source_id": "toxipep_paper",
     "text": "Each sequence is encoded by amino-acid composition descriptors into a numeric feature matrix.",
     "quote": "Each sequence is encoded by amino-acid composition descriptors", "anchored": True},
    {"title": "Toxicity decision gate", "locator": "Sec.3.3", "source_id": "toxipep_paper",
     "text": "A threshold of 0.5 is applied to the predicted toxicity probability to decide the label.",
     "quote": "A threshold of 0.5 is applied", "anchored": True},
    {"title": "RAPiDock docking refinement", "locator": "Sec.3.4", "source_id": "toxipep_paper",
     "text": "Candidate binders are refined by molecular docking to estimate binding affinity.",
     "quote": "Candidate binders are refined by molecular docking", "anchored": True},
    # 论文宣称但示例代码中没有对应实现 → 最高优先的复现缺口（parameter 类）
    {"title": "Half-life parameter config", "locator": "Sec.4.2", "source_id": "toxipep_paper",
     "text": "The parameter config for peptide half-life is estimated from stability assays. "
             "A learned parameter is reused as a fixed input at inference.",
     "quote": "The parameter config for peptide half-life", "anchored": True},
]


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class BuildRequest(BaseModel):
    capability_id: str = "cap_toxicity_toxipep"
    sources: Dict[str, str] = Field(default_factory=dict)
    source: str = ""
    code_path: str = ""
    paper_modules: List[Dict[str, Any]] = Field(default_factory=list)
    metric_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    include_blocks: bool = True
    version_id: str = ""
    use_demo: bool = False


class RetrieveRequest(BaseModel):
    query: str
    granularity: str = "function"        # function | block
    context_span: bool = True
    top_k: int = 5


class RepairRequest(BaseModel):
    metric: str = "roc_auc"
    value: float = 0.0
    threshold: float = 0.6
    direction: str = "higher"
    line: Optional[int] = None
    traceback: str = ""


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------
def _store_dir() -> Path:
    d = get_settings().path("storage") / "algograph"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_version(cv: CapabilityVersion) -> None:
    _VERSIONS[cv.version_id] = cv
    cv.save(_store_dir() / f"{cv.version_id.replace('/', '_')}.json")


def _all_versions() -> Dict[str, CapabilityVersion]:
    for p in sorted(_store_dir().glob("*.json")):
        if p.stem in _VERSIONS or p.name.endswith(".graph.json"):
            continue
        try:
            cv = CapabilityVersion.from_dict(json.loads(p.read_text(encoding="utf-8")))
            _VERSIONS[cv.version_id] = cv
        except Exception:  # noqa: BLE001 - 损坏的旧文件不应阻断列表
            continue
    return _VERSIONS


def _get_version(vid: str) -> CapabilityVersion:
    versions = _all_versions()
    if vid not in versions:
        raise HTTPException(404, f"CapabilityVersion {vid} 不存在")
    return versions[vid]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def health() -> Dict[str, Any]:
    return {"ok": True, "api": "v3", "n_versions": len(_all_versions()),
            "ts": now_iso()}


def schema() -> Dict[str, Any]:
    return {"schema_version": "algograph_v1", "node_types": list(NODE_TYPES),
            "edge_types": list(EDGE_TYPES), "causal_types": list(CAUSAL_TYPES),
            "abstractions": list(ABSTRACTIONS),
            "json_schema": node_json_schema(),
            "layers": {
                "structural": "PKG func_name/implementation/code_block + 站点级 CALLS/FLOWS_TO",
                "causal": "七类本体 micro/meso/macro 构造式层级",
                "alignment": "论文↔代码 Grounding + TestCase/MetricBinding",
            }}


def demo() -> Dict[str, Any]:
    return {"capability_id": "cap_toxicity_toxipep", "source": DEMO_SOURCE,
            "paper_modules": DEMO_PAPERS,
            "metric_bindings": [{"metric_name": "roc_auc", "role": "gate", "threshold": 0.6}],
            "test_cases": [{"id": "tc_gate", "assertion": "roc_auc >= 0.6",
                            "metric_name": "roc_auc", "role": "gate"}]}


def build(req: BuildRequest) -> Dict[str, Any]:
    sources = dict(req.sources)
    papers = list(req.paper_modules)
    bindings = list(req.metric_bindings)
    cases = list(req.test_cases)
    if req.use_demo or (not sources and not req.source):
        d = demo()
        sources = {"toxipep": d["source"]}
        papers = d["paper_modules"]
        bindings = d["metric_bindings"]
        cases = d["test_cases"]
    elif req.source and not sources:
        sources = {Path(req.code_path).stem if req.code_path else "module": req.source}
    if not sources:
        raise HTTPException(400, "缺少源码（sources 或 source 或 use_demo）")
    cv = build_capability_version(
        req.capability_id, sources, code_path=req.code_path,
        version_id=req.version_id, paper_modules=papers,
        metric_bindings=bindings, test_cases=cases,
        include_blocks=req.include_blocks)
    _save_version(cv)
    return {"version_id": cv.version_id, "stats": cv.stats(),
            "grounding_summary": cv.grounding.get("summary", {}),
            "validation_problems": cv.graph.validate(),
            "notes": cv.notes}


def list_versions() -> Dict[str, Any]:
    items = []
    for vid, cv in _all_versions().items():
        s = cv.stats()
        items.append({"version_id": vid, "capability_id": cv.capability_id,
                      "n_nodes": s["n_nodes"], "n_edges": s["n_edges"],
                      "grounding_coverage": s["grounding_coverage"],
                      "created_at": cv.created_at})
    return {"count": len(items), "items": items}


def version_detail(vid: str) -> Dict[str, Any]:
    cv = _get_version(vid)
    return {"version_id": vid, "stats": cv.stats(),
            "grounding": cv.grounding, "verification": cv.verification,
            "metric_bindings": [m.__dict__ for m in cv.metric_bindings],
            "test_cases": [t.__dict__ for t in cv.test_cases],
            "notes": cv.notes, "gate_bindings": cv.gate_bindings()}


def version_graph(vid: str, type: str = "", limit: int = 500) -> Dict[str, Any]:
    g = _get_version(vid).graph
    nodes = [n.to_dict() for n in g.nodes.values() if not type or n.type == type]
    edges = [e.to_dict() for e in g.edges]
    return {"version_id": vid, "n_nodes": len(g.nodes), "n_edges": len(g.edges),
            "nodes": nodes[:limit], "edges": edges[:limit * 3],
            "truncated": len(nodes) > limit or len(edges) > limit * 3,
            "stats": g.stats()}


def mermaid(vid: str, level: str = "meso", modality: str = "code") -> PlainTextResponse:
    if level not in ABSTRACTIONS:
        raise HTTPException(400, f"level 必须是 {list(ABSTRACTIONS)}")
    return PlainTextResponse(to_mermaid(_get_version(vid).graph,
                                        level=level, modality=modality),
                             media_type="text/plain")


def grounding(vid: str) -> Dict[str, Any]:
    cv = _get_version(vid)
    return {"version_id": vid, **cv.grounding}


def gaps(vid: str) -> Dict[str, Any]:
    cv = _get_version(vid)
    return {"version_id": vid, **cv.modules_and_gaps()}


def reachability(vid: str, qn: str = Query(..., description="起始节点 qn")) -> Dict[str, Any]:
    g = _get_version(vid).graph
    if qn not in g.nodes:
        raise HTTPException(404, f"节点 {qn} 不存在")
    return {"version_id": vid, **g.reachability(qn)}


def export(vid: str, format: str = "json"):
    cv = _get_version(vid)
    if format == "graphml":
        return PlainTextResponse(cv.graph.to_graphml(), media_type="application/xml")
    if format == "json":
        return PlainTextResponse(json.dumps(cv.to_dict(), ensure_ascii=False, indent=2),
                                 media_type="application/json")
    raise HTTPException(400, "format 仅支持 json / graphml")


def retrieve(vid: str, req: RetrieveRequest) -> Dict[str, Any]:
    g = _get_version(vid).graph
    if req.granularity not in ("function", "block"):
        raise HTTPException(400, "granularity 必须是 function 或 block")
    return {"version_id": vid, "query": req.query,
            "hits": g.retrieve(req.query, granularity=req.granularity,
                               context_span=req.context_span, top_k=req.top_k)}


def repair(vid: str, req: RepairRequest) -> Dict[str, Any]:
    cv = _get_version(vid)
    return {"version_id": vid, **RepairLocator().locate(cv, req.model_dump())}


def parse_mermaid(text: str = Query(..., description="Mermaid 文本")) -> Dict[str, Any]:
    g, warnings = mermaid_to_graph(text)
    return {"n_nodes": len(g.nodes), "n_edges": len(g.edges),
            "warnings": warnings, "stats": g.stats()}


def algograph_page() -> HTMLResponse:
    path = STATIC_DIR / "algograph.html"
    if not path.exists():
        raise HTTPException(500, "细粒度算法图页面缺失")
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 版本无关的显式挂载（同 domain_api.register）
# ---------------------------------------------------------------------------
_V3_ROUTES = [
    ("/api/v3/health", health, "GET", True),
    ("/api/v3/schema", schema, "GET", True),
    ("/api/v3/demo", demo, "GET", True),
    ("/api/v3/build", build, "POST", True),
    ("/api/v3/versions", list_versions, "GET", True),
    ("/api/v3/versions/{vid}", version_detail, "GET", True),
    ("/api/v3/versions/{vid}/graph", version_graph, "GET", True),
    ("/api/v3/versions/{vid}/mermaid", mermaid, "GET", True),
    ("/api/v3/versions/{vid}/grounding", grounding, "GET", True),
    ("/api/v3/versions/{vid}/gaps", gaps, "GET", True),
    ("/api/v3/versions/{vid}/reachability", reachability, "GET", True),
    ("/api/v3/versions/{vid}/export", export, "GET", True),
    ("/api/v3/versions/{vid}/retrieve", retrieve, "POST", True),
    ("/api/v3/versions/{vid}/repair", repair, "POST", True),
    ("/api/v3/mermaid/parse", parse_mermaid, "GET", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    added = 0
    for path, endpoint, method, in_schema in _V3_ROUTES:
        if path in existing:
            continue
        app.add_api_route(path, endpoint, methods=[method],
                          include_in_schema=in_schema)
        added += 1
    return added
