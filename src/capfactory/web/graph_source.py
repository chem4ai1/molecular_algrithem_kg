"""页面图源：统一从「语义层 / 应用层 / legacy」三张图里读，并做兼容映射。

- 页面默认读 **应用层图**（`batch10_app_v1.json`，含语义层 + 应用层两层）
- 用节点 `layer` 属性区分：`semantic` / `application`
- 数据视图（数据库层）**只读语义层**
- 关系浏览器**只读语义层**
- 应用层只在「论文复现 / 生成论文」时按任务构建（`capfactory/applayer/miner.py`）

为兼容现有页面代码，本模块把 v4 语义层字段名映射回旧名
（`research_question→research_problem`、`flow_family→algorithm_family`、
`AlgorithmModule→AlgorithmStep`），页面可逐步迁移。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path("storage_cf/sciforge")
SEMANTIC = ROOT / "batch10_semantic_v4.json"
APPLICATION = ROOT / "batch10_app_v1.json"
LEGACY = ROOT / "batch10_final_graph.json"

# v4 语义层 → 旧字段名（页面兼容用）
FIELD_ALIAS = {
    "research_question": "research_problem",
    "flow_family": "algorithm_family",
}
TYPE_ALIAS = {"AlgorithmModule": "AlgorithmStep"}
SEMANTIC_TYPES = ("Paper", "Algorithm", "AlgorithmModule", "CodeRepository",
                  "CodeFunction", "Benchmark")


def path_of(kind: str = "application") -> Path:
    return {"semantic": SEMANTIC, "application": APPLICATION,
            "legacy": LEGACY}.get(kind, APPLICATION)


def load(kind: str = "application", *, alias: bool = True):
    """加载图；alias=True 时把 v4 字段/类型名映射回旧名供页面使用。"""
    from ..po import POGraph
    p = path_of(kind)
    g = POGraph.load(str(p)) if p.exists() else POGraph(kind)
    if alias and kind != "legacy":
        _apply_alias(g)
    return g


def _apply_alias(g) -> None:
    for n in g.nodes.values():
        t = TYPE_ALIAS.get(n.type)
        if t:
            n.type = t
        a = n.attrs
        for old, new in FIELD_ALIAS.items():
            if old in a and new not in a:
                a[new] = a[old]


def layer_of(n: Any) -> str:
    return str((n.attrs or {}).get("layer") or "semantic")


def semantic_only(g, types: Optional[Iterable[str]] = None):
    """只保留语义层节点（数据库层 / 关系浏览器用）。"""
    want = set(types) if types else None
    return [n for n in g.nodes.values()
            if layer_of(n) == "semantic" and (want is None or n.type in want)]


def application_only(g, types: Optional[Iterable[str]] = None):
    want = set(types) if types else None
    return [n for n in g.nodes.values()
            if layer_of(n) == "application"
            and (want is None or n.type in want)]


def rebuild(semantic_graph=None, *, persist: bool = True) -> Dict[str, Any]:
    """重建应用层图（论文复现/生成论文时才调用）。"""
    from ..applayer.miner import mine_all
    from ..semantic.tbox_v4 import snapshot as sem_snap
    if semantic_graph is None:
        semantic_graph = load("semantic", alias=False)
    rep = mine_all(semantic_graph, persist=persist)
    rep["semantic"] = sem_snap()["version"]
    return rep


def load_task(task: str):
    """读取某任务的应用层图；不存在时抛清晰错误。"""
    from ..po import POGraph
    from ..applayer.tasks import out_path
    p = out_path(task)
    if not p.exists():
        raise FileNotFoundError(
            f"任务层尚未构建：{task}；请先调用 build_task_layer('{task}')")
    return POGraph.load(str(p))


def rebuild(semantic_graph=None, *, task: str | None = None,
            persist: bool = True) -> Dict[str, Any]:
    """兼容旧位置参数 semantic_graph；task=None 出语义层快照，否则构建任务层。"""
    from ..applayer.builder import build_task_layer
    from ..applayer.miner import mine_all
    g = semantic_graph if semantic_graph is not None else load(
        "semantic", alias=False)
    if task:
        return build_task_layer(task, graph=g, persist=persist)
    r = mine_all(g, task=None, persist=persist)
    return {"semantic_snapshot": r, "nodes": r["nodes"],
            "assertions": r["assertions"]}


def stats() -> Dict[str, Any]:
    out = {}
    for kind in ("legacy", "semantic", "application"):
        p = path_of(kind)
        if not p.exists():
            out[kind] = {"exists": False}
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out[kind] = {"exists": True, "nodes": len(d.get("nodes") or []),
                         "assertions": len(d.get("assertions") or []),
                         "path": str(p)}
        except Exception:  # noqa: BLE001
            out[kind] = {"exists": True, "error": "unreadable"}
    return out
