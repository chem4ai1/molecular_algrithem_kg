"""能力覆盖度分析：把「企业需求」与「已挖掘能力」对齐，定位研究缺口。

覆盖度评分 = 检索相关度 × 成熟度系数
- 相关度：需求文本与能力文本的混合检索得分（0-1）
- 成熟度：0（仅概念）→ 1（已复刻并通过验证）
=> 只有「相关且已验证」才算真正覆盖，避免"文献里提过"式的虚假覆盖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..kg import KnowledgeGraph

logger = logging.getLogger(__name__)

COVERED_THRESHOLD = 0.52
PARTIAL_THRESHOLD = 0.32
# 领域通用词不作为区分依据（几乎出现在所有能力文本中）
STOPWORDS = {
    "peptide", "peptides", "protein", "prediction", "predict", "predictor", "model",
    "based", "using", "with", "and", "for", "the", "from", "method", "approach",
    "analysis", "data", "learning", "deep", "neural", "network", "level", "new",
}


def _content_tokens(text: str) -> set:
    import re

    toks = {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}
    return toks - STOPWORDS


@dataclass
class NeedCoverage:
    """单个需求的覆盖情况。"""

    need: str
    status: str                 # covered / partial / gap
    relevance: float
    maturity: float
    score: float
    matched: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "need": self.need, "status": self.status,
            "relevance": round(self.relevance, 3), "maturity": round(self.maturity, 3),
            "score": round(self.score, 3), "matched": self.matched,
        }


class CoverageAnalyzer:
    """需求—能力覆盖矩阵。"""

    def __init__(self, graph: KnowledgeGraph, settings: Optional[Settings] = None):
        self.graph = graph
        self.settings = settings or get_settings()

    def analyze(self, needs: Optional[List[str]] = None, top_k: int = 3) -> Dict[str, Any]:
        needs = needs or self.settings.domain.get("needs", [])
        aliases: Dict[str, str] = self.settings.domain.get("need_aliases", {}) or {}
        results: List[NeedCoverage] = []
        for need in needs:
            # 中文需求 → 英文检索式（文献能力描述以英文为主）
            query = f"{need} {aliases.get(need, '')}".strip()
            q_tokens = _content_tokens(query)
            hits = self.graph.search_capabilities(query, top_k=top_k)
            matched = []
            for h in hits:
                node = self.graph.get(h.node_id) or {}
                attrs = node.get("attrs", {})
                maturity = float(attrs.get("maturity", 0) or 0)
                # 相关度 = 检索得分 × 任务词面重合度（防止"都有 peptide 所以都算覆盖"）
                cap_text = " ".join(filter(None, [
                    node.get("label", ""), attrs.get("task", ""),
                    " ".join(attrs.get("tags") or []), (attrs.get("summary") or "")[:200],
                ]))
                c_tokens = _content_tokens(cap_text)
                overlap = len(q_tokens & c_tokens) / max(len(q_tokens), 1)
                retrieval = min(1.0, h.score / 0.9)
                relevance = round(0.55 * retrieval + 0.45 * min(1.0, overlap * 1.8), 4)
                score = relevance * (0.35 + 0.65 * maturity)
                matched.append({
                    "capability_id": h.node_id,
                    "name": node.get("label", ""),
                    "relevance": round(relevance, 3),
                    "retrieval": round(retrieval, 3),
                    "overlap": round(overlap, 3),
                    "maturity": round(maturity, 3),
                    "verified": bool(attrs.get("verification", {}).get("passed")),
                    "score": round(score, 3),
                })
            matched.sort(key=lambda m: -m["score"])
            top = matched[0] if matched else {"relevance": 0.0, "maturity": 0.0, "score": 0.0}
            score = top["score"]
            if score >= COVERED_THRESHOLD:
                status = "covered"
            elif score >= PARTIAL_THRESHOLD or (top["relevance"] >= 0.6 and top["maturity"] < 0.3):
                # 有高相关候选但尚未复刻验证 → 部分覆盖（可快速补齐）
                status = "partial"
            else:
                status = "gap"
            # 缺口不展示"最相近"能力，避免误导
            visible = [m for m in matched if m["score"] >= PARTIAL_THRESHOLD] if status != "gap" else []
            results.append(NeedCoverage(
                need=need, status=status,
                relevance=float(top["relevance"]), maturity=float(top["maturity"]),
                score=float(score), matched=visible,
            ))
        summary = {
            "covered": sum(1 for r in results if r.status == "covered"),
            "partial": sum(1 for r in results if r.status == "partial"),
            "gap": sum(1 for r in results if r.status == "gap"),
            "coverage_rate": round(
                (sum(1 for r in results if r.status == "covered") / len(results)) if results else 0.0, 3),
        }
        logger.info("覆盖度分析完成：%s", summary)
        return {
            "needs": [r.to_dict() for r in results],
            "summary": summary,
            "thresholds": {"covered": COVERED_THRESHOLD, "partial": PARTIAL_THRESHOLD},
        }

    def task_distribution(self) -> List[Dict[str, Any]]:
        """按任务维度统计能力密度（发现"沙漠区"）。"""
        buckets: Dict[str, Dict[str, Any]] = {}
        for cap in self.graph.capabilities():
            attrs = cap.get("attrs", {})
            task = (attrs.get("task") or "unknown").strip().lower() or "unknown"
            b = buckets.setdefault(task, {"task": task, "count": 0, "verified": 0,
                                          "maturity_sum": 0.0, "examples": []})
            b["count"] += 1
            b["maturity_sum"] += float(attrs.get("maturity", 0) or 0)
            if attrs.get("verification", {}).get("passed"):
                b["verified"] += 1
            if len(b["examples"]) < 3:
                b["examples"].append(cap.get("label", ""))
        out = []
        for b in buckets.values():
            b["avg_maturity"] = round(b["maturity_sum"] / b["count"], 3) if b["count"] else 0.0
            b.pop("maturity_sum", None)
            out.append(b)
        out.sort(key=lambda x: -x["count"])
        return out
