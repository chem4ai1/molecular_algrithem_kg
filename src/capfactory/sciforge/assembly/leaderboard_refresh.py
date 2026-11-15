"""A4 子模块：榜单刷新（蓝图 §3.4.3 refresh_leaderboard 契约）。

存图统一由 assemble_stage3 负责，这里只做 PG 导入 + 图内榜单刷新（不落主图）。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict


def refresh_leaderboard(inp: Any, plan: Any, *, graph: Any,
                        md: str = "") -> Dict[str, Any]:
    from ..benchmark_fill import extract_and_refresh
    out: Dict[str, Any] = {"ok": False, "benchmark_roots":
                           list(plan.benchmark_roots)}
    try:
        r = extract_and_refresh(inp.arxiv_id, graph, md or inp.md,
                                persist=False)
        out.update({"ok": True,
                    "pg_rows": r["import"].get("rows"),
                    "benchmark_ids": r["import"].get("benchmark_ids"),
                    "refreshed": r["refresh"]["refreshed"],
                    "sota_changes": r["refresh"]["sota_changes"]})
    except Exception as exc:  # noqa: BLE001 失败不吞，记 error
        out["error"] = f"{type(exc).__name__}:{exc}"[:200]
    p = Path(inp.out_dir) / "leaderboard.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return out
