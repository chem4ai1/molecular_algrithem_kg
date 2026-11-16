"""paperapp 路径与阈值。

不改项目既有 config.yaml / config.py：这里自带默认值，允许环境变量覆盖，
测试里可直接 mock.patch 模块常量。全部路径在仓库工作区内。
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]          # .../molecular_algrithem_design
STORAGE = REPO_ROOT / "storage" / "sciforge"

SEMANTIC_GRAPH = REPO_ROOT / "storage_cf" / "sciforge" / "batch10_semantic_v4.json"
APP_GRAPH = REPO_ROOT / "storage_cf" / "sciforge" / "app_generation.json"
OTHER_APP_GRAPH = REPO_ROOT / "storage_cf" / "sciforge" / "app_reproduction.json"

NODE_CACHE = STORAGE / "node_cache"
SIGNALS_DIR = NODE_CACHE / "signals"
REQUESTS_DIR = NODE_CACHE / "requests"
PROPOSALS_DIR = NODE_CACHE / "proposals"
NODES_DIR = STORAGE / "dynamic_tbox" / "nodes"
DYNAMIC_TBOX = STORAGE / "dynamic_tbox"
RUNS_DIR = STORAGE / "paperapp"
LOCK_FILE = STORAGE / ".paperapp.lock"

SEMANTIC_TBOX_VERSION = "v4.1-semantic"
DYNAMIC_TBOX_VERSION = "dyn-1.0.0"
TASK = "generation"

# 阈值（I4/I6：代码不硬编码判定值，全部集中于此）
SIM_REUSE = float(os.environ.get("PAPERAPP_SIM_REUSE", "0.98"))
SIM_AMBIGUOUS = float(os.environ.get("PAPERAPP_SIM_AMBIGUOUS", "0.92"))
MIN_REUSE = int(os.environ.get("PAPERAPP_MIN_REUSE", "3"))
PROMOTE_AFTER = int(os.environ.get("PAPERAPP_PROMOTE_AFTER", "2"))
HUMAN_BOOST_CAP = float(os.environ.get("PAPERAPP_HUMAN_BOOST_CAP", "0.0"))
GATE_TIMEOUT_POLICY = "BLOCKED"          # 永不自动通过
BOUNDARY_FLOOR = 6.0
S2_REBUTTAL_BAR = 8.0
MINING_COVERAGE_TARGET = 0.75
STALE_SCOPE_CEILING = 0.05
ALLOW_INCREMENTAL_WRITE = False          # S4 才置 True

# 26 阶段 id（顺序即 stage_order，禁止用 sorted() 数字排序）
STAGE_IDS = (
    "0", "1", "1a", "1b", "4broad", "2", "2.5", "2.5b", "3", "4targeted",
    "5", "6", "6a", "6b", "6c", "7", "8", "9", "10", "11", "12", "13",
    "14", "15", "15.5", "16",
)


def ensure_dirs() -> None:
    for p in (NODE_CACHE, SIGNALS_DIR, REQUESTS_DIR, PROPOSALS_DIR,
              NODES_DIR, DYNAMIC_TBOX, RUNS_DIR):
        p.mkdir(parents=True, exist_ok=True)
