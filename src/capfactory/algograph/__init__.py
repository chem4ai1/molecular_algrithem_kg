"""AlgoGraph：细粒度算法图（论文方法模块 ↔ 代码函数/块 的节点对应）.

三层正交：
- L1 结构层：PKG 式 ``func_name → implementation → code_block``，站点级 CALLS/FLOWS_TO；
- L2 语义层：Causal Algorithm Design 的七类本体 + micro/meso/macro 构造式层级；
- L3 对齐与证据层：paper↔code grounding、TestCase / MetricBinding、修复定位。

设计依据见 ``docs/FINEGRAIN_ALGOGRAPH.md``。零新增第三方依赖，完全离线可用。
"""

from .schema import (
    ABSTRACTIONS, BLOCK_KINDS, CAUSAL_TYPES, EDGE_TYPES, LAYERS,
    METRIC_ROLES, NODE_TYPES, PHASES, RESOLUTIONS, Edge, Node,
    make_qn, node_json_schema, validate_graph,
)
from .store import AlgoGraph
from .parser import CodeGraphBuilder
from .callgraph import CallGraphBuilder
from .causal import CausalAnnotator, mermaid_to_graph, to_mermaid
from .linker import GroundingEngine
from .version import CapabilityVersion, MetricBinding, TestCase, build_capability_version
from .repair import RepairLocator

__all__ = [
    "NODE_TYPES", "EDGE_TYPES", "CAUSAL_TYPES", "PHASES", "ABSTRACTIONS",
    "BLOCK_KINDS", "LAYERS", "METRIC_ROLES", "RESOLUTIONS",
    "Node", "Edge", "make_qn", "node_json_schema", "validate_graph",
    "AlgoGraph", "CodeGraphBuilder", "CallGraphBuilder",
    "CausalAnnotator", "to_mermaid", "mermaid_to_graph",
    "GroundingEngine", "CapabilityVersion", "MetricBinding", "TestCase",
    "build_capability_version", "RepairLocator",
]
