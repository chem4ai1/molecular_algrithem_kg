"""边有效性验证：三值判定 + 置信度（TruthHypo KGVerifier 范式）。

VERDICT = SUPPORTED | REFUTED | INSUFFICIENT
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EdgeVerdict:
    verdict: str                       # SUPPORTED / REFUTED / INSUFFICIENT
    confidence: float                  # 0..1
    supporting: List[str] = field(default_factory=list)
    contradicting: List[str] = field(default_factory=list)
    path: List[str] = field(default_factory=list)
    reason: str = ""
    verifier: str = "edge_verdict_v1"

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict, "confidence": round(self.confidence, 3),
                "supporting": self.supporting, "contradicting": self.contradicting,
                "path": self.path, "reason": self.reason, "verifier": self.verifier}


def node_rating(node: Any, *, total_papers: int = 0) -> float:
    """从 B 节点的 rating + 支持度算置信度（GraphRAG rating 迁移）。"""
    r = float(node.attrs.get("rating") or 0)
    if r <= 0:
        # 没有 rating 时用支持度代理：n_papers / total
        n = int(node.attrs.get("n_papers") or 0)
        r = min(n / max(total_papers, 1), 1.0) if total_papers else 0.5
    n = int(node.attrs.get("n_papers") or 0)
    support = min(n / max(total_papers, 1), 1.0) if total_papers else 1.0
    return max(0.0, min(r * 0.7 + support * 0.3, 1.0))


def verify_edge(
    graph: Any,
    *,
    claim_source: str,
    relation: str,
    target_id: str,
    total_papers: int = 0,
    contradiction_terms: Optional[List[str]] = None,
    min_confidence: float = 0.3,
) -> EdgeVerdict:
    """三层门：置信度 → 负证据 → 支持边（TruthHypo verify_claim 范式）。

    1. 置信度：目标 B 节点 rating × 支持度
    2. 负证据：FailureModeLibrary 中与 contradiction_terms 命中的条目
    3. 支持边：source -relation-> target 是否存在，或同类型路径可达
    """
    target = graph.nodes.get(target_id)
    if target is None:
        return EdgeVerdict("INSUFFICIENT", 0.0, reason="target node not found")

    conf = node_rating(target, total_papers=total_papers)

    # 负证据：从 FailureModeLibrary 查矛盾项
    contra = []
    for lib in graph.by_type("FailureModeLibrary"):
        for k in ("negative_results", "limitations", "findings"):
            for item in (lib.attrs.get(k) or []):
                text = str(item.get("summary") if isinstance(item, dict) else item)
                if any(term and term in text for term in (contradiction_terms or [])):
                    contra.append(text)
    if contra:
        return EdgeVerdict("REFUTED", conf, contradicting=contra[:5],
                           reason=f"{len(contra)} contradicting findings")

    # 支持边：直接边或同类型出边
    direct = [a.id for a in graph.outgoing(claim_source)
              if a.target == target_id and a.relation == relation]
    if not direct:
        same_type = [a.id for a in graph.outgoing(claim_source)
                     if a.target in graph.nodes
                     and graph.nodes[a.target].type == target.type]
        if not same_type:
            return EdgeVerdict("INSUFFICIENT", conf,
                               reason="no supporting edge of same type")
        direct = same_type

    if conf < min_confidence:
        return EdgeVerdict("INSUFFICIENT", conf, supporting=direct[:5],
                           reason=f"confidence {conf:.2f} < {min_confidence}")

    return EdgeVerdict("SUPPORTED", conf, supporting=direct[:5],
                       reason=f"rating+support ok, {len(direct)} edge(s)")
