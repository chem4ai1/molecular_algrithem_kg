"""GGR-Paper 应用层：语义层抽取 → 动态本体 → LLM 新节点缓存 → 人类决策。

设计依据：docs/SCIFORGE_INTEGRATION_BLUEPRINT.md、
docs/DYNAMIC_ONTOLOGY_NODE_CACHE.md、docs/DESIGN_REFLECTION_V2.md、
docs/plan/V2_DELTA.md。

不变量：
  I1 事实主权：语义层 6 类/9 关系冻结，llm_proposal 永不入内
  I2 单真相源：增量 ≡ 全量重建
  I3 全谱留痕：未命中/被拒/失败/未尝试方向都成节点
  I4 人类主权：gate 超时只能 BLOCKED
  I5 决定可传播：每个边界逐字复述
  I6 确定性优先：规则/AST/表格优先于 LLM
  I7 可演进不失稳：版本化、单一写入者、可回滚
"""
from __future__ import annotations

from . import config, util, tbox, registry, signals, hitl, coverage, gates
from .registry import (active_classes, deprecate_class, load_registry,
                       register_class, validate_dynamic_tbox)
from .signals import (KnowledgeSignal, cluster_signals, dismiss_signal,
                      observe_event, signal_stats)
from .hitl import (HumanDecision, open_choice, decide, supersede,
                   reinject, load_reinjection)
from .gates import emit, VERDICT_STATES
from .util import verify_rebuild

__all__ = [
    "config", "util", "tbox", "registry", "signals", "hitl", "coverage", "gates",
    "active_classes", "deprecate_class", "load_registry", "register_class",
    "validate_dynamic_tbox", "KnowledgeSignal", "cluster_signals",
    "dismiss_signal", "observe_event", "signal_stats", "HumanDecision",
    "open_choice", "decide", "supersede", "reinject", "load_reinjection",
    "emit", "VERDICT_STATES", "verify_rebuild",
]
