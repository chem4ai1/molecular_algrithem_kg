"""AlgoGraph 统一 Schema：节点 / 边 / 受控词表 / 不变量校验.

设计取舍写在 ``docs/FINEGRAIN_ALGOGRAPH.md`` §2-3。与 PKG / CAD /
Code-Graph-RAG / AxiomCodeGraph 的字段映射见该文档。

绝不把「代码怎么切」和「切出来是什么」塞进同一张图：
``layer`` 字段把 structural / causal / alignment / verification / container 分开，
再用跨层边 ``REALIZES`` / ``GROUNDS_TO`` / ``ASSERTS`` 连接。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Tuple

LAYERS = ("container", "structural", "causal", "alignment", "verification")
GRANULARITIES = ("module", "function", "block", "paper", "causal", "version", "assertion")

# L1 结构层（PKG + 调用图）
STRUCTURAL_NODES = (
    "module", "class_unit", "func_name", "implementation", "code_block",
    "external_symbol", "unresolved_site", "data_artifact",
)
# L2 语义层（CAD）
CAUSAL_NODES = ("causal_node",)
# L3 对齐 / 证据 / 容器
OTHER_NODES = ("paper_module", "test_case", "metric_binding", "capability_version")
NODE_TYPES = tuple(STRUCTURAL_NODES + CAUSAL_NODES + OTHER_NODES)

CAUSAL_TYPES = ("input", "parameter", "mechanism", "state",
                "aggregation", "decision", "output")
PHASES = ("training", "inference", "init", "operational")
ABSTRACTIONS = ("micro", "meso", "macro")
SOURCE_MODALITIES = ("paper", "code")
RESOLUTIONS = ("exact", "method", "multi", "heuristic", "unresolved")
METRIC_ROLES = ("gate", "advisory")
BLOCK_KINDS = ("if", "for", "while", "try", "with", "match", "async_for",
               "async_with", "try_star", "else", "elif", "except", "finally",
               "case", "function", "class")
# CAD 的节点数预算（§3.2）：仅作软校验，避免规则标注产生过多/过少节点
LEVEL_BUDGET = {"micro": (1, 25), "meso": (1, 10), "macro": (1, 7)}

EDGE_TYPES = (
    "DECLARES", "HAS_IMPL", "HAS_BLOCK", "NESTS", "PROJECTS_TO", "IN_FUNCTION",
    "CALLS", "FLOWS_TO", "IMPORTS", "INHERITS", "PART_OF",
    "SPECIFIES", "REALIZES", "GROUNDS_TO", "DERIVES_FROM", "ASSERTS", "CAUSES",
)

# 跨层语义优先级：失败修复时按此顺序定位（decision / parameter 优先）
CAUSAL_PRIORITY = ("decision", "parameter", "mechanism", "state",
                   "aggregation", "input", "output")

CONCEPTUAL_GAP_TYPES = {"mechanism", "decision", "aggregation", "state"}
IMPLEMENTATION_HINTS = (
    "dtype", "cast", "alloc", "reshape", "parallel", "n_jobs", "seed", "cache",
    "buffer", "eps", "clamp", "guard", "api", "read_csv", "load_", "open",
    "format_", "save_", "dump", "serial", "device", "cuda", "memory", "copy",
    "file_io",
)


def make_qn(*parts: Any) -> str:
    """确定性主键：规范化各段后以 ``::`` 连接，避免同名冲突。"""
    def norm(x: Any) -> str:
        s = str(x).strip().replace("\\", "/")
        return re.sub(r"\s+", "_", s)
    return "::".join(norm(p) for p in parts if p not in (None, ""))


def stable_hash(*parts: Any, length: int = 10) -> str:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()[:length]


@dataclass
class Node:
    """图节点。``qn`` 是稳定主键，``attrs`` 承载类型特有字段。"""

    qn: str
    type: str
    label: str = ""
    layer: str = "structural"
    granularity: str = ""
    attrs: Dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.qn.rsplit("::", 1)[-1]
        if not self.granularity:
            self.granularity = {
                "module": "module", "class_unit": "module",
                "func_name": "function", "implementation": "function",
                "code_block": "block", "paper_module": "paper",
                "causal_node": "causal", "capability_version": "version",
                "test_case": "assertion", "metric_binding": "assertion",
            }.get(self.type, "function")
        if not self.layer:
            self.layer = ("causal" if self.type in CAUSAL_NODES else
                          "container" if self.type == "capability_version" else
                          "alignment" if self.type == "paper_module" else
                          "verification" if self.type in ("test_case", "metric_binding")
                          else "structural")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Node":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def get(self, key: str, default: Any = None) -> Any:
        return self.attrs.get(key, default)


@dataclass
class Edge:
    """图边。``key()`` 用于幂等合并（站点级边必须带站点坐标）。"""

    source: str
    target: str
    type: str
    attrs: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> Tuple[str, str, str, str]:
        site = self.attrs.get("site")
        if site is None and "line" in self.attrs and "col" in self.attrs:
            site = f'{self.attrs.get("line")}:{self.attrs.get("col")}'
        return (self.source, self.target, self.type, str(site or ""))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Edge":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def _check_known_vocab(graph: Any, problems: List[str]) -> None:
    for n in graph.nodes.values():
        if n.type not in NODE_TYPES:
            problems.append(f"未知节点类型 {n.type!r} @ {n.qn}")
        if n.type == "causal_node":
            ct = n.get("causal_type")
            if ct not in CAUSAL_TYPES:
                problems.append(f"causal_type={ct!r} 不在七类本体 @ {n.qn}")
            ph = n.get("phase")
            if ph not in PHASES:
                problems.append(f"phase={ph!r} 非法 @ {n.qn}")
            ab = n.get("abstraction")
            if ab not in ABSTRACTIONS:
                problems.append(f"abstraction={ab!r} 非法 @ {n.qn}")
        if n.type == "code_block" and n.get("block_kind") not in BLOCK_KINDS:
            problems.append(f"block_kind={n.get('block_kind')!r} 非法 @ {n.qn}")
    for e in graph.edges:
        if e.type not in EDGE_TYPES:
            problems.append(f"未知边类型 {e.type!r} @ {e.source}->{e.target}")
        if e.type == "CALLS" and e.attrs.get("resolution") not in RESOLUTIONS:
            problems.append(f"CALLS.resolution 非法 @ {e.source}->{e.target}")


def _check_structure_tree(graph: Any, problems: List[str]) -> None:
    """不变量 2/3：块构成树、无环、每个块可投影回函数。"""
    blocks = {n.qn: n for n in graph.nodes.values() if n.type == "code_block"}
    impls = {n.qn for n in graph.nodes.values() if n.type == "implementation"}
    names = {n.qn for n in graph.nodes.values() if n.type == "func_name"}

    parent_count: Dict[str, int] = {q: 0 for q in blocks}
    structural_edges = [e for e in graph.edges if e.type in ("HAS_BLOCK", "NESTS")]
    adjacency: Dict[str, List[str]] = {}
    for e in structural_edges:
        if e.target in blocks:
            parent_count[e.target] = parent_count.get(e.target, 0) + 1
            adjacency.setdefault(e.source, []).append(e.target)
    for q, cnt in parent_count.items():
        if cnt != 1:
            problems.append(f"code_block {q} 有 {cnt} 个结构父节点（应恰好 1）")

    # 显式 DFS 环检测（PKG 只靠索引顺序隐含保证，这里显式断言）
    WHITE, GREY, BLACK = 0, 1, 2
    color: Dict[str, int] = {}

    def dfs(node: str) -> None:
        color[node] = GREY
        for nxt in adjacency.get(node, []):
            if color.get(nxt, WHITE) == GREY:
                problems.append(f"结构层出现环：{node} -> {nxt}")
            elif color.get(nxt, WHITE) == WHITE:
                dfs(nxt)
        color[node] = BLACK

    for root in list(impls) + [q for q in blocks if parent_count.get(q) == 0]:
        if color.get(root, WHITE) == WHITE:
            dfs(root)

    proj = {(e.source, e.target) for e in graph.edges if e.type == "PROJECTS_TO"}
    infn = {(e.source, e.target) for e in graph.edges if e.type == "IN_FUNCTION"}
    for q, n in blocks.items():
        fid = n.get("function_id")
        if not fid:
            problems.append(f"code_block {q} 缺少 function_id（块→函数投影）")
            continue
        if not any(s == q and t in impls for s, t in proj):
            problems.append(f"code_block {q} 缺少 PROJECTS_TO 投影边")
        if not any(s == q and t in names for s, t in infn):
            problems.append(f"code_block {q} 缺少 IN_FUNCTION 投影边")

    # 不变量 8：子块 content 必须是父块 content 的子串
    for e in structural_edges:
        if e.type != "NESTS":
            continue
        parent, child = graph.nodes.get(e.source), graph.nodes.get(e.target)
        if parent and child and parent.type == "code_block":
            pc, cc = parent.get("content", ""), child.get("content", "")
            if pc and cc and cc not in pc:
                problems.append(f"块 content 子串不变量破坏：{e.target} ⊄ {e.source}")


def _check_causal_hierarchy(graph: Any, problems: List[str]) -> None:
    """不变量 5/6：构造式层级，meso/macro 必须由下层 DERIVES_FROM 聚合。"""
    derives: Dict[str, List[str]] = {}
    for e in graph.edges:
        if e.type == "DERIVES_FROM":
            derives.setdefault(e.source, []).append(e.target)
    for n in graph.nodes.values():
        if n.type != "causal_node":
            continue
        level = n.get("abstraction")
        if level in ("meso", "macro") and not derives.get(n.qn):
            problems.append(f"{level} 节点 {n.qn} 未由下层构造（禁止独立生成）")
    # CAD 的节点数预算是「prompt 结构护栏」，对多文件大图会自然超出；
    # 因此按 (modality, phase, level) 分组记软警告，不阻断构建。
    grouped: Dict[Tuple[str, str, str], int] = {}
    for n in graph.nodes.values():
        if n.type == "causal_node":
            k = (str(n.get("source_modality", "")), str(n.get("phase", "")),
                 str(n.get("abstraction", "")))
            grouped[k] = grouped.get(k, 0) + 1
    warnings = []
    for (modality, phase, level), count in grouped.items():
        hi = LEVEL_BUDGET.get(level, (1, 10**6))[1]
        if count > hi:
            warnings.append(f"{modality}/{phase}/{level}: {count} 节点 > 预算 {hi}")
    if warnings:
        graph.meta.setdefault("budget_warnings", []).extend(warnings)


def _check_gate_binding(graph: Any, problems: List[str]) -> None:
    """不变量 7：gate 指标必须绑定 decision / parameter 节点。"""
    for n in graph.nodes.values():
        if n.type != "metric_binding" or n.get("role") != "gate":
            continue
        asserted = [e.target for e in graph.edges
                    if e.type == "ASSERTS" and e.source == n.qn]
        ok = any((graph.nodes.get(t) is not None and
                  graph.nodes[t].get("causal_type") in ("decision", "parameter"))
                 for t in asserted)
        if not ok:
            problems.append(f"gate 指标 {n.label} 未绑定 decision/parameter 节点")


def validate_graph(graph: Any) -> List[str]:
    """返回不变量违反列表（空 = 通过）。"""
    problems: List[str] = []
    qns = [n.qn for n in graph.nodes.values()]
    if len(qns) != len(set(qns)):
        problems.append("存在重复 qn 主键")
    _check_known_vocab(graph, problems)
    _check_structure_tree(graph, problems)
    _check_causal_hierarchy(graph, problems)
    _check_gate_binding(graph, problems)
    return problems


def node_json_schema() -> Dict[str, Any]:
    """导出 JSON Schema，供 ``/api/v3/schema`` 与外部校验器使用。"""
    def arr(t: str = "string") -> Dict[str, Any]:
        return {"type": "array", "items": {"type": t}}

    def enum(*v: str) -> Dict[str, Any]:
        return {"type": "string", "enum": list(v)}

    return {
        "type": "object",
        "required": ["qn", "type"],
        "properties": {
            "qn": {"type": "string"}, "type": enum(*NODE_TYPES),
            "label": {"type": "string"}, "layer": enum(*LAYERS),
            "granularity": enum(*GRANULARITIES),
            "source_id": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "attrs": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "block_kind": enum(*BLOCK_KINDS),
                    "function_id": {"type": "string"},
                    "parent_block_id": {"type": "string"},
                    "start_line": {"type": "integer"}, "end_line": {"type": "integer"},
                    "col": {"type": "integer"}, "depth": {"type": "integer"},
                    "causal_type": enum(*CAUSAL_TYPES),
                    "phase": enum(*PHASES),
                    "abstraction": enum(*ABSTRACTIONS),
                    "source_modality": enum(*SOURCE_MODALITIES),
                    "resolution": enum(*RESOLUTIONS),
                    "line": {"type": "integer"}, "col_offset": {"type": "integer"},
                    "arg_count": {"type": "integer"},
                    "kwarg_names": arr(), "callee_written": {"type": "string"},
                    "role": enum(*METRIC_ROLES),
                    "metric_name": {"type": "string"},
                    "threshold": {"type": "number"},
                    "anchored": {"type": "boolean"},
                    "quote": {"type": "string"},
                    "agreement": enum("High", "Partial", "Low"),
                    "gap_type": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    }
