#!/usr/bin/env python3
"""P1：用 Leiden 自动发现 B 类社区，替代预设的 5 类。

对比对象：build_factory_graph_v2.py 里预设的
  MethodLineage 6 / EvaluationNorm 4 / FailureModeLibrary 1 / VenueProfile 1
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.community_discovery import (
    detect_communities, summarize_community)

GRAPH = ROOT / "storage/sciforge/factory_knowledge_v2.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_leiden.json"
REPORT = ROOT / "storage/sciforge/leiden_communities.json"


def main():
    g = POGraph.load(str(GRAPH))
    papers = [p for p in g.by_type("Paper") if p.attrs.get("evidence_type")]
    communities = detect_communities(g, papers, resolution=1.0)
    summaries = []
    for i, c in enumerate(communities):
        s = summarize_community(c)
        nid = f"community:leiden:{i}"
        # 标准 B 节点（GraphRAG CommunityReportResponse 结构）
        g.node(nid, "EvaluationNorm", s["title"],
               title=s["title"], summary=s["summary"],
               findings=s["findings"], rating=s["rating"],
               rating_explanation=s["rating_explanation"],
               n_papers=s["n_papers"], evidence_type=s["evidence_type"],
               accepted_metrics=s["accepted_metrics"],
               community_level=s["community_level"],
               members=s["members"], discovered_by="leiden")
        # 回指成员论文（community membership 边）
        for pid in s["members"]:
            if pid in g.nodes:
                g.assert_rel(nid, pid, "DERIVED_FROM_PAPERS")
        summaries.append({"id": nid, **s})

    g.save(str(OUT))
    REPORT.write_text(json.dumps({
        "algorithm": "leiden", "resolution": 1.0,
        "n_papers": len(papers), "n_communities": len(communities),
        "communities": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"n_communities": len(communities),
                      "sizes": [c["n"] for c in communities],
                      "nodes": len(g.nodes), "assertions": len(g.assertions),
                      "out": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
