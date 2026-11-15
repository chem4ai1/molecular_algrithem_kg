"""研究方向生成：把「覆盖缺口 + 文献证据」转成可执行的研究方向建议."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..kg import KnowledgeGraph
from ..llm import AdvisorAgent
from ..schema import ResearchDirection
from ..utils import short_hash
from .gaps import CoverageAnalyzer

logger = logging.getLogger(__name__)


class ResearchAdvisor:
    """研究方向顾问：覆盖分析 → 证据汇总 → LLM 综合 → 排序."""

    def __init__(self, graph: KnowledgeGraph, agent: Optional[AdvisorAgent] = None,
                 settings: Optional[Settings] = None):
        self.graph = graph
        self.settings = settings or get_settings()
        self.agent = agent or AdvisorAgent()

    def run(self, needs: Optional[List[str]] = None) -> Dict[str, Any]:
        needs = needs or self.settings.domain.get("needs", [])
        coverage = CoverageAnalyzer(self.graph, self.settings).analyze(needs)
        landscape = self.graph.landscape(limit=40)
        papers = self._paper_digest(limit=12)

        raw = self.agent.advise(needs, landscape, papers, coverage=coverage)
        directions = self._to_directions(raw, coverage)

        # 缺口对应的方向优先：priority 加权覆盖缺口
        gap_needs = {g["need"] for g in coverage["needs"] if g["status"] == "gap"}
        for d in directions:
            if any(g in d.gap for g in gap_needs):
                d.priority = round(min(1.0, d.priority + 0.08), 3)
        directions.sort(key=lambda d: -d.priority)

        # 方向是派生数据：每次重建，避免历史方向堆积
        self.graph.remove_nodes_of_type("direction")
        for d in directions:
            self.graph.add_direction(d)
        self.graph.save()

        logger.info("生成研究方向 %d 条", len(directions))
        return {
            "coverage": coverage,
            "task_distribution": CoverageAnalyzer(self.graph, self.settings).task_distribution(),
            "directions": [d.to_dict() for d in directions],
            "evidence": papers,
        }

    # ------------------------------------------------------------------
    def _paper_digest(self, limit: int = 12) -> List[Dict[str, Any]]:
        out = []
        for p in self.graph.papers()[:limit]:
            a = p.get("attrs", {})
            out.append({
                "title": p.get("label", ""),
                "year": a.get("year"),
                "research_object": a.get("research_object", ""),
                "contributions": (a.get("contributions") or [])[:3],
                "limitations": (a.get("limitations") or [])[:2],
                "datasets": (a.get("datasets") or [])[:3],
            })
        return out

    def _to_directions(self, raw: List[Dict[str, Any]], coverage: Dict[str, Any]) -> List[ResearchDirection]:
        name_to_id = {c.get("label", "").strip().lower(): c["id"] for c in self.graph.capabilities()}
        directions: List[ResearchDirection] = []
        for i, item in enumerate(raw or []):
            title = str(item.get("title") or f"方向 {i+1}")
            supporting = []
            for name in item.get("supporting_capabilities") or []:
                cid = name_to_id.get(str(name).strip().lower())
                if cid:
                    supporting.append(cid)
            # 名称未精确匹配时，用检索补一条最相关能力，保证方向节点接入图谱
            if not supporting:
                query = f"{title} {item.get('gap', '')[:200]}"
                hits = self.graph.search_capabilities(query, top_k=1)
                if hits:
                    supporting.append(hits[0].node_id)
            try:
                priority = float(item.get("priority", 0.5))
            except (TypeError, ValueError):
                priority = 0.5
            directions.append(ResearchDirection(
                id=f"dir_{short_hash(title, str(i), length=8)}",
                title=title,
                gap=str(item.get("gap") or ""),
                rationale=str(item.get("rationale") or ""),
                supporting_capabilities=supporting,
                required_capabilities=[str(x) for x in (item.get("required_capabilities") or [])],
                experiments=[str(x) for x in (item.get("experiments") or [])],
                expected_impact=str(item.get("expected_impact") or ""),
                difficulty=str(item.get("difficulty") or "medium"),
                priority=max(0.0, min(1.0, priority)),
                references=[str(x) for x in (item.get("references") or [])],
            ))
        return directions
