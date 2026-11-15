"""TBox 分层 API：语义层 v4 / 应用层 v1 / legacy v3.2 的只读快照与升级清单。"""
from __future__ import annotations
from typing import Any, Dict

from fastapi import HTTPException


def tbox_legacy() -> Dict[str, Any]:
    from ..ontology.tbox import snapshot, active_snapshot, reserved_snapshot
    return {"legacy": snapshot(), "active": active_snapshot(),
            "reserved": reserved_snapshot()}


def tbox_upgrade_plan() -> Dict[str, Any]:
    from ..ontology.tbox import upgrade_plan
    return upgrade_plan()


def tbox_semantic() -> Dict[str, Any]:
    from ..semantic.tbox_v4 import snapshot, class_snapshot
    return {"snapshot": snapshot(), "classes": class_snapshot()}


def tbox_application() -> Dict[str, Any]:
    from ..applayer.tbox import snapshot, class_snapshot
    return {"snapshot": snapshot(), "classes": class_snapshot()}


def layers() -> Dict[str, Any]:
    """三层对照：legacy(46/105) → semantic v4(8/11) → application v1(8/9)。"""
    from ..ontology.tbox import snapshot as ls
    from ..semantic.tbox_v4 import snapshot as ss
    from ..applayer.tbox import snapshot as aps
    L, S, A = ls(), ss(), aps()
    return {"legacy": {"version": L["version"], "classes": L["n_classes"],
                       "relations": L["n_relations"]},
            "semantic": {"version": S["version"],
                         "classes": S["n_classes"],
                         "relations": S["n_relations"],
                         "removed_classes": S["removed"]},
            "application": {"version": A["version"],
                            "classes": A["n_classes"],
                            "relations": A["n_relations"],
                            "derived_from": A["derived_from"]},
            "note": "semantic 只抽客观事实；application 从 semantic 确定性挖掘；"
                    "legacy 为切换前的兼容层"}


def task_specs() -> Dict[str, Any]:
    from ..applayer.tasks import snapshot
    return snapshot()


def task_status(task: str) -> Dict[str, Any]:
    from ..applayer.builder import status
    return status(task)


def task_build(task: str) -> Dict[str, Any]:
    from ..applayer.builder import build_task_layer
    return build_task_layer(task, persist=True)


def semantic_snapshot_build() -> Dict[str, Any]:
    from ..web.graph_source import rebuild
    return rebuild(task=None)



_V8T = [
    ("/api/v8/tbox/layers", layers, "GET", True),
    ("/api/v8/tbox/legacy", tbox_legacy, "GET", True),
    ("/api/v8/tbox/upgrade-plan", tbox_upgrade_plan, "GET", True),
    ("/api/v8/tbox/semantic", tbox_semantic, "GET", True),
    ("/api/v8/tbox/application", tbox_application, "GET", True),
    ("/api/v8/task/specs", task_specs, "GET", True),
    ("/api/v8/task/{task}/status", task_status, "GET", True),
    ("/api/v8/task/{task}/build", task_build, "POST", True),
    ("/api/v8/task/snapshot/build", semantic_snapshot_build, "POST", True),
]


def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    n = 0
    for path, ep, method, ins in _V8T:
        if path in existing:
            continue
        app.add_api_route(path, ep, methods=[method], include_in_schema=ins)
        n += 1
    return n
