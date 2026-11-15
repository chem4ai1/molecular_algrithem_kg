"""论文表格抽取新范式：Table N → 模型×指标矩阵 → 可更新榜单 → 动态 SOTA。

用户要求：
* 表格是基准测试集最重要的产物，**行=模型、列=指标**；
* 表会随新论文抽取而变化，因此 SOTA 不能写死成「本论文方法(ours)」，
  而要按每个指标的方向（max/min）从**全部已入库结果**动态计算；
* 新论文出现更好结果时，自动新增行并切换该列 SOTA。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 基准节点保留的核心属性（用户明确：就这些够了）
CORE_FIELDS = ("name", "input_form", "output_form",
               "metrics", "model_results", "sota_by_metric",
               "n_samples", "scale", "modality", "research_object",
               "is_evaluation")
CORE_LABELS = {
    "name": "基准名称", "input_form": "输入数据形式",
    "output_form": "输出数据形式", "source_papers": "Benchmark 源论文",
    "metrics": "测试指标", "model_results": "各模型测试结果（可更新）",
    "sota_by_metric": "当前 SOTA（动态）", "n_samples": "样本量",
    "scale": "规模", "modality": "数据模态", "research_object": "研究对象"}

MIN_METRICS = {"mae", "rmse", "rmsd", "error", "frag_ratio", "loss", "fcd"}
OURS_SUFFIX = re.compile(
    r"\s*[\(（]\s*(ours?|our\s+method|本文|ours?\s+work)\s*[\)）]\s*$", re.I)


def normalize_model_name(name: str) -> str:
    """去掉 (ours) 等归属后缀：模型名就是模型名，SOTA 由计算得出。"""
    s = str(name or "").strip().strip("★").strip()
    prev = None
    while prev != s:
        prev = s
        s = OURS_SUFFIX.sub("", s).strip()
    return s


def direction_with_source(metric: str, *, declared: str = ""
                          ) -> Tuple[str, str]:
    """返回 (direction, source)；source 标明是词表/声明还是启发式。"""
    m = str(metric or "").lower().strip()
    if declared in ("min", "max"):
        return declared, "declared"
    if m in MIN_METRICS or m.startswith("mae"):
        return "min", "vocab"
    return "max", "heuristic"


def direction_of(metric: str, *, declared: str = "") -> str:
    return direction_with_source(metric, declared=declared)[0]


UNIT_PAT = re.compile(
    r"(kcal/mol|kJ/mol|eV|Hartree|Å|angstrom|nm|%|ms|s|mmHg|μg/ml|uM|nM)\s*$",
    re.I)


def parse_unit(v: Any) -> str:
    """从数值字符串尾部抽单位（修 E14：unit 恒空）。"""
    m = UNIT_PAT.search(str(v or "").strip())
    if m:
        return m.group(1)
    return "%" if "%" in str(v or "") else ""


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def rows_from_tables(tables: List[Dict[str, Any]], *, paper_id: str,
                     benchmark_id: str, provenance: str = "table_extract"
                     ) -> List[Dict[str, Any]]:
    """把 parse_tables 的结果摊平成可 upsert 的结果行。"""
    out: List[Dict[str, Any]] = []
    for t in tables:
        for m in t.get("models") or []:
            model = normalize_model_name(m.get("name") or "")
            if not model:
                continue
            for i, val in enumerate(m.get("values") or []):
                if i >= len(t.get("metrics") or []):
                    break
                metric = str(t["metrics"][i] or "").strip()
                if not metric or _num(val) is None:
                    continue
                out.append({"benchmark_id": benchmark_id,
                            "model_name": model, "metric_name": metric,
                            "value": _num(val), "value_raw": str(val),
                            "unit": parse_unit(val), "paper_id": paper_id,
                            "provenance": f"{provenance}:{t.get('table_no')}"})
    return out


def compute_sota(rows: List[Dict[str, Any]], *,
                 directions: Optional[Dict[str, str]] = None,
                 declared_metrics: Optional[Dict[str, str]] = None
                 ) -> Dict[str, Dict[str, Any]]:
    """按指标从全部结果里算当前 SOTA；并列记录 ties（不破坏原结构）。"""
    declared_metrics = declared_metrics or {}
    best: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        metric = r["metric_name"]
        v = _num(r.get("value"))
        if v is None:
            continue
        d = (directions or {}).get(metric) or \
            direction_of(metric, declared=declared_metrics.get(metric, ""))
        cur = best.get(metric)
        better = (cur is None or
                  (d == "min" and v < cur["numeric"]) or
                  (d == "max" and v > cur["numeric"]))
        if better:
            if cur and cur["numeric"] == v:
                ties = list(cur.get("ties") or []) + [cur["model"]]
            else:
                ties = []
            best[metric] = {"metric": metric, "model": r["model_name"],
                            "value": r["value_raw"], "numeric": v,
                            "direction": d,
                            "direction_source": (
                                "declared" if declared_metrics.get(metric)
                                else direction_with_source(metric)[1]),
                            "ties": ties,
                            "paper_id": r.get("paper_id"),
                            "provenance": r.get("provenance")}
        elif cur and v == cur["numeric"]:
            cur.setdefault("ties", []).append(r["model_name"])
    return best


def matrix(rows: List[Dict[str, Any]], *,
           directions: Optional[Dict[str, str]] = None,
           declared_metrics: Optional[Dict[str, str]] = None
           ) -> Dict[str, Any]:
    """行=模型、列=指标的显式矩阵（前端直接渲染）。"""
    dirs = dict(directions or {})
    sota = compute_sota(rows, directions=dirs,
                        declared_metrics=declared_metrics)
    metrics = []
    for m in sorted({r["metric_name"] for r in rows}):
        s = sota.get(m) or {}
        metrics.append({"name": m, "unit": "",
                        "direction": s.get("direction") or dirs.get(m)
                        or direction_of(m),
                        "direction_source": s.get("direction_source") or
                        ("declared" if dirs.get(m) else
                         direction_with_source(m)[1]),
                        "sota_model": s.get("model"),
                        "sota_value": s.get("value"),
                        "ties": s.get("ties") or []})
    cells: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        m, model = r["model_name"], r["metric_name"]
        cells.setdefault(m, {})[model] = {
            "value": r["value_raw"], "num": _num(r["value"]),
            "unit": r.get("unit") or "",
            "is_sota": False,
            "paper_id": r.get("paper_id"),
            "provenance": r.get("provenance")}
    # 修正 is_sota：按 (model, metric) 与 sota_by_metric 对齐
    for model, row in cells.items():
        for metric, cell in row.items():
            s = sota.get(metric)
            cell["is_sota"] = bool(s and s["model"] == model and
                                   cell["num"] == s["numeric"])
    models = []
    for model in sorted(cells):
        row = cells[model]
        models.append({"name": model, "cells": row,
                       "n_sota": sum(1 for c in row.values()
                                     if c["is_sota"])})
    models.sort(key=lambda x: (-x["n_sota"], x["name"]))
    return {"metrics": metrics, "models": models,
            "sota_by_metric": sota,
            "stats": {"n_models": len(models), "n_metrics": len(metrics),
                      "n_values": sum(len(m["cells"]) for m in models)}}
