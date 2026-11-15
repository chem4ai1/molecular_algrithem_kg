#!/usr/bin/env python3
"""独立入口：自动把 src/ 加入 sys.path，可在本目录直接运行。"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)   # 统一使用仓库根作为工作目录（storage_cf/ 相对路径）

"""批量抽取（断点续跑）：python run_batch.py --limit 3"""
import json
from capfactory.semantic.batch_extract import run, status

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--n-shards", type=int, default=1)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(run(limit=a.limit, shard=a.shard,
                             n_shards=a.n_shards), ensure_ascii=False))
