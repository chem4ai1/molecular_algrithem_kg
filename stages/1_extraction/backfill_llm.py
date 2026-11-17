#!/usr/bin/env python3
"""LLM 二次抽取回填：E1-E3 重抽新字段 → apply_one 写回语义层图。

用法：
    python stages/1_extraction/backfill_llm.py --papers 2411.06608 2405.03370
    python stages/1_extraction/backfill_llm.py --papers-file data/slice_papers.txt
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph                              # noqa: E402
from capfactory.semantic.apply import apply_one                # noqa: E402
from capfactory.semantic.extraction.runner import run_extraction  # noqa: E402

GRAPH = ROOT / "storage_cf/sciforge/batch10_semantic_v4.json"
STAGES = ["E1_paper", "E2_algorithm", "E3_benchmark"]


def done(aid: str) -> bool:
    p = ROOT / "storage/sciforge/semantic_extraction" / (aid + ".json")
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        e1 = (d.get("stages", {}).get("E1_paper") or {}).get("data") or {}
        return bool(e1.get("evidence_type") or e1.get("paradigm"))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", nargs="*", default=[])
    ap.add_argument("--papers-file")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--save-every", type=int, default=1)
    a = ap.parse_args()
    ids = list(a.papers)
    if a.papers_file:
        ids += [x.strip() for x in Path(a.papers_file).read_text(
            encoding="utf-8").splitlines() if x.strip()]
    if not ids:
        ap.print_help()
        return 2
    g = POGraph.load(str(GRAPH))
    stat = {"ok": 0, "skip": 0, "fail": 0}
    t0 = time.time()
    for i, aid in enumerate(ids, 1):
        if done(aid) and not a.force:
            stat["skip"] += 1
            print(f"[{i}/{len(ids)}] {aid} 已有新字段，跳过")
            continue
        try:
            rep = run_extraction(aid, graph=g, persist=True, run_stages=STAGES)
            r = apply_one(g, rep)
            e1 = rep["stages"]["E1_paper"]["data"]
            print(f"[{i}/{len(ids)}] {aid} paradigm={e1.get('paradigm')} "
                  f"evidence_type={e1.get('evidence_type')} "
                  f"gaps={len(e1.get('gaps') or [])} "
                  f"claims={len(e1.get('claims') or [])} "
                  f"updated={r.get('updated')}")
            stat["ok"] += 1
        except Exception as exc:
            stat["fail"] += 1
            print(f"[{i}/{len(ids)}] {aid} 失败: {type(exc).__name__}: {exc}")
        if i % a.save_every == 0:
            g.save(str(GRAPH))
    g.save(str(GRAPH))
    print({"stat": stat, "secs": round(time.time() - t0, 1)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
