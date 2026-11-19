#!/usr/bin/env python3
"""全量抽取 52 篇（vLLM + 声明式规则）：E1+E2+E3 → 语义层图。

- LLM 并发（4），apply 主线程串行（避免图字典竞态）
- 规则由 E1 YAML 的 rules: 段驱动（runner 内自动执行）
- 每 10 篇落盘，支持断点续跑
"""
from __future__ import annotations
import json, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.semantic.extraction.runner import run_extraction
from capfactory.semantic.apply import apply_one
from capfactory.llm.backends import chat

GRAPH = ROOT / "storage/sciforge/semantic_full52.json"
REPORTS = ROOT / "storage/sciforge/semantic_extraction"
MD = ROOT / "data/docx"
STAGES = ["E1_paper", "E2_algorithm", "E3_benchmark"]
WORKERS = 4


def chat_fn(prompt, **kw):
    return chat(prompt, backend="vllm", max_tokens=kw.get("max_tokens", 16384))


def done(aid: str) -> bool:
    p = REPORTS / f"{aid}.json"
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        e1 = (d.get("stages", {}).get("E1_paper") or {}).get("data") or {}
        # 新字段覆盖：至少 4 个 P0/P2 字段有值才算完成
        keys = ("formal_def", "data_sources", "method_limits", "result_tables",
                "paradigm", "evidence_type")
        return sum(1 for k in keys if e1.get(k) not in (None, "", [], {})) >= 4
    except Exception:
        return False


def main():
    force = "--force" in sys.argv
    ids = sorted(p.stem for p in MD.glob("*.md"))
    todo = [a for a in ids if force or not done(a)]
    print(f"总 {len(ids)} 篇，待抽 {len(todo)} 篇", flush=True)
    g = POGraph.load(str(GRAPH)) if GRAPH.exists() else POGraph("full52")
    lock = threading.Lock()
    stat = {"ok": 0, "fail": 0}
    t0 = time.time()

    def task(aid):
        try:
            rep = run_extraction(aid, graph=g, persist=True,
                                 chat_fn=chat_fn, run_stages=STAGES)
            return (aid, rep, "ok" if rep.get("ok") else "fail")
        except Exception as exc:  # noqa: BLE001
            print(f"ERR {aid}: {type(exc).__name__}:{str(exc)[:60]}", flush=True)
            return (aid, None, "fail")

    applied = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(task, a): a for a in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            aid, rep, status = fu.result()
            with lock:
                stat[status] += 1
                if rep is not None:
                    try:
                        apply_one(g, rep)
                        applied += 1
                    except Exception as exc:  # noqa: BLE001
                        print(f"APPLY_FAIL {aid}: {str(exc)[:60]}", flush=True)
                if applied and applied % 10 == 0:
                    g.save(str(GRAPH))
                print(f"[{i}/{len(todo)}] {status} {aid}", flush=True)
    g.save(str(GRAPH))
    print(json.dumps({"stat": stat, "applied": applied, "nodes": len(g.nodes),
                      "assertions": len(g.assertions),
                      "secs": round(time.time() - t0, 1),
                      "graph": str(GRAPH)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
