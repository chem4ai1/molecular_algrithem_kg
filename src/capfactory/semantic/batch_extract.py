"""全量论文知识抽取（断点续跑，后台长跑）。

用法：
    python -m capfactory.semantic.batch_extract             # 续跑全部
    python -m capfactory.semantic.batch_extract --limit 20 # 只跑 20 篇
    python -m capfactory.semantic.batch_extract --status   # 只看进度

设计：
  - 论文清单 = data/docx/*.md（783 篇），按 arxiv_id 排序
  - 已有 `ok=true` 报告直接跳过（断点续跑）
  - 每篇失败不阻断，记入 state 后可重试
  - state 原子写，日志追加，随时可查进度
  - 全部完成后统一执行「回填 + 代码联系 + 溯源刷新 + 应用层重建」
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

MD_DIR = Path(os.environ.get("CAPFACTORY_PAPERS_DIR", "data/docx"))
EXT_DIR = Path("storage_cf/sciforge/semantic_extraction")
STATE = EXT_DIR / "_batch_state.json"
LOG = EXT_DIR / "_batch_extract.log"


def state_path(shard: int = 0, n_shards: int = 1) -> Path:
    return (EXT_DIR / f"_batch_state_{shard}of{n_shards}.json"
            if n_shards > 1 else STATE)


def read_state(shard: int = 0, n_shards: int = 1) -> Dict[str, Any]:
    p = state_path(shard, n_shards)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done": {}, "failed": {}, "started_at": "",
            "updated_at": "", "total": 0, "phase": "idle",
            "shard": f"{shard}/{n_shards}"}


def write_state(st: Dict[str, Any], shard: int = 0,
                n_shards: int = 1) -> None:
    st["updated_at"] = datetime.now().isoformat(timespec="seconds")
    p = state_path(shard, n_shards)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, p)
SEM_GRAPH = Path("storage_cf/sciforge/batch10_semantic_v4.json")


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def papers() -> list:
    return sorted(p.stem for p in MD_DIR.glob("*.md")
                  if p.stem[:4].isdigit() and "." in p.stem)






def report_exists(aid: str) -> bool:
    """报告存在即算「已处理」（ok=false 也是一种确定性结果，不应反复重跑）。"""
    return (EXT_DIR / (aid + ".json")).exists()


def report_ok(aid: str) -> bool:
    p = EXT_DIR / (aid + ".json")
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("ok"))
    except Exception:
        return False


def status(n_shards: int = 2) -> Dict[str, Any]:
    allp = papers()
    shards = []
    failed = 0
    for i in range(n_shards):
        st = read_state(i, n_shards)
        shards.append({"shard": f"{i}/{n_shards}",
                       "phase": st.get("phase"),
                       "done": len(st.get("done") or {}),
                       "failed": len(st.get("failed") or {}),
                       "updated_at": st.get("updated_at")})
        failed += len(st.get("failed") or {})
    done = sum(1 for a in allp if report_exists(a))
    n_ok = sum(1 for a in allp if report_ok(a))
    return {"total": len(allp), "done": done, "n_ok": n_ok,
            "n_not_ok": done - n_ok,
            "failed": failed, "remaining": len(allp) - done,
            "shards": shards,
            "updated_at": max((x["updated_at"] or "" for x in shards),
                              default="")}


def run(*, limit: int = 0, max_retries: int = 1,
        shard: int = 0, n_shards: int = 1) -> Dict[str, Any]:
    from ..po import POGraph
    from .extraction.runner import run_extraction

    allp = papers()
    if n_shards > 1:
        allp = [a for i, a in enumerate(allp) if i % n_shards == shard]
    st = read_state(shard, n_shards)
    if not st.get("started_at"):
        st["started_at"] = datetime.now().isoformat(timespec="seconds")
    st["total"] = len(allp)
    st["phase"] = "extracting"
    write_state(st, shard, n_shards)
    g = POGraph.load(str(SEM_GRAPH))
    log(f"START total={len(allp)} graph={len(g.nodes)} nodes")
    todo = [a for a in allp if not report_exists(a)]
    if limit:
        todo = todo[:limit]
    log(f"TODO {len(todo)} (skip {len(allp) - len(todo)} already ok)")
    t0 = time.time()
    for i, aid in enumerate(todo, 1):
        t = time.time()
        try:
            r = run_extraction(aid, graph=g, persist=True)
            st["done"][aid] = {"ok": r["ok"],
                               "paper_type": r["paper_type"]["paper_type"],
                               "slot_score": (r.get("paradigm") or {})
                               .get("summary", {}).get("slot_score"),
                               "seconds": r["seconds"]}
            st["failed"].pop(aid, None)
            log(f"[{i}/{len(todo)}] {aid} ok={r['ok']} "
                f"{r['seconds']}s slot={st['done'][aid]['slot_score']}")
        except Exception as exc:  # noqa: BLE001
            st["failed"][aid] = type(exc).__name__ + ":" + str(exc)[:150]
            log(f"[{i}/{len(todo)}] {aid} FAILED {st['failed'][aid]}")
            traceback.print_exc(file=sys.stderr)
        write_state(st, shard, n_shards)
    # 收尾：只有「全部论文都完成」且拿到文件锁的分片才重建派生层
    if status().get("remaining", 1) == 0:
        import fcntl
        lock = EXT_DIR / "_finalize.lock"
        with lock.open("a+") as lf:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log("FINALIZE skipped (another shard holds lock)")
            else:
                st["phase"] = "finalizing"
                write_state(st, shard, n_shards)
                log("FINALIZE start")
                try:
                    from .apply import apply_all
                    from .refresh import refresh_all
                    a = apply_all(rebuild_app=False)
                    log(f"  apply_all papers={a['n_papers']} "
                        f"subclass={a['totals']['subclass_of']}")
                    rr = refresh_all()
                    log(f"  refresh_all ok={rr['ok']} graph={rr['graph']}")
                except Exception as exc:  # noqa: BLE001
                    log("FINALIZE ERROR " + type(exc).__name__ + ":"
                        + str(exc)[:200])
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)
    else:
        log(f"FINALIZE deferred (remaining={status().get('remaining')})")
    st["phase"] = "done"
    st["elapsed_seconds"] = round(time.time() - t0, 1)
    write_state(st, shard, n_shards)
    log(f"DONE elapsed={st['elapsed_seconds']}s status={json.dumps(status())}")
    return status()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--n-shards", type=int, default=1)
    a = ap.parse_args()
    if a.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(run(limit=a.limit, max_retries=a.retries,
                             shard=a.shard, n_shards=a.n_shards),
                         ensure_ascii=False, indent=2))
