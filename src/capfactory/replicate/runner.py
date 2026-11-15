"""沙箱子进程内的评测执行器.

该文件 **不是** 被生成的代码，而是平台侧的「裁判」：它负责导入被测模块、
按契约调用 ``featurize`` / ``build_model``，并在固定测试集上计算指标。
生成代码只能提供特征与模型，不能伪造评测结果。

用法::

    python -m capfactory.replicate.runner --module solution.py \
        --dataset dataset.json --out result.json --seed 42
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_csv(path: str) -> Tuple[List[str], List[int]]:
    seqs, labels = [], []
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        for row in csv.DictReader(f):
            s = (row.get("sequence") or "").strip()
            try:
                y = int(float(row.get("label")))
            except (TypeError, ValueError):
                continue
            if s:
                seqs.append(s)
                labels.append(y)
    return seqs, labels


def _load_module(path: str):
    spec = importlib.util.spec_from_file_location("candidate_solution", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_solution"] = module
    spec.loader.exec_module(module)
    return module


def _peak_mb() -> float:
    try:
        import psutil  # type: ignore

        return round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return 0.0


def _predict_scores(model: Any, X) -> List[float]:
    """统一取正类概率；不支持 predict_proba 时退化为 predict。"""
    import numpy as np

    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X))
        if proba.ndim == 2 and proba.shape[1] >= 2:
            return proba[:, 1].astype(float).tolist()
        if proba.ndim == 2 and proba.shape[1] == 1:
            return proba[:, 0].astype(float).tolist()
        return np.asarray(proba, dtype=float).ravel().tolist()
    pred = np.asarray(model.predict(X), dtype=float).ravel()
    return pred.tolist()


def run(module_path: str, dataset_path: str, out_path: str,
        seed: int = 42, subsample: float = 1.0) -> Dict[str, Any]:
    """执行训练与评测，返回结果字典（同时写入 out_path）。"""
    import numpy as np

    from capfactory.replicate.metrics import compute_classification_metrics

    result: Dict[str, Any] = {"ok": False, "stage": "init", "warnings": []}
    start = time.time()
    try:
        meta = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
        train_seqs, train_labels = _read_csv(meta["train_path"])
        test_seqs, test_labels = _read_csv(meta["test_path"])
        if not train_seqs or not test_seqs:
            raise ValueError("数据集为空（train 或 test 无有效样本）")
        result.update({"n_train": len(train_seqs), "n_test": len(test_seqs)})

        # ---- 可选下采样（用于稳定性测试） ----
        if subsample < 1.0:
            rng = np.random.RandomState(seed)
            idx = rng.choice(len(train_seqs), max(20, int(len(train_seqs) * subsample)), replace=False)
            train_seqs = [train_seqs[i] for i in idx]
            train_labels = [train_labels[i] for i in idx]

        # ---- 导入被测模块 ----
        result["stage"] = "import"
        module = _load_module(module_path)
        if not hasattr(module, "featurize") or not hasattr(module, "build_model"):
            raise AttributeError("模块缺少 featurize / build_model")
        declared_task = getattr(module, "TASK_TYPE", "")
        result["declared_task_type"] = declared_task
        if declared_task != "sequence_binary_classification":
            result["warnings"].append(f"TASK_TYPE 声明为 {declared_task!r}，与契约不一致")

        # ---- 特征化 ----
        result["stage"] = "featurize"
        t0 = time.time()
        X_train = np.asarray(module.featurize(train_seqs))
        X_test = np.asarray(module.featurize(test_seqs))
        feat_seconds = time.time() - t0
        if X_train.ndim != 2 or X_test.ndim != 2:
            raise ValueError(f"featurize 必须返回二维数组，实际 {X_train.shape} / {X_test.shape}")
        if X_train.shape[1] != X_test.shape[1]:
            raise ValueError(f"训练/测试特征维度不一致：{X_train.shape} vs {X_test.shape}")
        if X_train.shape[0] != len(train_seqs) or X_test.shape[0] != len(test_seqs):
            raise ValueError("featurize 返回的样本数与输入不一致")
        if not np.isfinite(X_train).all() or not np.isfinite(X_test).all():
            raise ValueError("特征中存在 NaN/Inf")

        # 边界用例：空输入 / 单样本 / 短序列
        edge_ok = True
        try:
            empty = np.asarray(module.featurize([]))
            single = np.asarray(module.featurize(["A"]))
            edge_ok = (empty.ndim == 2 and empty.shape[0] == 0) and (single.ndim == 2 and single.shape[0] == 1)
        except Exception as exc:  # 边界用例不计入致命错误
            edge_ok = False
            result["warnings"].append(f"边界用例异常：{exc}")

        y_train = np.asarray(train_labels, dtype=int)
        y_test = np.asarray(test_labels, dtype=int)

        # ---- 训练 ----
        result["stage"] = "fit"
        t0 = time.time()
        model = module.build_model()
        model.fit(X_train, y_train)
        fit_seconds = time.time() - t0

        # ---- 预测 ----
        result["stage"] = "predict"
        t0 = time.time()
        scores = _predict_scores(model, X_test)
        pred_seconds = time.time() - t0
        if len(scores) != len(y_test):
            raise ValueError(f"预测数量不匹配：{len(scores)} vs {len(y_test)}")
        scores_arr = np.asarray(scores, dtype=float)
        if not np.isfinite(scores_arr).all():
            raise ValueError("预测结果包含 NaN/Inf")
        if scores_arr.min() < -1e-6 or scores_arr.max() > 1 + 1e-6:
            result["warnings"].append("预测值超出 [0,1]，已裁剪")
            scores_arr = np.clip(scores_arr, 0.0, 1.0)

        # ---- 指标 ----
        metrics = compute_classification_metrics(y_test, scores_arr)
        train_scores = _predict_scores(model, X_train)
        train_metrics = compute_classification_metrics(y_train, np.asarray(train_scores))

        # 恒定预测检测（防止"作弊式"实现）
        if len(np.unique(scores_arr)) == 1:
            result["warnings"].append("预测值恒定，疑似无效实现")

        result.update({
            "ok": True,
            "stage": "done",
            "metrics": metrics,
            "train_metrics": train_metrics,
            "feature_dim": int(X_train.shape[1]),
            "edge_cases_ok": edge_ok,
            "overfit_gap": round(train_metrics.get("roc_auc", 0) - metrics.get("roc_auc", 0), 4),
            "timings": {
                "featurize_s": round(feat_seconds, 3),
                "fit_s": round(fit_seconds, 3),
                "predict_s": round(pred_seconds, 3),
                "total_s": round(time.time() - start, 3),
            },
            "peak_mem_mb": _peak_mb(),
            "seed": seed,
            "subsample": subsample,
        })
    except Exception as exc:
        result.update({
            "ok": False,
            "stage": result.get("stage", "unknown"),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-4000:],
        })
    finally:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="CapFactory 沙箱评测执行器")
    ap.add_argument("--module", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--subsample", type=float, default=1.0)
    args = ap.parse_args()
    res = run(args.module, args.dataset, args.out, seed=args.seed, subsample=args.subsample)
    print("CAPFACTORY_RESULT:", json.dumps({k: res.get(k) for k in ("ok", "stage", "metrics")}, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
