"""RUNSTATE / events.ndjson：事件日志是 durable truth，RUNSTATE 是派生快照。"""
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any, Dict, List

from .contract import RunState


class EventLog:
    def __init__(self, ws: Path):
        self.dir = Path(ws) / ".repro"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.ndjson"

    def append(self, event: Dict[str, Any]):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        return out


def replay(log: EventLog, state: RunState) -> RunState:
    """崩溃恢复：只按事件重放，快照不覆盖日志。"""
    for e in log.read():
        if e.get("type") == "phase_done":
            state.phase = e.get("phase", state.phase)
            state.next_action = e.get("next", state.next_action)
            state.verdicts[e["phase"]] = e.get("verdict", "PASS")
        elif e.get("type") == "interrupted":
            state.status = "interrupted"
        elif e.get("type") == "resume":
            state.status = "running"
    return state


def save_state(ws: Path, state: RunState):
    p = Path(ws) / "RUNSTATE.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, p)          # 原子写，避免撕裂快照
