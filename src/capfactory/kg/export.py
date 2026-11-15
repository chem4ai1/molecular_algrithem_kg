"""图谱导出：GraphML / Neo4j CSV / RDF Turtle / Web 前端载荷."""

from __future__ import annotations

import csv
import html
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ..utils import ensure_dir, write_json

logger = logging.getLogger(__name__)

GRAPHML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="ntype" for="node" attr.name="type" attr.type="string"/>
  <key id="summary" for="node" attr.name="summary" attr.type="string"/>
  <key id="maturity" for="node" attr.name="maturity" attr.type="double"/>
  <key id="rel" for="edge" attr.name="relation" attr.type="string"/>
  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>
  <graph id="CapFactoryKG" edgedefault="directed">
"""


def to_graphml(graph: Any, path: Path) -> Path:
    """导出 GraphML（可被 Gephi / yEd / Cytoscape 直接打开）。"""
    path = Path(path)
    ensure_dir(path.parent)
    lines: List[str] = [GRAPHML_HEADER]
    for node in graph.nodes.values():
        attrs = node.get("attrs", {})
        lines.append(
            f'    <node id="{html.escape(node["id"])}">'
            f'<data key="label">{html.escape(str(node.get("label", "")))}</data>'
            f'<data key="ntype">{html.escape(node["type"])}</data>'
            f'<data key="summary">{html.escape(str(attrs.get("summary", ""))[:300])}</data>'
            f'<data key="maturity">{float(attrs.get("maturity", 0) or 0)}</data>'
            f"</node>"
        )
    for i, edge in enumerate(graph.edges):
        lines.append(
            f'    <edge id="e{i}" source="{html.escape(edge["source"])}" '
            f'target="{html.escape(edge["target"])}">'
            f'<data key="rel">{html.escape(edge["type"])}</data>'
            f'<data key="weight">{float(edge.get("weight", 1.0))}</data>'
            f"</edge>"
        )
    lines.append("  </graph>\n</graphml>\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("GraphML 已导出：%s", path)
    return path


def to_neo4j_csv(graph: Any, out_dir: Path) -> Dict[str, str]:
    """导出 Neo4j ``LOAD CSV`` 所需文件。"""
    out_dir = ensure_dir(Path(out_dir))
    nodes_path = out_dir / "nodes.csv"
    edges_path = out_dir / "edges.csv"
    with open(nodes_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "label", "type", "summary", "maturity", "task"])
        for node in graph.nodes.values():
            a = node.get("attrs", {})
            w.writerow([node["id"], node.get("label", ""), node["type"],
                        (a.get("summary") or "").replace("\n", " ")[:300],
                        a.get("maturity", 0), a.get("task", "")])
    with open(edges_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":END_ID", ":TYPE", "weight"])
        for e in graph.edges:
            w.writerow([e["source"], e["target"], e["type"], e.get("weight", 1.0)])
    return {"nodes": str(nodes_path), "edges": str(edges_path)}


def to_turtle(graph: Any, path: Path) -> Path:
    """导出精简 RDF Turtle（能力/论文/关系三元组）。"""
    path = Path(path)
    ensure_dir(path.parent)
    lines = [
        "@prefix cf: <https://capfactory.local/ontology#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
    ]
    for node in graph.nodes.values():
        nid = f"<https://capfactory.local/entity/{node['id']}>"
        label = json.dumps(node.get("label", ""), ensure_ascii=False)
        lines.append(f"{nid} a cf:{node['type']} ;")
        lines.append(f"  rdfs:label {label} .")
    for e in graph.edges:
        s = f"<https://capfactory.local/entity/{e['source']}>"
        o = f"<https://capfactory.local/entity/{e['target']}>"
        lines.append(f"{s} cf:{e['type'].lower()} {o} .")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Turtle 已导出：%s", path)
    return path


def to_web_payload(graph: Any, max_nodes: int = 220) -> Dict[str, Any]:
    """为前端力导向图生成精简载荷（含度数、类型、指标）。"""
    degree = {nid: 0 for nid in graph.nodes}
    for e in graph.edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    priority = {"capability": 0, "paper": 1, "task": 2, "dataset": 3,
                "metric": 4, "artifact": 5, "lesson": 6, "direction": 7}
    ordered = sorted(graph.nodes.values(),
                     key=lambda n: (priority.get(n["type"], 9), -degree.get(n["id"], 0)))
    keep = {n["id"] for n in ordered[:max_nodes]}

    nodes = []
    for n in ordered[:max_nodes]:
        a = n.get("attrs", {})
        nodes.append({
            "id": n["id"], "label": n.get("label", n["id"])[:70], "type": n["type"],
            "degree": degree.get(n["id"], 0),
            "maturity": round(float(a.get("maturity", 0) or 0), 2),
            "confidence": round(float(a.get("confidence", 0) or 0), 2),
            "task": a.get("task", ""),
            "verified": bool(a.get("verification", {}).get("passed")),
        })
    edges = [{"source": e["source"], "target": e["target"], "type": e["type"],
              "weight": e.get("weight", 1.0)}
             for e in graph.edges if e["source"] in keep and e["target"] in keep]
    return {"nodes": nodes, "edges": edges}


def export_all(graph: Any, out_dir: Path) -> Dict[str, str]:
    """一次性导出全部格式。"""
    out_dir = ensure_dir(Path(out_dir))
    files = {
        "graphml": str(to_graphml(graph, out_dir / "graph.graphml")),
        "turtle": str(to_turtle(graph, out_dir / "graph.ttl")),
    }
    neo = to_neo4j_csv(graph, out_dir)
    files.update({f"neo4j_{k}": v for k, v in neo.items()})
    files["web_payload"] = str(write_json(out_dir / "web_payload.json", to_web_payload(graph)))
    return files
