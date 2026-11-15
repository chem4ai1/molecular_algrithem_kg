"""指标名归一：与 ``MetricDefinition`` 受控词表对齐，阻断重复建节点。

问题（``docs/REFINEMENTS.md`` §4）：逐节抽出 ``MSE / Forward time /
Binary Cross Entropy (BCE) / Mean Absolute Error``，这 4 个都不在词表里，
若直接建节点，每篇论文都会各造一个同义指标，榜单随后无法比较。

策略按优先级：

1. **exact / alias**：命中已有规范值或别名 → 复用已有 ``MetricDefinition`` 节点；
2. **canonicalize**：缩写与展开（``BCE``→``binary_cross_entropy``、
   ``Forward time``→``runtime``）→ 登记进词表并**只建一个共享节点**（幂等）；
3. **unmapped**：判不出来的写法 → **不建节点**，进 ``metric_proposals`` 交人工。

关键：注册规范值必须显式走 ``register_metric``，不能让抽取器顺手造节点。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..po import POGraph
from ..po.vocab import default_registry

METRIC_VOCAB = "metric_name"

# 缩写 / 展开 / 同义 → 规范值。规范值用 snake_case，便于跨论文共享。
METRIC_ALIASES: Dict[str, str] = {
    # 已在词表里的规范名，统一大小写与分隔符
    "ic50": "IC50", "kd": "Kd", "ki": "Ki",
    "auroc": "AUROC", "auprc": "AUPRC", "auc": "AUROC",
    "qed": "QED", "pearson r": "Pearson_r", "pearson_r": "Pearson_r",
    "vina": "Vina_Dock", "vina dock": "Vina_Dock", "docking score": "docking_score",
    "pose success": "pose_success_percent",
    "pb valid": "PB_valid_fraction",
    # 通用 ML 指标：词表原没有，登记为共享规范值
    "mse": "mean_squared_error",
    "mean squared error": "mean_squared_error",
    "mae": "mean_absolute_error",
    "mean absolute error": "mean_absolute_error",
    "bce": "binary_cross_entropy",
    "binary cross entropy": "binary_cross_entropy",
    "binary cross entropy (bce)": "binary_cross_entropy",
    "cross entropy": "cross_entropy",
    "ce": "cross_entropy",
    "rmse": "root_mean_squared_error",
    "root mean squared error": "root_mean_squared_error",
    "forward time": "runtime",
    "runtime": "runtime", "inference time": "runtime",
    "wall clock": "runtime", "latency": "runtime", "speed": "runtime",
    "accuracy": "accuracy", "acc": "accuracy",
    "f1": "F1", "f1 score": "F1", "r2": "R2",
    "validity": "validity", "uniqueness": "uniqueness", "novelty": "novelty",
}

# 通用指标登记时的方向 / 单位 / 值类型（写入共享节点）
METRIC_PROFILE: Dict[str, Dict[str, str]] = {
    "mean_squared_error": {"direction": "lower", "value_type": "number", "unit": ""},
    "mean_absolute_error": {"direction": "lower", "value_type": "number", "unit": ""},
    "root_mean_squared_error": {"direction": "lower", "value_type": "number", "unit": ""},
    "binary_cross_entropy": {"direction": "lower", "value_type": "number", "unit": ""},
    "cross_entropy": {"direction": "lower", "value_type": "number", "unit": ""},
    "runtime": {"direction": "lower", "value_type": "number", "unit": "s"},
    "accuracy": {"direction": "higher", "value_type": "fraction", "unit": ""},
    "F1": {"direction": "higher", "value_type": "fraction", "unit": ""},
    "R2": {"direction": "higher", "value_type": "number", "unit": ""},
    "validity": {"direction": "higher", "value_type": "fraction", "unit": ""},
    "uniqueness": {"direction": "higher", "value_type": "fraction", "unit": ""},
    "novelty": {"direction": "higher", "value_type": "fraction", "unit": ""},
}


def _norm(name: str) -> str:
    s = str(name or "").strip().lower()
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)       # 去括号注释
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def canonical_metric(name: str) -> Tuple[str, str]:
    """返回 ``(规范名, 命中方式)``；命中方式 ∈ exact/alias/canonical/raw。

    不查词表、不建节点——纯字符串归一，便于单测与批处理。
    """
    raw = str(name or "").strip()
    low = _norm(raw)
    if not raw:
        return "", "empty"
    vocab = default_registry.get(METRIC_VOCAB)
    for v in vocab.values:
        if v.lower() == raw.lower() or _norm(v) == low:
            return v, "exact"
    for alias, canonical in dict(vocab.aliases, **METRIC_ALIASES).items():
        if _norm(alias) == low:
            return canonical, "alias"
    # 规整成 snake_case 作为候选（仍需人工确认才登记）
    return re.sub(r"\s+", "_", low), "raw"


def register_metric(canonical: str, *, reason: str = "") -> Dict[str, Any]:
    """把通用指标**显式登记**进受控词表（幂等），不建图节点。"""
    vocab = default_registry.get(METRIC_VOCAB)
    if canonical in vocab.values:
        return {"canonical": canonical, "registered": False, "reason": "already_present"}
    default_registry.add_values(METRIC_VOCAB, [canonical])
    default_registry.add_aliases(
        METRIC_VOCAB,
        {k: v for k, v in METRIC_ALIASES.items() if v == canonical})
    return {"canonical": canonical, "registered": True, "reason": reason}


def metric_node_id(canonical: str) -> str:
    return f"metric:{canonical.lower().replace(' ', '_')}"


def ensure_metric_node(graph: POGraph, canonical: str) -> Tuple[str, bool]:
    """在共享图里只建**一个** MetricDefinition 节点；已存在则复用。"""
    mid = metric_node_id(canonical)
    if mid in graph.nodes:
        return mid, False
    prof = METRIC_PROFILE.get(canonical, {})
    graph.node(mid, "MetricDefinition", canonical,
               name=canonical, direction=prof.get("direction", "context_dependent"),
               value_type=prof.get("value_type", "number"),
               unit=prof.get("unit", ""),
               provenance="registered_shared_metric")
    return mid, True


def align_metric_name(name: str, *, graph: Optional[POGraph] = None,
                      allow_register: bool = True
                      ) -> Dict[str, Any]:
    """完整归一流程：判名 → 决定是否登记 → 是否建共享节点。

    返回 ``{raw, canonical, match, action, node_id, proposal}``。
    ``action`` ∈ reuse | registered | proposal。
    """
    canonical, match = canonical_metric(name)
    out: Dict[str, Any] = {"raw": name, "canonical": canonical, "match": match,
                           "action": "proposal", "node_id": "", "proposal": ""}
    if not canonical:
        out["proposal"] = "空指标名"
        return out
    vocab = default_registry.get(METRIC_VOCAB)
    if canonical in vocab.values:
        out["action"] = "reuse"
        if graph is not None:
            mid, _ = ensure_metric_node(graph, canonical)
            out["node_id"] = mid
        return out
    # 只有能给出明确 profile 的通用指标才自动登记，其余留给人工
    if allow_register and canonical in METRIC_PROFILE and match in ("alias", "canonical"):
        reg = register_metric(canonical, reason=f"通用 ML 指标：{name}")
        out["action"] = "registered"
        out["registered"] = reg["registered"]
        if graph is not None:
            mid, created = ensure_metric_node(graph, canonical)
            out["node_id"] = mid
            out["node_created"] = created
        return out
    out["proposal"] = (f"未命中受控词表（归一为 {canonical}），"
                       "不建节点；请确认是新增规范值还是已有指标的别名")
    return out


def align_experiments(experiments: Dict[str, Any], *,
                      graph: Optional[POGraph] = None) -> Dict[str, Any]:
    """对 ``extract_experiments`` 的输出整批归一，并给出节点复用统计。"""
    rows = [align_metric_name(str(m.get("name") or ""), graph=graph)
            for m in experiments.get("metrics") or []]
    out: Dict[str, Any] = {
        "n_raw": len(rows),
        "by_action": {},
        "by_match": {},
        "rows": rows,
        "proposals": [r for r in rows if r["action"] == "proposal"],
        "unique_nodes": len({r["node_id"] for r in rows if r["node_id"]}),
    }
    from collections import Counter
    out["by_action"] = dict(Counter(r["action"] for r in rows))
    out["by_match"] = dict(Counter(r["match"] for r in rows))
    return out


def metric_names_for_prompt() -> str:
    """给抽取 prompt 注入的受控指标清单（源头约束用）。"""
    vocab = default_registry.get(METRIC_VOCAB)
    return ", ".join(sorted(vocab.values))
