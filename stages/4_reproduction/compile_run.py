#!/usr/bin/env python3
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

"""编译 ReproSpec（含 SAU/树）→ 跑 dry/lite 复现 → 出 rubric 与判定。"""
import json, sys
from pathlib import Path
from capfactory.po import POGraph
from capfactory.reprospec.compiler import compile_reprospec
from capfactory.sciforge.repro import run_repro

if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "paper:2411.06608"
    effort = sys.argv[2] if len(sys.argv) > 2 else "lite"
    ws = Path("storage/repro_runs") / pid.split(":")[-1]
    spec = compile_reprospec(paper_id=pid, out_dir=ws)
    print("SAU", len(spec.sau), "| spec_hash", spec.spec_hash[:20])
    r = run_repro(POGraph.load("storage_cf/sciforge/app_reproduction.json"),
                  pid, ws=ws, effort=effort)
    print(json.dumps({k: r.get(k) for k in ("ok", "overall", "effort",
                                            "ws", "files")},
                     ensure_ascii=False, indent=2))
