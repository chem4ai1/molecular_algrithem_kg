"""POGraph ⇄ networkx 适配层。

现状：本项目图谱是自研 ``POGraph``（dataclass + dict/list），不依赖图数据库；
本模块把它映射成 ``networkx.MultiDiGraph``，用于图算法、GraphML/GEXF 导出、
与外部图生态互通。

设计要点：
  * 用 ``MultiDiGraph``：同一对节点可有多条不同关系（EVALUATED_ON + RELATED_TO）
  * 属性值中的 list/dict 统一转 JSON 字符串（GraphML 只支持标量）
  * 转换是单向快照，不反向持有引用；``from_networkx`` 可还原
"""
from __future__ import annotations
import json
from typing import Any, Dict, Optional

import networkx as nx


def _scalar(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


def _node_attrs(n: Any) -> Dict[str, Any]:
    a = {"type": n.type, "label": n.label}
    a.update({k: v for k, v in n.attrs.items() if k != "label"})
    a["attribution"] = getattr(n, "attribution", "")
    a["source_version"] = getattr(n, "source_version", "")
    if getattr(n, "evidence_ids", None):
        a["evidence_ids"] = list(n.evidence_ids)
    return {k: _scalar(v) for k, v in a.items()}


def to_networkx(graph: Any, *, layer: Optional[str] = None,
                with_meta: bool = True) -> nx.MultiDiGraph:
    """POGraph → nx.MultiDiGraph（快照，不复制引用）。"""
    mg = nx.MultiDiGraph()
    if with_meta:
        mg.graph.update({"graph_id": getattr(graph, "graph_id", ""),
                         "schema_version": (graph.meta or {}).get(
                             "schema_version", ""),
                         "source": (graph.meta or {}).get("source", "")})
    for nid, n in graph.nodes.items():
        if layer and n.attrs.get("layer") != layer:
            continue
        mg.add_node(nid, **_node_attrs(n))
    for a in graph.assertions:
        if a.source not in mg or a.target not in mg:
            continue
        props = dict(a.properties or {})
        mg.add_edge(a.source, a.target, key=a.id or None,
                    relation=a.relation, edge_id=a.id,
                    attribution=a.attribution,
                    evidence_ids=_scalar(list(a.evidence_ids or [])),
                    lay=(props.get("layer") or ""),
                    task=(props.get("task") or ""),
                    **{("p_" + k): _scalar(v) for k, v in props.items()
                       if k not in ("layer", "task")})
    return mg


def from_networkx(mg: nx.MultiDiGraph) -> Any:
    """nx.MultiDiGraph → POGraph（类型/关系/属性可还原）。"""
    from .store import POGraph
    g = POGraph(mg.graph.get("graph_id", "") if mg.graph else "")
    for nid, d in mg.nodes(data=True):
        attrs = {k: v for k, v in d.items() if k not in ("type", "label")}
        g.node(nid, d.get("type", "Unknown"), d.get("label", nid), **attrs)
    for s, t, _key, d in mg.edges(keys=True, data=True):
        props = {k[2:]: v for k, v in d.items() if k.startswith("p_")}
        if d.get("lay"):
            props["layer"] = d["lay"]
        if d.get("task"):
            props["task"] = d["task"]
        g.assert_rel(s, t, d.get("relation", "RELATED_TO"),
                     assertion_id=d.get("edge_id", ""), **props)
    return g


def stats(graph: Any) -> Dict[str, Any]:
    """基于 networkx 的图统计（连通性 / 度分布 / 中心性）。"""
    mg = to_networkx(graph)
    n, e = mg.number_of_nodes(), mg.number_of_edges()
    types: Dict[str, int] = {}
    rels: Dict[str, int] = {}
    for _, d in mg.nodes(data=True):
        t = d.get("type", "?")
        types[t] = types.get(t, 0) + 1
    for _, _, d in mg.edges(data=True):
        r = d.get("relation", "?")
        rels[r] = rels.get(r, 0) + 1
    indeg, outdeg = dict(mg.in_degree()), dict(mg.out_degree())
    top_out = sorted(outdeg.items(), key=lambda x: -x[1])[:8]
    top_in = sorted(indeg.items(), key=lambda x: -x[1])[:8]
    degs = [d for _, d in mg.degree()]
    return {
        "engine": "networkx", "graph_class": type(mg).__name__,
        "n_nodes": n, "n_edges": e,
        "types": dict(sorted(types.items(), key=lambda x: -x[1])),
        "relations": dict(sorted(rels.items(), key=lambda x: -x[1])),
        "n_weak_components": (nx.number_weakly_connected_components(mg)
                              if n else 0),
        "density": round(nx.density(mg), 8) if n > 1 else 0.0,
        "degree": {"max": max(degs) if degs else 0,
                   "avg": round(sum(degs) / max(len(degs), 1), 2),
                   "median": sorted(degs)[len(degs) // 2] if degs else 0},
        "top_out_degree": [{"id": k, "label": mg.nodes[k].get("label", ""),
                            "degree": v} for k, v in top_out],
        "top_in_degree": [{"id": k, "label": mg.nodes[k].get("label", ""),
                           "degree": v} for k, v in top_in],
        "is_dag": nx.is_directed_acyclic_graph(mg) if n else True,
    }


def neighbours(graph: Any, node_id: str, hops: int = 1) -> Dict[str, Any]:
    """多跳邻居（有向边，含跳数）。"""
    mg = to_networkx(graph)
    if node_id not in mg:
        return {"node": node_id, "found": False, "neighbours": [],
                "count": 0}
    dist = nx.single_source_shortest_path_length(mg, node_id, cutoff=hops)
    out = []
    for nid, d in sorted(dist.items(), key=lambda x: (x[1], x[0])):
        if nid == node_id:
            continue
        x = mg.nodes[nid]
        out.append({"id": nid, "label": x.get("label", ""),
                    "type": x.get("type", ""), "hops": d})
    return {"node": node_id, "found": True,
            "label": mg.nodes[node_id].get("label", ""),
            "neighbours": out[:500], "count": len(out)}


def shortest_path(graph: Any, src: str, dst: str) -> Dict[str, Any]:
    mg = to_networkx(graph)
    if src not in mg or dst not in mg:
        return {"found": False, "reason": "node_missing"}
    try:
        path = nx.shortest_path(mg, src, dst)
    except nx.NetworkXNoPath:
        return {"found": False, "reason": "no_path"}
    edges = []
    for a, b in zip(path, path[1:]):
        d = mg.get_edge_data(a, b) or {}
        rel = next(iter(d.values()))["relation"] if d else ""
        edges.append({"from": a, "to": b, "relation": rel})
    return {"found": True, "hops": len(path) - 1, "path": path,
            "edges": edges}


def export(graph: Any, path: str, fmt: str = "graphml") -> Dict[str, Any]:
    """导出 graphml / gexf / json。"""
    import os
    mg = to_networkx(graph)
    fmt = (fmt or "graphml").lower()
    if fmt == "graphml":
        nx.write_graphml(mg, path)
    elif fmt == "gexf":
        nx.write_gexf(mg, path)
    elif fmt == "json":
        from networkx.readwrite import json_graph
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json_graph.node_link_data(mg, edges="edges"), f,
                      ensure_ascii=False)
    else:
        raise ValueError("fmt 只支持 graphml / gexf / json")
    return {"path": path, "format": fmt,
            "bytes": os.path.getsize(path),
            "n_nodes": mg.number_of_nodes(),
            "n_edges": mg.number_of_edges()}
