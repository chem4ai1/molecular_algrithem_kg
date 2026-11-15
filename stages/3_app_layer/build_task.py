#!/usr/bin/env python3
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

"""按 TaskSpec 构建任务层（reproduction / generation）。"""
import json, sys
from capfactory.applayer.builder import build_task_layer, status

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "reproduction"
    if task == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        r = build_task_layer(task, persist=True)
        print(json.dumps({k: r[k] for k in ("task", "nodes", "assertions",
                                            "n_relations", "by_type", "path")},
                         ensure_ascii=False, indent=2))
