"""应用层任务层的显式构建入口（唯一允许产生应用节点的地方）。"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from .tasks import spec, out_path, snapshot as task_snapshot

SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")


def build_task_layer(task: str, *, graph: Any = None,
                     persist: bool = True) -> Dict[str, Any]:
    """按 TaskSpec 构建某一任务的应用层图，写入 app_<task>.json。"""
    from ..po import POGraph
    from .miner import mine_all
    sp = spec(task)
    g = graph or POGraph.load(str(SEM))
    r = mine_all(g, task=task, out=out_path(task), persist=persist)
    return {"task": task, "label": sp["label"], "goal": sp["goal"],
            "classes": list(sp["classes"]),
            "relations": list(sp["relations"]),
            "by_type": r["by_type"], "n_relations": r["n_relations"],
            "nodes": r["nodes"], "assertions": r["assertions"],
            "miners": r["miners"], "path": r.get("path")}


def status(task: str | None = None) -> Dict[str, Any]:
    out = {"specs": task_snapshot()}
    if task:
        sp = spec(task)
        p = out_path(task)
        out["task"] = {"name": task, "label": sp["label"],
                       "file": str(p), "exists": p.exists()}
    else:
        out["tasks"] = {k: {"file": v["file"],
                            "exists": out_path(k).exists()}
                        for k in v_dict()}
    return out


def v_dict():
    from .tasks import TASK_SPECS
    return TASK_SPECS
