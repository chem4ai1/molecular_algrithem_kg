"""统一验证机制.

五类检查（对应需求「功能正确性 / 指标表现 / 运行稳定性 / 接口规范 / 安全性」）::

    1. 静态契约检查   syntax、必需函数、禁用 API、危险导入
    2. 功能正确性     导入执行、特征形状、边界用例（空输入/单样本/短序列）
    3. 指标表现       在固定测试集上计算 AUROC/ACC/F1/MCC/AP 等
    4. 运行稳定性     改变随机种子与采样率重复执行，比较指标波动
    5. 资源与安全     运行时长、峰值内存、AST 安全扫描

最终给出 0-1 综合评分与 pass/fail 判定，并写回知识图谱。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..schema import Artifact, VerificationReport
from ..utils import ensure_dir, short_hash
from .contract import get_contract, static_check
from .sandbox import ExecResult, run_module

logger = logging.getLogger(__name__)


class Verifier:
    """算法模块统一验证器。"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        cfg = self.settings.replicate
        self.timeout = int(cfg.get("exec_timeout_seconds", 300))
        self.repeats = int(cfg.get("stability_repeats", 2))
        self.min_score = float(cfg.get("min_metric_score", 0.5))

    # ------------------------------------------------------------------
    def verify(self, artifact: Artifact, dataset_meta: Dict[str, Any],
               code: str, output_dir: Optional[Path] = None) -> VerificationReport:
        """执行全量验证。"""
        report_id = f"ver_{short_hash(artifact.id, artifact.rounds, length=8)}"
        report = VerificationReport(id=report_id, artifact_id=artifact.id,
                                    capability_id=artifact.capability_id)
        contract = get_contract(artifact.task_type)
        module_path = Path(artifact.code_path)
        dataset_json = Path(dataset_meta["dataset_json"]) if dataset_meta.get("dataset_json") else None
        if dataset_json is None:
            dataset_json = Path(dataset_meta["train_path"]).parent / "dataset.json"

        # ---- 1. 静态检查 ----
        static = static_check(code, artifact.task_type)
        report.contract = {
            "static": static,
            "task_type": artifact.task_type,
            "primary_metric": contract.primary_metric,
            "threshold": contract.metric_threshold,
            "passed": bool(static.get("ok")),
        }
        if not static.get("ok"):
            report.failures.append(
                "静态检查未通过：" + "; ".join(
                    filter(None, [
                        "" if static.get("syntax_ok") else "语法错误",
                        f"缺少函数 {static.get('missing_functions')}" if static.get("missing_functions") else "",
                        f"缺少常量 {static.get('missing_constants')}" if static.get("missing_constants") else "",
                        f"禁用调用 {static.get('forbidden_calls')}" if static.get("forbidden_calls") else "",
                        f"危险导入 {static.get('forbidden_imports')}" if static.get("forbidden_imports") else "",
                    ]))
            )

        out_dir = ensure_dir(Path(output_dir) if output_dir else module_path.parent / "verification")

        # ---- 2/3. 功能 + 指标 ----
        first: ExecResult = run_module(
            module_path, dataset_json, out_dir / "run_1.json",
            work_dir=module_path.parent, seed=42, subsample=1.0, timeout=self.timeout,
        )
        payload = first.payload
        metrics = payload.get("metrics") or {}
        report.functional = {
            "ran": first.ok,
            "stage": payload.get("stage"),
            "n_train": payload.get("n_train"),
            "n_test": payload.get("n_test"),
            "feature_dim": payload.get("feature_dim"),
            "edge_cases_ok": payload.get("edge_cases_ok"),
            "overfit_gap": payload.get("overfit_gap"),
            "warnings": payload.get("warnings", []),
            "error": None if first.ok else first.error_text,
        }
        report.metrics = {
            "values": metrics,
            "train_values": payload.get("train_metrics", {}),
            "primary_metric": contract.primary_metric,
            "primary_value": metrics.get(contract.primary_metric),
            "threshold": contract.metric_threshold,
        }
        if not first.ok:
            report.failures.append(f"执行失败：{first.error_text[:600]}")

        # ---- 4. 稳定性 ----
        stability: Dict[str, Any] = {"runs": [], "passed": False}
        if first.ok and self.repeats > 1:
            for i in range(1, self.repeats):
                r = run_module(
                    module_path, dataset_json, out_dir / f"run_{i+1}.json",
                    work_dir=module_path.parent, seed=42 + i * 7,
                    subsample=0.8 if i % 2 else 1.0, timeout=self.timeout,
                )
                stability["runs"].append({
                    "seed": 42 + i * 7,
                    "ok": r.ok,
                    "primary": (r.payload.get("metrics") or {}).get(contract.primary_metric),
                    "duration": round(r.duration, 2),
                })
            values = [v for v in [metrics.get(contract.primary_metric)] +
                      [run.get("primary") for run in stability["runs"]] if isinstance(v, (int, float))]
            if values:
                mean = sum(values) / len(values)
                std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
                stability.update({
                    "mean": round(mean, 4),
                    "std": round(std, 4),
                    "cv": round(std / mean, 4) if mean else 1.0,
                    "max_drop": round(max(values) - min(values), 4),
                    "passed": std <= 0.05 and all(r.get("ok") for r in stability["runs"]),
                })
        report.stability = stability

        # ---- 5. 资源与安全 ----
        report.resources = {
            "duration_s": round(first.duration, 2),
            "timings": payload.get("timings", {}),
            "peak_mem_mb": payload.get("peak_mem_mb", 0),
            "timeout_s": self.timeout,
        }
        report.security = {
            "forbidden_calls": static.get("forbidden_calls", []),
            "forbidden_imports": static.get("forbidden_imports", []),
            "sandboxed": True,
            "clean": not static.get("forbidden_calls") and not static.get("forbidden_imports"),
        }

        # ---- 综合评分与判定 ----
        report.overall_score = self._score(report, contract.primary_metric, contract.metric_threshold)
        report.passed = self._decide(report, contract.primary_metric, contract.metric_threshold)
        if not report.passed and not report.failures:
            report.failures.append("未达到通过阈值或稳定性要求")
        report.logs = (first.stdout or "")[-2000:] + (first.stderr or "")[-2000:]
        logger.info("验证完成 %s：passed=%s score=%.3f", artifact.id, report.passed, report.overall_score)
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _score(report: VerificationReport, primary: str, threshold: float) -> float:
        static_ok = 1.0 if report.contract.get("static", {}).get("ok") else 0.0
        functional = 0.0
        if report.functional.get("ran"):
            functional = 0.7 + (0.3 if report.functional.get("edge_cases_ok") else 0.0)
        value = report.metrics.get("primary_value")
        perf = 0.0
        if isinstance(value, (int, float)):
            # 以阈值为 0.6 分，1.0 封顶
            perf = min(1.0, max(0.0, (value - 0.5) / max(threshold, 1e-6) * 0.6))
            perf = min(1.0, perf + 0.2)
        stability = report.stability.get("passed")
        stab = 1.0 if stability else (0.5 if report.stability.get("runs") else 0.0)
        security = 1.0 if report.security.get("clean") else 0.0
        score = 0.20 * static_ok + 0.25 * functional + 0.35 * perf + 0.10 * stab + 0.10 * security
        return round(min(1.0, score), 4)

    def _decide(self, report: VerificationReport, primary: str, threshold: float) -> bool:
        if not report.contract.get("static", {}).get("ok"):
            return False
        if not report.functional.get("ran"):
            return False
        if not report.security.get("clean"):
            return False
        value = report.metrics.get("primary_value")
        if not isinstance(value, (int, float)) or value < threshold:
            return False
        if any("恒定" in w for w in report.functional.get("warnings", [])):
            return False
        return True


def verify_and_attach(artifact: Artifact, dataset_meta: Dict[str, Any], code: str,
                      settings: Optional[Settings] = None,
                      output_dir: Optional[Path] = None) -> VerificationReport:
    """便捷函数：验证并把结果摘要挂到 artifact 上。"""
    report = Verifier(settings).verify(artifact, dataset_meta, code, output_dir)
    artifact.status = "verified" if report.passed else "failed"
    return report
