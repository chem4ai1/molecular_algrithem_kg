#!/usr/bin/env python3
"""全量二次抽取（并发 LLM + 串行写图）。

- 并发：run_extraction 只写各自的报告文件，互不冲突
- 串行：apply_one 写同一张图，最后统一 save
- 断点：done() 判断已完成论文，跳过
"""
from __future__ import annotations
import argparse, json, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph                              # noqa: E402
from capfactory.semantic.apply import apply_one                # noqa: E402
from capfactory.semantic.extraction.runner import run_extraction  # noqa: E402

GRAPH = ROOT / "storage_cf/sciforge/batch10_semantic_v4.json"
MD = ROOT / "data/docx"
REPORT = ROOT / "storage/sciforge/semantic_extraction"
STAGES = ["E1_paper", "E2_algorithm", "E3_benchmark"]
KEYS = ("paradigm", "evidence_type", "gaps", "claims", "authors", "abstract",
        "open_problems", "delta_claims", "negative_results",
        "protocol_disclosure", "citation_style", "writing_style")


def done(aid: str) -> bool:
    p = REPORT / (aid + ".json")
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        e1 = (d.get("stages", {}).get("E1_paper") or {}).get("data") or {}
        return sum(1 for k in KEYS if e1.get(k) not in (None, "", [])) >= 8
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--log", default=str(ROOT / "storage/batch_extract.log"))
    a = ap.parse_args()
    ids = [p.stem for p in sorted(MD.glob("*.md"))]
    todo = [x for x in ids if a.force or not done(x)]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        print("没有待抽取论文")
        return 0
    g = POGraph.load(str(GRAPH))
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    stat = {"ok": 0, "fail": 0}

    def task(aid):
        try:
            rep = run_extraction(aid, graph=g, persist=True, run_stages=STAGES)
            with lock:
                stat["ok"] += 1
                with log.open("a", encoding="utf-8") as f:
                    e1 = rep["stages"]["E1_paper"]["data"]
                    filled = sum(1 for k in KEYS if e1.get(k) not in (None, "", []))
                    f.write(f"OK\t{aid}\t{filled}/12\t{e1.get('paradigm')}\t{e1.get('evidence_type')}\n")
            return (aid, rep, None)
        except Exception as exc:
            with lock:
                stat["fail"] += 1
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"FAIL\t{aid}\t{type(exc).__name__}:{exc}\n")
            return (aid, None, exc)

    t0 = time.time()
    applied = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(task, aid): aid for aid in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            aid, rep, err = fu.result()
            if rep is not None:
                try:
                    apply_one(g, rep)   # 主线程串行写图，线程安全
                    applied += 1
                except Exception as exc:
                    with log.open("a", encoding="utf-8") as f:
                        f.write(f"APPLY_FAIL\t{aid}\t{exc}\n")
            if applied and applied % 20 == 0:
                g.save(str(GRAPH))     # 每 20 篇落盘，中断最多丢 19 篇
            if i % 20 == 0:
                print(f"进度 {i}/{len(todo)}  ok={stat['ok']} fail={stat['fail']} "
                      f"elapsed={round(time.time()-t0)}s", flush=True)
    g.save(str(GRAPH))
    print({"todo": len(todo), "ok": stat["ok"], "fail": stat["fail"],
           "applied": applied, "secs": round(time.time() - t0, 1),
           "log": str(log)}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
