"""运行历史存储（SQLite）：供 Web 展示流水线轨迹与版本演进."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..utils import ensure_dir, now_iso

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,            -- build_kg / replicate / research / full
    status TEXT NOT NULL,          -- running / success / failed
    title TEXT,
    started_at TEXT,
    finished_at TEXT,
    summary TEXT,                  -- 人类可读摘要
    payload TEXT                   -- JSON 详情
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    ts TEXT,
    agent TEXT,
    level TEXT,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(kind);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
"""


class RunStore:
    """轻量运行记录库（线程安全）。"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        db_dir = ensure_dir(self.settings.path("storage") / "db")
        self.path = db_dir / "runs.sqlite3"
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    def start_run(self, run_id: str, kind: str, title: str = "") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs(id, kind, status, title, started_at) VALUES (?,?,?,?,?)",
                (run_id, kind, "running", title, now_iso()),
            )

    def finish_run(self, run_id: str, status: str, summary: str = "",
                   payload: Optional[Dict[str, Any]] = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status=?, finished_at=?, summary=?, payload=? WHERE id=?",
                (status, now_iso(), summary, json.dumps(payload or {}, ensure_ascii=False), run_id),
            )

    def log_event(self, run_id: str, message: str, agent: str = "system",
                  level: str = "info") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events(run_id, ts, agent, level, message) VALUES (?,?,?,?,?)",
                (run_id, now_iso(), agent, level, message[:2000]),
            )

    def list_runs(self, limit: int = 30, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT id, kind, status, title, started_at, finished_at, summary FROM runs"
        params: list = []
        if kind:
            query += " WHERE kind=?"
            params.append(kind)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params)]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["payload"] = json.loads(data.get("payload") or "{}")
            data["events"] = [dict(r) for r in conn.execute(
                "SELECT ts, agent, level, message FROM events WHERE run_id=? ORDER BY id", (run_id,))]
            return data
