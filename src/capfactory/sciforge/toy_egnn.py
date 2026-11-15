"""任务 B 的 toy 复现实验：EGNN 的 E(n) 等变性解析解回归（纯标准库）。

SciForge 范式（``fixtures/e2e_minimal/toy_experiment/run_toy.py``）：
用**已知解析恒等式**设 sanity band，固定 seeds，蒙特卡洛结果必须落回区间。

这里的解析解是 EGNN（arXiv:2102.09844）的核心性质：

1. **距离不变性**：对坐标做任意旋转 R + 平移 t，
   ``||(R x_i + t) - (R x_j + t)|| == ||x_i - x_j||``  精确成立。
2. **等变消息传递层**：``x_i' = x_i + Σ_j (x_i - x_j) φ(||x_i-x_j||²)``
   满足 ``f(RX + t) == R f(X) + t``（旋转等变、平移等变），
   而标量特征 ``h`` 在变换下保持不变。

判定门：

* 距离不变误差 < ``1e-9``（解析恒等）；
* 等变层误差 < ``1e-9``（浮点舍入量级）；
* 不变特征误差 == 0；
* 三个 seed 全部通过，且两次运行逐字段一致（除耗时）。
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

SEEDS = (42, 43, 44)
N_POINTS = 8
DISTANCE_TOL = 1e-9
EQUIV_TOL = 1e-9
RATIO_BAND = (0.0, 1e-9)      # 等变误差必须落在的区间


def rotation_z(theta: float) -> List[List[float]]:
    c, s = math.cos(theta), math.sin(theta)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def mat_vec(R: Sequence[Sequence[float]], v: Sequence[float]) -> List[float]:
    return [sum(R[i][j] * v[j] for j in range(3)) for i in range(3)]


def apply_transform(x: Sequence[Sequence[float]], R: Sequence[Sequence[float]],
                    t: Sequence[float]) -> List[List[float]]:
    return [[mat_vec(R, p)[k] + t[k] for k in range(3)] for p in x]


def dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))


def phi(r2: float) -> float:
    """标量消息函数：只依赖不变距离（EGNN 的关键简化）。"""
    return 1.0 / (1.0 + r2)


def equivariant_layer(x: Sequence[Sequence[float]],
                      h: Sequence[float]) -> Tuple[List[List[float]], List[float]]:
    """简化 EGCL：坐标用相对位移加权更新，标量特征做均值聚合。"""
    n = len(x)
    out_x: List[List[float]] = []
    out_h: List[float] = []
    for i in range(n):
        dx = [0.0, 0.0, 0.0]
        for j in range(n):
            if i == j:
                continue
            w = phi(dist(x[i], x[j]) ** 2)
            for k in range(3):
                dx[k] += (x[i][k] - x[j][k]) * w
        out_x.append([x[i][k] + dx[k] for k in range(3)])
        out_h.append(statistics.fmean(h))
    return out_x, out_h


def run_seed(seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    x = [[rng.uniform(-2, 2) for _ in range(3)] for _ in range(N_POINTS)]
    h = [rng.uniform(0, 1) for _ in range(N_POINTS)]
    R = rotation_z(rng.uniform(-math.pi, math.pi))
    t = [rng.uniform(-3, 3) for _ in range(3)]
    xt = apply_transform(x, R, t)

    # ① 距离不变性
    d_err = max(abs(dist(x[i], x[j]) - dist(xt[i], xt[j]))
                for i in range(N_POINTS) for j in range(N_POINTS))

    # ② 等变层：先变换再算 vs 先算再变换
    fx, fh = equivariant_layer(x, h)
    ftx, fth = equivariant_layer(xt, h)
    fx_transformed = apply_transform(fx, R, t)
    eq_err = max(abs(ftx[i][k] - fx_transformed[i][k])
                 for i in range(N_POINTS) for k in range(3))

    # ③ 标量特征不变
    h_err = max(abs(a - b) for a, b in zip(fh, fth))

    return {"seed": seed, "distance_invariance_error": d_err,
            "equivariance_error": eq_err, "invariant_feature_error": h_err,
            "passed": (d_err < DISTANCE_TOL and eq_err < EQUIV_TOL
                       and h_err == 0.0)}


def run_toy() -> Dict[str, Any]:
    rows = [run_seed(s) for s in SEEDS]
    errs = [r["equivariance_error"] for r in rows]
    mean = statistics.fmean(errs)
    std = statistics.pstdev(errs)
    passed = (all(r["passed"] for r in rows)
              and RATIO_BAND[0] <= mean <= RATIO_BAND[1])
    return {"schema_version": "1.0", "experiment": "egnn_en_equivariance_toy",
            "analytic_ground_truth": "f(RX+t) == R f(X) + t; ||Rxi+t - (Rxj+t)|| == ||xi-xj||",
            "seeds": list(SEEDS), "n_points": N_POINTS,
            "sanity_band": list(RATIO_BAND), "rows": rows,
            "mean_equivariance_error": mean, "std_equivariance_error": std,
            "status": "PASS" if passed else "FAIL",
            "note": "纯标准库；距离/等变误差应仅为浮点舍入量级"}


def save_result(out: str | Path) -> Path:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    r = run_toy()
    p.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


if __name__ == "__main__":
    print(json.dumps(run_toy(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if run_toy()["status"] == "PASS" else 2)


def non_equivariant_layer(x: Sequence[Sequence[float]],
                          h: Sequence[float]) -> List[List[float]]:
    """对照基线：直接用**绝对坐标**做消息（破坏平移/旋转等变性）。"""
    n = len(x)
    out = []
    for i in range(n):
        dx = [0.0, 0.0, 0.0]
        for j in range(n):
            if i == j:
                continue
            w = phi(dist(x[i], x[j]) ** 2)
            for k in range(3):
                dx[k] += x[j][k] * w
        out.append([x[i][k] + dx[k] for k in range(3)])
    return out


def run_toy_ladder() -> Dict[str, Any]:
    """真实 subset→full 阶梯：naive 基线 vs 等变层，方向 minimize（误差）。"""
    from .contracts import decide, relative_gain, is_improvement
    rows = []
    for seed in SEEDS:
        rng = random.Random(seed)
        x = [[rng.uniform(-2, 2) for _ in range(3)] for _ in range(N_POINTS)]
        h = [rng.uniform(0, 1) for _ in range(N_POINTS)]
        R = rotation_z(rng.uniform(-math.pi, math.pi))
        t = [rng.uniform(-3, 3) for _ in range(3)]
        xt = apply_transform(x, R, t)

        def err(layer_fn):
            a = layer_fn(x, h)
            b = layer_fn(xt, h)
            ref = apply_transform(a, R, t)
            return max(abs(b[i][k] - ref[i][k])
                       for i in range(N_POINTS) for k in range(3))

        base = err(lambda xx, hh: non_equivariant_layer(xx, hh))
        cand = err(lambda xx, hh: equivariant_layer(xx, hh)[0])
        rows.append({"seed": seed, "baseline_error": base,
                     "candidate_error": cand})
    baseline = statistics.fmean(r["baseline_error"] for r in rows)
    candidate = statistics.fmean(r["candidate_error"] for r in rows)
    state = decide(baseline, candidate, direction="minimize")
    return {"schema_version": "1.0", "direction": "minimize",
            "baseline_score": baseline, "candidate_score": candidate,
            "critic_state": state, "engineer_rounds": 0,
            "relative_gain_pct": relative_gain(baseline, candidate, "minimize"),
            "full_set_pass": is_improvement(baseline, candidate, "minimize"),
            "rows": rows, "seeds": list(SEEDS),
            "note": "真实 toy 实验：naive 绝对坐标层 vs EGNN 相对位移等变层"}
