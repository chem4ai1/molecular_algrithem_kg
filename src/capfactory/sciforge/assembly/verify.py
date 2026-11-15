"""A5 Verify：悬空边 / TBox 违反 / 三档门。"""
from __future__ import annotations
from typing import Any, Dict, List


def verify(graph: Any, manifest: Any, a4: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[Dict[str, Any]] = list(a4.get("violations") or [])
    # 悬空边：任一端不在图内
    dangling = [{"kind": "dangling", "src": a.source,
                 "rel": a.relation, "dst": a.target}
                for a in graph.assertions
                if a.source not in graph.nodes or a.target not in graph.nodes]
    violations += dangling[:50]
    a5 = {"n_dangling_edges": len(dangling),
          "n_violations": len(violations),
          "must_have_violations": 0,
          "n_assertions": len(graph.assertions),
          "n_nodes": len(graph.nodes)}
    manifest.violations = violations
    manifest.warnings = list(a4.get("warnings") or [])
    if not manifest.a1.get("complete", False):
        manifest.gate = "BLOCKED"
    elif dangling or any(v["kind"] == "domain_range" for v in violations):
        manifest.gate = "PARTIAL"
    elif manifest.warnings:
        manifest.gate = "PARTIAL"
    else:
        manifest.gate = "PASS"
    a5["gate"] = manifest.gate
    manifest.a5 = a5
    return a5
