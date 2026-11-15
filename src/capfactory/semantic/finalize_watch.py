"""全量抽取收尾守护：报告齐全后自动回填并重建全部派生层。

独立于抽取分片运行（用新代码），避免旧分片内存里旧 status() 导致收尾不触发。
"""
from __future__ import annotations
import fcntl, json, time, traceback
from datetime import datetime
from pathlib import Path

from .batch_extract import status, log, EXT_DIR

DONE = EXT_DIR / "_finalize_done.json"
LOCK = EXT_DIR / "_finalize.lock"
INTERVAL = 60


def main() -> None:
    log("FINALIZE_WATCH start")
    while True:
        try:
            s = status()
            if s["remaining"] == 0:
                with LOCK.open("a+") as lf:
                    try:
                        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        log("FINALIZE_WATCH lock busy, retry")
                    else:
                        log("FINALIZE_WATCH all reports present, start")
                        try:
                            from .apply import apply_all
                            from .refresh import refresh_all
                            a = apply_all(rebuild_app=False)
                            log("  apply_all papers=" + str(a["n_papers"]))
                            r = refresh_all()
                            log("  refresh_all ok=" + str(r["ok"]))
                            DONE.write_text(json.dumps(
                                {"status": s, "at":
                                 datetime.now().isoformat(timespec="seconds")},
                                ensure_ascii=False, indent=2),
                                encoding="utf-8")
                            log("FINALIZE_WATCH DONE")
                        except Exception:  # noqa: BLE001
                            log("FINALIZE_WATCH ERROR " +
                                traceback.format_exc()[-400:])
                        finally:
                            fcntl.flock(lf, fcntl.LOCK_UN)
                        return
            else:
                log("FINALIZE_WATCH wait remaining=" + str(s["remaining"]))
        except Exception:  # noqa: BLE001
            log("FINALIZE_WATCH loop error " + traceback.format_exc()[-250:])
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
