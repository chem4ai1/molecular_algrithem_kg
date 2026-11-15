"""评价指标（纯 numpy 实现，无额外依赖，便于在沙箱子进程中使用）. """

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np


def _as_array(x: Sequence[float]) -> np.ndarray:
    return np.asarray(list(x) if not isinstance(x, np.ndarray) else x, dtype=np.float64)


def confusion(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, int]:
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def accuracy(y_true, y_pred) -> float:
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.mean(y_true == y_pred)) if len(y_true) else 0.0


def precision(y_true, y_pred) -> float:
    c = confusion(_as_array(y_true), _as_array(y_pred))
    denom = c["tp"] + c["fp"]
    return c["tp"] / denom if denom else 0.0


def recall(y_true, y_pred) -> float:
    c = confusion(_as_array(y_true), _as_array(y_pred))
    denom = c["tp"] + c["fn"]
    return c["tp"] / denom if denom else 0.0


def f1(y_true, y_pred) -> float:
    p, r = precision(y_true, y_pred), recall(y_true, y_pred)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def mcc(y_true, y_pred) -> float:
    c = confusion(_as_array(y_true), _as_array(y_pred))
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]
    denom = np.sqrt(float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)))
    return float((tp * tn - fp * fn) / denom) if denom else 0.0


def roc_auc(y_true, y_score) -> float:
    """秩和法计算 AUROC（处理并列值）。"""
    y_true = _as_array(y_true)
    y_score = _as_array(y_score)
    n_pos = int(np.sum(y_true == 1))
    n_neg = int(np.sum(y_true == 0))
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = np.argsort(y_score, kind="mergesort")
    ranks = np.empty(len(y_score), dtype=np.float64)
    sorted_scores = y_score[order]
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1
    sum_pos_ranks = float(ranks[y_true == 1].sum())
    return float((sum_pos_ranks - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def average_precision(y_true, y_score) -> float:
    """PR 曲线下面积（标准阶梯法，等价 sklearn.average_precision_score）。"""
    y_true = _as_array(y_true)
    y_score = _as_array(y_score)
    if len(y_true) == 0:
        return 0.0
    total_pos = int(np.sum(y_true == 1))
    if total_pos == 0:
        return 0.0
    order = np.argsort(-y_score, kind="mergesort")
    y_sorted = y_true[order]
    tp = np.cumsum(y_sorted == 1).astype(np.float64)
    fp = np.cumsum(y_sorted == 0).astype(np.float64)
    precision = tp / np.maximum(tp + fp, 1.0)
    recall = tp / total_pos
    prev_recall = np.concatenate(([0.0], recall[:-1]))
    return float(np.sum((recall - prev_recall) * precision))


def rmse(y_true, y_pred) -> float:
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2))) if len(y_true) else 0.0


def mae(y_true, y_pred) -> float:
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.mean(np.abs(y_true - y_pred))) if len(y_true) else 0.0


def spearman(y_true, y_pred) -> float:
    """Spearman 秩相关。"""
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    if len(y_true) < 3:
        return 0.0

    def rank(a: np.ndarray) -> np.ndarray:
        order = np.argsort(a, kind="mergesort")
        r = np.empty(len(a))
        r[order] = np.arange(1, len(a) + 1)
        return r

    rt, rp = rank(y_true), rank(y_pred)
    if rt.std() == 0 or rp.std() == 0:
        return 0.0
    return float(np.corrcoef(rt, rp)[0, 1])


def compute_classification_metrics(y_true, y_score, threshold: float = 0.5) -> Dict[str, float]:
    """给定概率输出，返回完整分类指标集合。"""
    y_true = _as_array(y_true)
    y_score = _as_array(y_score)
    y_pred = (y_score >= threshold).astype(int)
    return {
        "accuracy": round(accuracy(y_true, y_pred), 4),
        "precision": round(precision(y_true, y_pred), 4),
        "recall": round(recall(y_true, y_pred), 4),
        "f1": round(f1(y_true, y_pred), 4),
        "mcc": round(mcc(y_true, y_pred), 4),
        "roc_auc": round(roc_auc(y_true, y_score), 4),
        "average_precision": round(average_precision(y_true, y_score), 4),
        "brier": round(float(np.mean((y_score - y_true) ** 2)) if len(y_true) else 0.0, 4),
        "n_samples": int(len(y_true)),
        "positive_rate": round(float(np.mean(y_true)) if len(y_true) else 0.0, 4),
    }
