#!/usr/bin/env python3
"""独立入口：自动把 src/ 加入 sys.path，可在本目录直接运行。"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)   # 统一使用仓库根作为工作目录（storage_cf/ 相对路径）

"""回填语义层 + 重建所有派生层（关系索引/溯源/CSV/向量/快照）。"""
import json
from capfactory.po import POGraph
from capfactory.semantic.apply import apply_all
from capfactory.semantic.refresh import refresh_all

if __name__ == "__main__":
    g = POGraph.load("storage_cf/sciforge/batch10_semantic_v4.json")
    a = apply_all(rebuild_app=False)
    print("apply_all", a["n_papers"], "篇 ->", a["totals"])
    r = refresh_all()
    print("refresh_all ok", r["ok"], "graph", r["graph"])
    print(json.dumps(r["steps"], ensure_ascii=False, default=str)[:800])
