"""溯源修正一条命令：溯源修复 → 索引 → CSV → 向量 → 关系 → 应用层。

用法：
    from capfactory.semantic.refresh import refresh_all
    refresh_all()                       # 全量重建
    refresh_all(reextract=False)        # 只重算派生层，不重跑抽取
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

SEM_GRAPH = Path("storage_cf/sciforge/batch10_semantic_v4.json")


def refresh_all(*, graph=None, persist: bool = True,
                rebuild_app: bool = True,
                rebuild_vector: bool = True) -> Dict[str, Any]:
    from ..po import POGraph
    from . import provenance as P
    from . import vector_sync as V
    from ..sciforge.relation_layer import build_relations
    from ..applayer.miner import mine_all

    g = graph or POGraph.load(str(SEM_GRAPH))
    rep: Dict[str, Any] = {"steps": {}}
    rep["steps"]["repair"] = P.repair(g, persist=persist)
    # 新回填的 Paper 也要补 keywords（fill_keywords 原本只在迁移时跑）
    try:
        from .enrich import fill_keywords
        rep["steps"]["keywords"] = fill_keywords(g)
    except Exception as exc:  # noqa: BLE001
        rep["steps"]["keywords"] = {"error": str(exc)[:100]}
    rep["steps"]["provenance_index"] = P.build_index(g, persist=persist)
    rep["steps"]["missing_csv"] = P.export_missing_csv(g)
    rep["steps"]["relation_index"] = build_relations(g, persist=persist)
    if rebuild_vector:
        try:
            rep["steps"]["vector"] = V.build(g, persist=persist)
        except Exception as exc:  # noqa: BLE001
            rep["steps"]["vector"] = {"error":
                                      f"{type(exc).__name__}:{exc}"[:120]}
    if rebuild_app:
        # 只生成语义层快照；应用节点由任务层按 TaskSpec 显式构建
        rep["steps"]["semantic_snapshot"] = mine_all(
            g, task=None, persist=persist)
    rep["ok"] = not any("error" in str(v) for v in rep["steps"].values())
    rep["graph"] = {"nodes": len(g.nodes),
                    "assertions": len(g.assertions)}
    return rep


def csv_paths() -> Dict[str, str]:
    from .provenance import OUT_DIR
    return {"algorithms": str(OUT_DIR / "missing_paper_algorithms.csv"),
            "benchmarks": str(OUT_DIR / "missing_paper_benchmarks.csv"),
            "report": str(OUT_DIR / "provenance_report.json")}
