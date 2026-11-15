#!/usr/bin/env python3
"""独立入口：自动把 src/ 加入 sys.path，可在本目录直接运行。"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)   # 统一使用仓库根作为工作目录（storage_cf/ 相对路径）

import json, sys
from capfactory.po import POGraph
from capfactory.semantic.extraction.runner import run_extraction

if __name__ == "__main__":
    aid = sys.argv[1] if len(sys.argv) > 1 else "2411.06608"
    g = POGraph.load("storage_cf/sciforge/batch10_semantic_v4.json")
    r = run_extraction(aid, graph=g, persist=True)
    print(json.dumps({"arxiv_id": aid, "ok": r["ok"],
                      "paper_type": r["paper_type"],
                      "paradigm": (r.get("paradigm") or {}).get("summary"),
                      "model_results": r["model_results"]["deduplicated"]},
                     ensure_ascii=False, indent=2))
