"""核心流程单一入口（标准化后的推荐 import 路径）。

历史 ``sciforge/__init__.py`` 是重量级聚合导出（被 660 个测试依赖，保留不动），
但它把「当前核心链路」与「研究/兼容层」混在一起。后续改造请优先从本模块导入：

    from capfactory.sciforge.core import assemble, plan_repro, run_e2e

核心链路：
    Stage0–2 产物 → assemble_stage3(A1–A5) → cards / leaderboard
    → 关系索引 → 端到端报告 → 复现计划 → 复现执行
"""
from __future__ import annotations
from typing import Any

# ---- Stage3 装配层（A1–A5）----
from .assembly import assemble_stage3 as assemble
from .assembly import Stage3Manifest
from .assembly.cards import build_algorithm_cards
from .assembly.leaderboard_refresh import refresh_leaderboard

# ---- 端到端抽取与关系层 ----
from .extraction_e2e import run_extraction_e2e as run_e2e
from .relation_layer import build_relations, relations_for, instances

# ---- 语义层抽取 / 回填（新链路唯一入口）----
from ..semantic.extraction.runner import run_extraction
from ..semantic.apply import apply_all
from ..semantic.refresh import refresh_all
# ---- 三库核心 ----
from .algorithm_problem import search_algorithms, build_index
from .benchmark_fill import refresh_from_pg

# ---- 代码复现框架 ----
from .repro import build_plan as plan_repro
from .repro import run_repro, resume_repro

__all__ = ["assemble", "Stage3Manifest", "build_algorithm_cards",
           "refresh_leaderboard", "run_e2e", "build_relations",
           "relations_for", "instances", "run_extraction", "apply_all",
           "refresh_all", "search_algorithms", "build_index",
           "refresh_from_pg",
           "plan_repro", "run_repro", "resume_repro"]
