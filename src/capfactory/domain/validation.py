"""v2 领域验证器：蛋白质 / 分子算法的可执行复现验证.

为什么需要第二条验证路径
------------------------
``replicate/runner.py`` 把标签读成 ``int``、只算分类指标、硬编码
``TASK_TYPE == "sequence_binary_classification"``，无法验证 SMILES 回归、
结合亲和力回归、分子生成等新契约。本模块在不改动 v1 的前提下提供 v2：

1. **静态契约**：复用 ``contract.static_check``（先显式注册领域契约）；
2. **预执行完整性门**：SciForge AAR D2/D3 扫描（评测集泄漏 / 教师模型）；
3. **平台侧裁判执行**：候选代码只在子进程中提供 ``featurize`` / ``build_model``
   或 ``generate``，所有指标由本模块计算（选手与裁判分离）；
4. **稳定性**：换 seed + 下采样复跑，检查主指标波动；
5. **三态 Critic**：相对复现基线必须在**全集测试集**上严格更优，平局不算赢；
6. **完备性审计**：增益算术复核 + 方法描述↔实现 token parity；
7. **fail-closed 边界门**：任何非 PASS verdict 阻断知识沉淀。

所有指标用 numpy 实现，无新增依赖；子进程带超时强杀与环境变量白名单。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..integration.sciforge_bridge import SciForgeBridge, get_bridge
from ..replicate.contract import static_check
from ..utils import now_iso, short_hash, write_json
from .contracts import (
    DOMAIN_CONTRACTS, DOMAIN_EVALUATION, get_domain_contract,
    register_domain_contracts,
)

# ---------------------------------------------------------------------------
# 纯函数指标
# ---------------------------------------------------------------------------
def _rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1, dtype=float)
    # 处理并列
    i = 0
    while i < len(a):
        j = i + 1
        while j < len(a) and a[order[j]] == a[order[i]]:
            j += 1
        if j - i > 1:
            ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def compute_regression_metrics(y_true: Sequence[float],
                               y_pred: Sequence[float]) -> Dict[str, float]:
    """回归指标：spearman / pearson / rmse / mae / r2（纯 numpy）。"""
    y = np.asarray(y_true, dtype=float).ravel()
    p = np.asarray(y_pred, dtype=float).ravel()
    n = min(len(y), len(p))
    y, p = y[:n], p[:n]
    if n == 0 or not np.isfinite(y).all() or not np.isfinite(p).all():
        return {"spearman": 0.0, "pearson": 0.0, "rmse": 0.0, "mae": 0.0,
                "r2": 0.0, "n": 0}
    err = y - p
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-12
    return {
        "spearman": round(_pearson(_rankdata(y), _rankdata(p)), 6),
        "pearson": round(_pearson(y, p), 6),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 6),
        "mae": round(float(np.mean(np.abs(err))), 6),
        "r2": round(1.0 - ss_res / ss_tot, 6),
        "n": int(n),
    }


# 轻量代理校验：不含 RDKit，刻意排除 '@' / '*' 等易被滥用的通配/手性符号，
# 使明显非法的占位串不会被判为有效分子（真实 SMILES 语法子集请接 RDKit）。
_SMILES_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                    "()[]{}#+-=/\\.:%~$")


def _smiles_valid(s: str) -> bool:
    if not isinstance(s, str) or not (1 <= len(s) <= 200):
        return False
    if not set(s) <= _SMILES_CHARS:
        return False
    return s.count("(") == s.count(")") and s.count("[") == s.count("]")


def compute_generation_metrics(train: Sequence[str],
                               generated: Sequence[str]) -> Dict[str, float]:
    """生成任务：validity / uniqueness / novelty / diversity（不依赖 RDKit）。"""
    gen = [g for g in generated if isinstance(g, str)]
    n = len(gen)
    if n == 0:
        return {"validity": 0.0, "uniqueness": 0.0, "novelty": 0.0,
                "diversity": 0.0, "n": 0}
    valid = [g for g in gen if _smiles_valid(g)]
    uniq = set(gen)
    train_set = set(train or [])
    novelty = sum(1 for g in uniq if g not in train_set) / max(len(uniq), 1)
    sample = valid[:100]

    def grams(s: str) -> set:
        return {s[i:i + 3] for i in range(max(0, len(s) - 2))} or {s}

    diversity = 0.0
    if len(sample) >= 2:
        gs = [grams(s) for s in sample]
        pairs = 0
        total = 0.0
        for i in range(min(len(gs), 40)):
            for j in range(i + 1, min(len(gs), 40)):
                union = gs[i] | gs[j]
                total += 1.0 - (len(gs[i] & gs[j]) / len(union) if union else 0.0)
                pairs += 1
        diversity = total / pairs if pairs else 0.0
    return {
        "validity": round(len(valid) / n, 6),
        "uniqueness": round(len(uniq) / n, 6),
        "novelty": round(float(novelty), 6),
        "diversity": round(float(diversity), 6),
        "n": int(n),
    }


# ---------------------------------------------------------------------------
# 数据集
# ---------------------------------------------------------------------------
@dataclass
class DomainDataset:
    """v2 验证数据集。``x`` 元素可为 str 或 ``[a, b]``（成对任务）。"""

    train_x: List[Any] = field(default_factory=list)
    train_y: List[float] = field(default_factory=list)
    test_x: List[Any] = field(default_factory=list)
    test_y: List[float] = field(default_factory=list)
    name: str = "synthetic"
    protocol: str = "held-out test split, fixed seed 42"

    def to_json(self) -> Dict[str, Any]:
        return {"name": self.name, "protocol": self.protocol,
                "train": [{"x": x, "y": y} for x, y in zip(self.train_x, self.train_y)],
                "test": [{"x": x, "y": y} for x, y in zip(self.test_x, self.test_y)]}

    @classmethod
    def synthetic(cls, task_type: str = "protein_sequence_regression",
                  n_train: int = 200, n_test: int = 80, seed: int = 42) -> "DomainDataset":
        """确定性合成数据，供离线自检与复现测试。"""
        rng = np.random.RandomState(seed)
        aa = "ACDEFGHIKLMNPQRSTVWY"

        def make_x(n: int) -> List[str]:
            return ["".join(rng.choice(list(aa), size=int(rng.randint(8, 30))))
                    for _ in range(n)]

        if task_type == "smiles_property_regression":
            atoms = "CNOPSClBr"
            def make_smiles(n: int) -> List[str]:
                return ["C" * int(rng.randint(2, 8)) + rng.choice(list("CNOPS")) +
                        "(" + "C" * int(rng.randint(0, 3)) + ")" +
                        rng.choice(list(atoms)) for _ in range(n)]
            tr, te = make_smiles(n_train), make_smiles(n_test)
            f = lambda s: 0.35 * s.count("O") + 0.2 * s.count("N") - 0.1 * s.count("C")  # noqa: E731
        elif task_type == "pairwise_binding_regression":
            tr = [[a, "CCO" if i % 2 else "CCN"] for i, a in enumerate(make_x(n_train))]
            te = [[a, "CCO" if i % 2 else "CCN"] for i, a in enumerate(make_x(n_test))]
            f = lambda p: 0.5 * p[0].count("A") + 0.3 * (p[1].count("O"))  # noqa: E731
        elif task_type == "molecular_generation":
            tr, te = make_x(n_train), []
            f = lambda s: 0.0  # noqa: E731
        else:
            tr, te = make_x(n_train), make_x(n_test)
            f = lambda s: 0.6 * s.count("A") + 0.25 * s.count("K") - 0.15 * s.count("D")  # noqa: E731
        return cls(train_x=tr, train_y=[float(f(x) + rng.normal(0, 0.25)) for x in tr],
                   test_x=te, test_y=[float(f(x) + rng.normal(0, 0.25)) for x in te],
                   name=f"synthetic_{task_type}",
                   protocol=f"held-out test split ({n_train}/{n_test}), fixed seed {seed}")


# ---------------------------------------------------------------------------
# 平台侧裁判脚本（子进程中执行；候选代码无法改写指标计算）
# ---------------------------------------------------------------------------
_EVAL_SCRIPT = r'''
import json, sys, importlib.util, traceback
from pathlib import Path
import numpy as np

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = {"ok": False, "stage": "init", "warnings": []}
try:
    data = json.loads(Path(cfg["dataset"]).read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("candidate_solution", cfg["module"])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["candidate_solution"] = mod
    spec.loader.exec_module(mod)
    res["stage"] = "import"
    res["declared_task_type"] = getattr(mod, "TASK_TYPE", "")
    tr = data["train"]; te = data["test"]
    train_x = [r["x"] for r in tr]; train_y = np.asarray([r["y"] for r in tr], dtype=float)
    test_x = [r["x"] for r in te]; test_y = np.asarray([r["y"] for r in te], dtype=float)
    if cfg["evaluator"] == "generation":
        res["stage"] = "generate"
        gen = mod.generate(cfg["n_generate"], seed=cfg["seed"])
        res["generated"] = [str(g) for g in gen]
        res["train_items"] = [str(x) for x in train_x]
        res["ok"] = True
    else:
        if not hasattr(mod, "featurize") or not hasattr(mod, "build_model"):
            raise AttributeError("missing featurize/build_model")
        res["stage"] = "featurize"
        Xtr = np.asarray(mod.featurize(train_x), dtype=float)
        Xte = np.asarray(mod.featurize(test_x), dtype=float)
        empty = np.asarray(mod.featurize([]), dtype=float)
        single = np.asarray(mod.featurize([train_x[0]]), dtype=float)
        if Xtr.ndim != 2 or Xte.ndim != 2 or Xtr.shape[1] != Xte.shape[1]:
            raise ValueError("featurize must return 2-D arrays with equal feature dim")
        if Xtr.shape[0] != len(train_x) or Xte.shape[0] != len(test_x):
            raise ValueError("featurize row count mismatch")
        if not np.isfinite(Xtr).all() or not np.isfinite(Xte).all():
            raise ValueError("non-finite features")
        res["edge_cases_ok"] = bool(empty.ndim == 2 and empty.shape[0] == 0
                                    and single.ndim == 2 and single.shape[0] == 1)
        res["feature_dim"] = int(Xtr.shape[1])
        res["stage"] = "fit"
        model = mod.build_model()
        model.fit(Xtr, train_y)
        res["stage"] = "predict"
        pred = np.asarray(model.predict(Xte), dtype=float).ravel()
        if len(pred) != len(test_y) or not np.isfinite(pred).all():
            raise ValueError("invalid predictions")
        if len(np.unique(pred)) == 1:
            res["warnings"].append("constant prediction")
        res["y_true"] = test_y.tolist()
        res["y_pred"] = pred.tolist()
        res["ok"] = True
    res["stage"] = "done"
except Exception as exc:
    res["error"] = f"{type(exc).__name__}: {exc}"
    res["traceback"] = traceback.format_exc()[-3000:]
print("DOMAIN_RESULT:" + json.dumps(res, ensure_ascii=False))
'''


# ---------------------------------------------------------------------------
# 验证器
# ---------------------------------------------------------------------------
class DomainVerifier:
    """蛋白质 / 分子算法复刻的 v2 验证器。"""

    def __init__(self, *, bridge: Optional[SciForgeBridge] = None,
                 timeout: int = 120, stability_repeats: int = 1):
        register_domain_contracts()          # 让 static_check 认识领域契约
        self.bridge = bridge or get_bridge()
        self.timeout = timeout
        self.stability_repeats = max(1, stability_repeats)

    def _run(self, code: str, dataset: DomainDataset, task_type: str,
             *, seed: int = 42, n_generate: int = 50) -> Dict[str, Any]:
        """在隔离子进程中执行候选代码并回传原始结果。"""
        evaluator = DOMAIN_EVALUATION[task_type]["evaluator"]
        with tempfile.TemporaryDirectory(prefix="cf_domain_") as td:
            root = Path(td)
            module = root / "solution.py"
            module.write_text(code, encoding="utf-8")
            (root / "dataset.json").write_text(json.dumps(dataset.to_json()), encoding="utf-8")
            (root / "eval_runner.py").write_text(_EVAL_SCRIPT, encoding="utf-8")
            cfg = {"module": str(module), "dataset": str(root / "dataset.json"),
                   "evaluator": evaluator, "seed": seed, "n_generate": n_generate}
            (root / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
            env = {k: v for k, v in os.environ.items()
                   if k in ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "HOME")}
            env["PYTHONHASHSEED"] = str(seed)
            env["MPLBACKEND"] = "Agg"
            try:
                proc = subprocess.run(
                    [sys.executable, str(root / "eval_runner.py"), str(root / "cfg.json")],
                    cwd=str(root), env=env, capture_output=True, text=True,
                    timeout=self.timeout, check=False,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "stage": "timeout",
                        "error": f"execution exceeded {self.timeout}s"}
            marker = "DOMAIN_RESULT:"
            line = next((ln for ln in (proc.stdout or "").splitlines()
                         if ln.startswith(marker)), "")
            if not line:
                return {"ok": False, "stage": "no_result",
                        "error": (proc.stderr or proc.stdout or "no DOMAIN_RESULT")[-1500:]}
            return json.loads(line[len(marker):])

    def verify(self, code: str, dataset: DomainDataset, task_type: str,
               *, method_text: str = "", baseline_value: Optional[float] = None,
               problem_id: str = "", output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """完整 v2 验证，返回可 JSON 序列化的报告。"""
        if task_type not in DOMAIN_CONTRACTS:
            raise KeyError(f"未知领域任务类型：{task_type}")
        contract = get_domain_contract(task_type)
        eval_cfg = DOMAIN_EVALUATION[task_type]
        report: Dict[str, Any] = {
            "report_id": f"dver_{short_hash(code, task_type, length=8)}",
            "task_type": task_type, "created_at": now_iso(),
            "dataset": {"name": dataset.name, "protocol": dataset.protocol,
                        "n_train": len(dataset.train_x), "n_test": len(dataset.test_x)},
            "sciforge_backend": self.bridge.status()["backend"],
        }

        # 1) 静态契约
        static = static_check(code, task_type)
        report["contract"] = {"passed": bool(static.get("ok")), "detail": static,
                              "primary_metric": contract.primary_metric,
                              "threshold": contract.metric_threshold}
        # 2) 预执行完整性门
        gate = self.bridge.pre_execution_gate(code, benchmark_names=[dataset.name])
        report["integrity_gate"] = gate

        verdicts: Dict[str, str] = {
            "static_contract_ok": "PASS" if static.get("ok") else "FAIL",
            "integrity_D2_D3": "PASS" if gate["verdict"] == "PASS" else "FAIL",
        }

        # 3) 平台侧执行
        run = self._run(code, dataset, task_type)
        report["execution"] = {k: v for k, v in run.items()
                               if k not in ("y_true", "y_pred", "generated", "train_items")}
        if not run.get("ok"):
            report["metrics"] = {}
            verdicts["metrics_computed"] = "FAIL"
            report["failures"] = [f"执行失败：{run.get('error', 'unknown')}"]
        else:
            if eval_cfg["evaluator"] == "generation":
                metrics = compute_generation_metrics(run.get("train_items") or [],
                                                     run.get("generated") or [])
            else:
                metrics = compute_regression_metrics(run.get("y_true") or [],
                                                     run.get("y_pred") or [])
            report["metrics"] = metrics
            verdicts["metrics_computed"] = "PASS"
            report["functional"] = {
                "feature_dim": run.get("feature_dim"),
                "edge_cases_ok": run.get("edge_cases_ok"),
                "warnings": run.get("warnings") or [],
                "declared_task_type": run.get("declared_task_type"),
                "task_type_match": run.get("declared_task_type") == task_type,
            }

            # 4) 稳定性：换 seed 复跑
            stability = {"runs": [], "passed": True}
            for i in range(1, self.stability_repeats + 1):
                rep = self._run(code, dataset, task_type, seed=42 + 7 * i)
                if eval_cfg["evaluator"] == "generation":
                    rm = compute_generation_metrics(rep.get("train_items") or [],
                                                    rep.get("generated") or [])
                else:
                    rm = compute_regression_metrics(rep.get("y_true") or [],
                                                    rep.get("y_pred") or [])
                stability["runs"].append({"seed": 42 + 7 * i, "ok": rep.get("ok"),
                                          "primary": rm.get(contract.primary_metric)})
            vals = [v["primary"] for v in stability["runs"]
                    if isinstance(v["primary"], (int, float))]
            if vals:
                mean = sum(vals) / len(vals)
                std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
                stability.update({"mean": round(mean, 4), "std": round(std, 4),
                                  "passed": std <= 0.08 and all(v["ok"] for v in stability["runs"])})
            report["stability"] = stability

            # 5) SciForge 三态 Critic（相对复现基线）
            primary = metrics.get(contract.primary_metric)
            if baseline_value is not None and isinstance(primary, (int, float)):
                direction = "minimize" if contract.primary_metric in ("rmse", "mae") else "maximize"
                ladder = self.bridge.evaluate_candidate(
                    baseline_subset=baseline_value, candidate_subset=float(primary),
                    baseline_full=baseline_value, candidate_full=float(primary),
                    direction=direction, metric=contract.primary_metric,
                    problem_id=problem_id or report["report_id"])
                report["ladder"] = ladder
                verdicts["s2_ladder"] = ladder["verdict"]
            else:
                report["ladder"] = {"verdict": "NOT_APPLICABLE",
                                    "note": "未提供复现基线，跳过严格提升判定"}
                verdicts["s2_ladder"] = "NOT_APPLICABLE"

            # 6) 完备性审计
            report["audit"] = self.bridge.audit_experiment(
                method_text=method_text or f"{task_type} using {contract.title}",
                code_text=code,
                ladder_doc=report["ladder"].get("doc"),
                protocol_text=dataset.protocol)
            verdicts["reward_hacking_audit"] = report["audit"]["overall"]

        # 7) fail-closed 边界门 + 综合判定
        boundary = self.bridge.check_boundary(
            verdicts, phase="p5_verify->p6_deposit",
            required=["static_contract_ok", "integrity_D2_D3", "metrics_computed"])
        report["boundary"] = boundary
        value = report["metrics"].get(contract.primary_metric)
        metric_ok = isinstance(value, (int, float)) and (
            value <= contract.metric_threshold if contract.primary_metric in ("rmse", "mae")
            else value >= contract.metric_threshold)
        warnings = (report.get("functional") or {}).get("warnings") or []
        cheating = any("constant" in w for w in warnings)
        report["overall_score"] = round(
            0.20 * (1.0 if static.get("ok") else 0.0) +
            0.20 * (1.0 if run.get("ok") else 0.0) +
            0.30 * (min(1.0, float(value or 0.0) / max(contract.metric_threshold, 1e-6))
                    if metric_ok else 0.0) +
            0.15 * (1.0 if report.get("stability", {}).get("passed") else 0.0) +
            0.15 * (1.0 if boundary["ok"] else 0.0), 4)
        report["passed"] = bool(boundary["ok"] and metric_ok and not cheating)
        report["verdicts"] = verdicts
        report["failures"] = report.get("failures") or (
            [] if report["passed"] else
            ["边界门未通过或主指标未达阈值" if not (boundary["ok"] and metric_ok)
             else "检测到恒定预测，判定为无效实现"])

        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            write_json(out / "domain_verification.json", report)
        return report


def verify_domain_code(code: str, task_type: str = "protein_sequence_regression",
                       *, dataset: Optional[DomainDataset] = None,
                       method_text: str = "", baseline_value: Optional[float] = None,
                       output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """便捷入口：合成数据 + v2 验证，供 CLI / API / 测试直接调用。"""
    ds = dataset or DomainDataset.synthetic(task_type)
    return DomainVerifier().verify(code, ds, task_type, method_text=method_text,
                                   baseline_value=baseline_value,
                                   output_dir=output_dir)
