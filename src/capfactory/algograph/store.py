"""AlgoGraph 图容器：幂等写入、内存邻接索引、JSON/GraphML 落盘、粒度检索.

存储选择遵循"零新增重依赖"：JSON 单文件 + 内存邻接索引
（借鉴 code-graph-rag ``graph_loader.py`` 的 by_id/by_label/outgoing/incoming），
需要时再投影到主 ``KnowledgeGraph`` 或导出 GraphML / Neo4j CSV。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..kg.retrieval import tokenize
from ..utils import now_iso
from .schema import Edge, Node, make_qn, validate_graph

# 只把这些类型投影到主能力图谱，块级节点数量大，保留在 AlgoGraph 子图里
PROJECTABLE_TYPES = ("func_name", "implementation", "causal_node",
                     "paper_module", "capability_version")


class AlgoGraph:
    """一张细粒度算法图（一个 CapabilityVersion 对应一张）。"""

    def __init__(self, graph_id: str = ""):
        self.graph_id = graph_id or make_qn("algograph", now_iso())
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._edge_keys: set = set()
        self._out: Optional[Dict[str, List[Edge]]] = None
        self._in: Optional[Dict[str, List[Edge]]] = None
        self.meta: Dict[str, Any] = {"created_at": now_iso(), "schema_version": "algograph_v1"}

    # -- 写入 -------------------------------------------------------------
    def add_node(self, node: Node) -> Node:
        if node.qn in self.nodes:
            self.nodes[node.qn].attrs.update(node.attrs)
            self.nodes[node.qn].label = node.label or self.nodes[node.qn].label
        else:
            self.nodes[node.qn] = node
        self._out = self._in = None
        return self.nodes[node.qn]

    def node(self, qn: str, ntype: str, label: str = "", **attrs: Any) -> Node:
        return self.add_node(Node(qn=qn, type=ntype, label=label, attrs=dict(attrs)))

    def add_edge(self, source: str, target: str, rel: str, **attrs: Any) -> bool:
        """幂等写入；返回是否新增。站点级边用 (line,col) 区分。"""
        if source not in self.nodes or target not in self.nodes:
            return False
        edge = Edge(source=source, target=target, type=rel, attrs=dict(attrs))
        key = edge.key()
        if key in self._edge_keys:
            return False
        self._edge_keys.add(key)
        self.edges.append(edge)
        self._out = self._in = None
        return True

    # -- 索引与查询 -------------------------------------------------------
    def _index(self) -> None:
        if self._out is not None:
            return
        out: Dict[str, List[Edge]] = defaultdict(list)
        inc: Dict[str, List[Edge]] = defaultdict(list)
        for e in self.edges:
            out[e.source].append(e)
            inc[e.target].append(e)
        self._out, self._in = dict(out), dict(inc)

    def outgoing(self, qn: str, rel: str = "") -> List[Edge]:
        self._index()
        return [e for e in (self._out or {}).get(qn, []) if not rel or e.type == rel]

    def incoming(self, qn: str, rel: str = "") -> List[Edge]:
        self._index()
        return [e for e in (self._in or {}).get(qn, []) if not rel or e.type == rel]

    def by_type(self, ntype: str) -> List[Node]:
        return [n for n in self.nodes.values() if n.type == ntype]

    def neighbours(self, qn: str, hops: int = 1, rel: str = "") -> List[Tuple[str, int]]:
        self._index()
        seen, queue, out = {qn: 0}, deque([(qn, 0)]), []
        while queue:
            cur, d = queue.popleft()
            if d >= hops:
                continue
            for e in (self._out or {}).get(cur, []) + (self._in or {}).get(cur, []):
                if rel and e.type != rel:
                    continue
                nxt = e.target if e.source == cur else e.source
                if nxt in seen:
                    continue
                seen[nxt] = d + 1
                out.append((nxt, d + 1))
                queue.append((nxt, d + 1))
        return out

    def reachability(self, start: str, rel: str = "CALLS",
                     max_hops: int = 8) -> Dict[str, Any]:
        """影响面/可达性查询；**必须同时报告 unresolved_count**（Axiom 不变量 4）。"""
        self._index()
        seen, queue = {start}, deque([(start, 0)])
        while queue:
            cur, d = queue.popleft()
            if d >= max_hops:
                continue
            for e in (self._out or {}).get(cur, []):
                if rel and e.type != rel:
                    continue
                if e.target not in seen:
                    seen.add(e.target)
                    queue.append((e.target, d + 1))
        unresolved = [n for n in self.nodes.values() if n.type == "unresolved_site"]
        return {
            "start": start, "reachable": sorted(seen - {start}),
            "n_reachable": len(seen) - 1,
            "unresolved_count": len(unresolved),
            "unresolved_sites": [n.get("callee_written") for n in unresolved[:20]],
            "note": "unresolved_count>0 时可达性结论不完整（未解析调用可能指向外部目标）",
        }

    # -- 粒度检索（PKG 的广度 ↔ 精确性权衡） -------------------------------
    def retrieve(self, query: str, *, granularity: str = "function",
                 context_span: bool = True, top_k: int = 5) -> List[Dict[str, Any]]:
        """按粒度检索代码单元。

        ``granularity=block`` 返回精确的语法块；``context_span=True`` 时
        同时附上其父函数完整实现，使修复 Agent 同时拿到精确性与上下文广度。
        """
        # tokenize 把 snake_case 当成单个 token，这里先拆开下划线/连字符，
        # 否则 "threshold" 命中不了 "apply_threshold"，块级检索会失效
        q_tokens = set(tokenize((query or "").replace("_", " ").replace("-", " ")))
        if not q_tokens:
            return []
        types = ("code_block",) if granularity == "block" else ("implementation", "func_name")
        scored: List[Tuple[float, Node]] = []
        for n in self.nodes.values():
            if n.type not in types:
                continue
            text = f"{n.label} {n.get('content', '')} {n.get('docstring', '')}"
            if n.type == "code_block":
                # PKG：任何块都能投影回父函数，函数名是块级检索的上下文信号
                text += " " + str(self.function_context(n.qn).get("name") or "")
            tokens = set(tokenize(text.replace("_", " ").replace("-", " ")))
            if not tokens:
                continue
            score = len(q_tokens & tokens) / (len(q_tokens | tokens) ** 0.5)
            if score > 0:
                scored.append((score, n))
        scored.sort(key=lambda x: -x[0])
        hits: List[Dict[str, Any]] = []
        for score, n in scored[:top_k]:
            item: Dict[str, Any] = {
                "qn": n.qn, "type": n.type, "label": n.label,
                "score": round(score, 4), "granularity": granularity,
                "precise": n.get("content", "")[:4000],
                "start_line": n.get("start_line"), "end_line": n.get("end_line"),
                "block_kind": n.get("block_kind", ""),
                "function_id": n.get("function_id", ""),
            }
            if context_span:
                item["function_context"] = self.function_context(n.qn)
            hits.append(item)
        return hits

    def function_context(self, qn: str) -> Dict[str, Any]:
        """由任意块/实现节点投影回父函数（PKG 缺失的反向投影）。"""
        node = self.nodes.get(qn)
        if not node:
            return {}
        fid = node.get("function_id")
        if not fid and node.type == "implementation":
            fid = qn[:-len("#impl")] if qn.endswith("#impl") else qn
        if not fid and node.type == "func_name":
            fid = qn
        if not fid:
            for e in self.outgoing(qn, "IN_FUNCTION"):
                fid = e.target
                break
        impl_qn = fid if fid.endswith("#impl") else f"{fid}#impl"
        impl = self.nodes.get(impl_qn)
        name_node = self.nodes.get(fid)
        return {
            "function_qn": fid,
            "name": (name_node.label if name_node else ""),
            "implementation": (impl.get("content", "") if impl else ""),
            "start_line": (impl.get("start_line") if impl else None),
            "end_line": (impl.get("end_line") if impl else None),
            "docstring": (name_node.get("docstring", "") if name_node else ""),
        }

    # -- 校验与统计 -------------------------------------------------------
    def validate(self) -> List[str]:
        return validate_graph(self)

    def stats(self) -> Dict[str, Any]:
        by_type = Counter(n.type for n in self.nodes.values())
        by_edge = Counter(e.type for e in self.edges)
        causal = Counter(n.get("causal_type") for n in self.by_type("causal_node"))
        levels = Counter(n.get("abstraction") for n in self.by_type("causal_node"))
        return {
            "graph_id": self.graph_id, "n_nodes": len(self.nodes), "n_edges": len(self.edges),
            "nodes_by_type": dict(by_type), "edges_by_type": dict(by_edge),
            "causal_types": dict(causal), "abstraction_levels": dict(levels),
            "unresolved_sites": by_type.get("unresolved_site", 0),
            "problems": self.validate(),
        }

    # -- 序列化 -----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {"meta": {**self.meta, "stats": self.stats()},
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [e.to_dict() for e in self.edges]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlgoGraph":
        g = cls(str((data.get("meta") or {}).get("graph_id", "")))
        g.meta = dict(data.get("meta") or {})
        for nd in data.get("nodes", []):
            g.add_node(Node.from_dict(nd))
        for ed in data.get("edges", []):
            g.add_edge(ed["source"], ed["target"], ed["type"], **(ed.get("attrs") or {}))
        return g

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "AlgoGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # -- 导出 -------------------------------------------------------------
    def to_graphml(self) -> str:
        def esc(v: Any) -> str:
            return (str(v).replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace('"', "&quot;"))
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
                 '<key id="d0" for="node" attr.name="label" attr.type="string"/>',
                 '<key id="d1" for="node" attr.name="type" attr.type="string"/>',
                 '<key id="d2" for="edge" attr.name="rel" attr.type="string"/>',
                 '<graph edgedefault="directed">']
        for n in self.nodes.values():
            lines.append(f'<node id="{esc(n.qn)}"><data key="d0">{esc(n.label)}</data>'
                         f'<data key="d1">{esc(n.type)}</data></node>')
        for i, e in enumerate(self.edges):
            lines.append(f'<edge id="e{i}" source="{esc(e.source)}" target="{esc(e.target)}">'
                         f'<data key="d2">{esc(e.type)}</data></edge>')
        lines += ["</graph>", "</graphml>"]
        return "\n".join(lines)

    def to_neo4j_csv(self) -> Tuple[str, str]:
        import csv
        import io

        def dump(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(header)
            w.writerows(rows)
            return buf.getvalue()

        nodes = dump([":ID", "label", "type", "layer", "granularity"],
                     [(n.qn, n.label, n.type, n.layer, n.granularity)
                      for n in self.nodes.values()])
        edges = dump([":START_ID", ":END_ID", ":TYPE", "site"],
                     [(e.source, e.target, e.type,
                       e.attrs.get("site", "")) for e in self.edges])
        return nodes, edges

    def project_to_main_graph(self, kg: Any) -> Dict[str, int]:
        """把函数级/因果/论文模块节点投影进主 ``KnowledgeGraph``（块级不投影）。"""
        added = 0
        for n in self.nodes.values():
            if n.type not in PROJECTABLE_TYPES:
                continue
            before = len(kg.nodes)
            kg.add_node(n.qn, n.type, n.label,
                        **{k: v for k, v in n.attrs.items()
                           if k not in ("content",) and not isinstance(v, (list, dict))},
                        source_id=n.source_id, confidence=n.confidence)
            if len(kg.nodes) > before:
                added += 1
        edges_added = 0
        for e in self.edges:
            if e.source in kg.nodes and e.target in kg.nodes:
                before = len(kg.edges)
                kg.add_edge(e.source, e.target, e.type,
                            weight=float(e.attrs.get("weight", 1.0)))
                edges_added += len(kg.edges) - before
        return {"nodes_added": added, "edges_added": edges_added,
                "note": "code_block 节点保留在 AlgoGraph 子图，避免主图爆炸"}
