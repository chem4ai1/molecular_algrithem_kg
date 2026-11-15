"""能力复刻：方案规划 → 代码生成 → 沙箱验证 → 多轮修复 → 结果沉淀.

关键设计
--------
1. **多候选并行比较**：对 Top-N 方案分别生成代码并验证，按综合分择优
   （对应需求「支持多个候选算法方案自动比较」）；
2. **失败驱动修复**：把沙箱报错 + 历史失败经验（Lesson）回灌给修复智能体，
   最多 ``max_repair_rounds`` 轮（对应「支持多轮代码修复」）；
3. **验证结果回写**：通过后更新能力成熟度、版本、验证摘要与工件关联，
   失败则沉淀 ``Lesson``（对应「失败经验沉淀为可复用知识」）。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..config import Settings, get_settings
from ..kg import KnowledgeGraph
from ..llm import CoderAgent, PlannerAgent, RepairAgent
from ..schema import Artifact, Capability, Lesson, Plan, VerificationReport
from ..utils import ensure_dir, now_iso, read_json, short_hash, write_json
from .contract import contract_for_prompt, get_contract, infer_task_type, static_check
from .verifier import Verifier

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[str, str], None]]


def _notify(progress: ProgressFn, level: str, message: str) -> None:
    logger.info("[%s] %s", level, message)
    if progress:
        progress(level, message)


class Replicator:
    """单条能力的复刻执行器。"""

    def __init__(self, graph: KnowledgeGraph, settings: Optional[Settings] = None,
                 progress: ProgressFn = None):
        self.graph = graph
        self.settings = settings or get_settings()
        self.progress = progress
        cfg = self.settings.replicate
        self.max_candidates = int(cfg.get("max_candidates", 3))
        self.max_rounds = int(cfg.get("max_repair_rounds", 3))
        self.planner = PlannerAgent()
        self.coder = CoderAgent()
        self.repairer = RepairAgent()
        self.verifier = Verifier(self.settings)

    # ------------------------------------------------------------------
    def run(self, capability_id: str, dataset_meta: Dict[str, Any],
            code_refs: str = "") -> Dict[str, Any]:
        """执行完整复刻闭环，返回汇总结果。"""
        node = self.graph.get(capability_id)
        if node is None:
            raise KeyError(f"能力不存在：{capability_id}")
        attrs = node["attrs"]
        capability = self._to_capability(node)
        task_type = attrs.get("task_type") or infer_task_type(
            f"{capability.task} {capability.name} {capability.method}")
        contract = get_contract(task_type)
        contract_text = contract_for_prompt(task_type)

        _notify(self.progress, "plan", f"能力「{capability.name}」：检索相似能力并规划方案")
        references = self._references(capability, capability_id)
        plans = self.planner.plan(capability, references, contract_text, self.max_candidates)
        _notify(self.progress, "plan", f"生成 {len(plans)} 个候选方案，最优：{plans[0].name}（{plans[0].score:.3f}）")

        run_id = f"rep_{short_hash(capability_id, now_iso(), length=8)}"
        run_dir = ensure_dir(self.settings.path("workspace") / "runs" / run_id)
        write_json(run_dir / "plans.json", [p.to_dict() for p in plans])

        outcomes: List[Dict[str, Any]] = []
        for idx, plan in enumerate(plans):
            _notify(self.progress, "codegen", f"候选 {idx+1}/{len(plans)}：{plan.name}")
            outcome = self._attempt(capability, plan, task_type, contract_text,
                                    dataset_meta, run_dir, idx, code_refs)
            outcomes.append(outcome)
            if outcome["passed"] and outcome["report"].overall_score >= 0.85:
                break  # 已足够好，不再消耗算力

        best = max(outcomes, key=lambda o: o["report"].overall_score)
        self._consolidate(capability, best, outcomes, run_dir)
        _notify(self.progress, "done",
                f"复刻完成：{'通过' if best['passed'] else '未通过'}，"
                f"首选方案 {best['plan'].name}，综合分 {best['report'].overall_score:.3f}")

        return {
            "run_id": run_id,
            "capability_id": capability_id,
            "capability_name": capability.name,
            "task_type": task_type,
            "plans": [p.to_dict() for p in plans],
            "candidates": [{
                "plan": o["plan"].to_dict(),
                "artifact": o["artifact"].to_dict(),
                "report": o["report"].to_dict(),
                "passed": o["passed"],
                "code_path": o["artifact"].code_path,
            } for o in outcomes],
            "best": {
                "plan": best["plan"].name,
                "artifact_id": best["artifact"].id,
                "code_path": best["artifact"].code_path,
                "passed": best["passed"],
                "score": best["report"].overall_score,
                "metrics": best["report"].metrics.get("values", {}),
            },
            "run_dir": str(run_dir),
        }

    # ------------------------------------------------------------------
    def _attempt(self, capability: Capability, plan: Plan, task_type: str,
                 contract_text: str, dataset_meta: Dict[str, Any],
                 run_dir: Path, idx: int, code_refs: str) -> Dict[str, Any]:
        """单方案：生成 → 静态检查 → 验证 → 修复迭代。"""
        cand_dir = ensure_dir(run_dir / f"candidate_{idx+1}")
        code = self.coder.generate(capability, plan, contract_text, code_refs)
        module_path = cand_dir / "solution.py"
        module_path.write_text(code, encoding="utf-8")
        write_json(cand_dir / "plan.json", plan.to_dict())

        artifact = Artifact(
            id=f"art_{short_hash(capability.id, plan.id, length=8)}",
            capability_id=capability.id, plan_id=plan.id,
            code_path=str(module_path), task_type=task_type,
            dataset_path=dataset_meta.get("train_path", ""),
            requirements=self._requirements(code),
        )
        report: Optional[VerificationReport] = None

        for round_idx in range(1, self.max_rounds + 1):
            static = static_check(code, task_type)
            if not static.get("ok"):
                error = ("静态检查失败：" +
                         f"missing={static.get('missing_functions')} "
                         f"constants={static.get('missing_constants')} "
                         f"forbidden={static.get('forbidden_calls')} {static.get('forbidden_imports')} "
                         f"err={static.get('error', '')}")
                _notify(self.progress, "repair", f"第 {round_idx} 轮：静态检查失败，尝试修复")
            else:
                _notify(self.progress, "verify", f"第 {round_idx} 轮：沙箱验证中…")
                report = self.verifier.verify(artifact, dataset_meta, code,
                                              output_dir=cand_dir / f"verify_r{round_idx}")
                artifact.rounds = round_idx
                if report.passed:
                    break
                error = "验证未通过：" + "; ".join(report.failures) + "\n" + report.functional.get("error", "")[:2000]
                _notify(self.progress, "repair", f"第 {round_idx} 轮未通过：{report.failures[:1]}")

            if round_idx >= self.max_rounds:
                break
            lessons = self._lesson_texts(capability.id)
            fixed = self.repairer.repair(capability, contract_text, code,
                                          stage=report.functional.get("stage", "static") if report else "static",
                                          error=error, lessons=lessons)
            if not fixed:
                _notify(self.progress, "repair", "修复智能体未给出可用代码，停止迭代")
                break
            code = fixed
            module_path.write_text(code, encoding="utf-8")
            artifact.status = "repaired"

        if report is None:  # 全轮静态失败
            report = VerificationReport(
                id=f"ver_{short_hash(artifact.id, length=8)}",
                artifact_id=artifact.id, capability_id=capability.id,
                passed=False, failures=["静态检查未通过且修复失败"], overall_score=0.0,
            )
        report.metrics["dataset"] = dataset_meta.get("name", "")

        artifact.status = "verified" if report.passed else "failed"
        write_json(cand_dir / "report.json", report.to_dict())
        return {"plan": plan, "artifact": artifact, "report": report, "passed": report.passed}

    # ------------------------------------------------------------------
    def _consolidate(self, capability: Capability, best: Dict[str, Any],
                     outcomes: List[Dict[str, Any]], run_dir: Path) -> None:
        """把验证结果写回图谱：成熟度、版本、工件、经验。"""
        report: VerificationReport = best["report"]
        artifact: Artifact = best["artifact"]
        node = self.graph.get(capability.id)
        if node is None:
            return
        attrs = node["attrs"]
        primary = report.metrics.get("primary_value")
        threshold = report.metrics.get("threshold", 0.6)
        verified = bool(report.passed)
        if verified and isinstance(primary, (int, float)):
            perf = min(1.0, max(0.0, (primary - threshold) / max(1e-6, 1.0 - threshold)))
            maturity = round(min(1.0, 0.45 + 0.35 * perf + 0.20 * report.overall_score), 3)
        else:
            maturity = round(min(0.45, 0.15 + 0.3 * report.overall_score), 3)
        attrs["maturity"] = max(float(attrs.get("maturity", 0) or 0), maturity)
        attrs["task_type"] = artifact.task_type
        attrs["verification"] = {
            "passed": verified,
            "score": report.overall_score,
            "metrics": report.metrics.get("values", {}),
            "artifact_id": artifact.id,
            "run_id": run_dir.name,
            "dataset": report.metrics.get("dataset", ""),
            "verified_at": now_iso(),
            "candidates_compared": len(outcomes),
        }
        attrs["version"] = int(attrs.get("version", 1)) + 1
        attrs.setdefault("artifact_ids", [])
        if artifact.id not in attrs["artifact_ids"]:
            attrs["artifact_ids"].append(artifact.id)
        attrs["updated_at"] = now_iso()

        self.graph.add_artifact(artifact)
        self.graph.add_verification(report)

        # 失败经验沉淀
        if not verified:
            err = (report.functional.get("error") or "") or "; ".join(report.failures)
            signature = self._signature(err)
            lesson = Lesson(
                id=f"lesson_{short_hash(capability.id, signature, length=8)}",
                capability_id=capability.id,
                symptom=(report.failures[0] if report.failures else "验证未通过")[:200],
                root_cause=self._guess_cause(err),
                fix=self._guess_fix(err),
                error_signature=signature,
            )
            self.graph.add_lesson(lesson)
        self.graph.save()

    # ------------------------------------------------------------------
    def _references(self, capability: Capability, exclude_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query = f"{capability.name}\n{capability.task}\n{capability.method[:600]}"
        refs = []
        for hit in self.graph.search_capabilities(query, top_k=top_k + 1):
            if hit.node_id == exclude_id:
                continue
            node = self.graph.get(hit.node_id) or {}
            refs.append({
                "name": node.get("label", ""),
                "summary": (node.get("attrs", {}).get("summary") or "")[:200],
                "method": (node.get("attrs", {}).get("method") or "")[:400],
                "similarity": hit.score,
            })
            if len(refs) >= top_k:
                break
        return refs

    def _lesson_texts(self, capability_id: str) -> List[str]:
        out = []
        for e in self.graph.edges:
            if e["source"] == capability_id and e["type"] == "FAILED_WITH":
                node = self.graph.get(e["target"]) or {}
                a = node.get("attrs", {})
                out.append(f"{node.get('label')} → {a.get('fix', '')}（根因：{a.get('root_cause', '')}）")
        return out[:5]

    def _to_capability(self, node: Dict[str, Any]) -> Capability:
        attrs = node.get("attrs", {})
        data = dict(attrs)
        data.pop("label", None)
        data["id"] = node["id"]
        data["name"] = node.get("label", "")
        for key in ("inputs", "outputs", "metrics", "evidence"):
            data.setdefault(key, [])
        return Capability.from_dict(data)

    @staticmethod
    def _requirements(code: str) -> List[str]:
        mods = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", code or "", re.MULTILINE))
        std = {"math", "random", "itertools", "collections", "typing", "json", "csv", "re",
               "dataclasses", "functools", "pathlib", "os", "sys", "time", "warnings", "abc"}
        return sorted(m for m in mods if m not in std)

    @staticmethod
    def _signature(error: str) -> str:
        for line in (error or "").splitlines():
            line = line.strip()
            if line:
                return re.sub(r"0x[0-9a-f]+|\d+", "N", line)[:160]
        return "unknown"

    @staticmethod
    def _guess_cause(error: str) -> str:
        low = (error or "").lower()
        rules = [
            ("modulenotfound", "依赖未安装或导入了不可用库"),
            ("shapen", "特征维度/样本数不一致"),
            ("nan", "特征或预测出现 NaN/Inf（除零、空序列）"),
            ("singular", "矩阵奇异（特征冗余或样本过少）"),
            ("single class", "训练集只有单一类别，无法拟合"),
            ("timeout", "算法复杂度过高或存在死循环"),
            ("missing", "未实现契约要求的函数/常量"),
        ]
        for key, cause in rules:
            if key in low:
                return cause
        return "实现细节与契约/数据不匹配"

    @staticmethod
    def _guess_fix(error: str) -> str:
        low = (error or "").lower()
        if "modulenotfound" in low:
            return "移除不可用依赖，改用 numpy/scikit-learn 等价实现"
        if "nan" in low or "inf" in low:
            return "在特征化中对空序列/未知字符做零向量兜底，并加 np.nan_to_num"
        if "shape" in low:
            return "统一特征维度：固定 20/400 维输出，避免按样本自适应维度"
        if "single class" in low:
            return "训练前检查类别数，单类别时返回常数概率并给出 warning"
        if "timeout" in low:
            return "降低模型复杂度（减少树数量/迭代次数），避免 O(n^2) 特征计算"
        return "按契约修正函数签名与返回值形状"


def relevance_between(a: str, b: str) -> float:
    """简易文本相关度（供测试使用）。"""
    ta, tb = set(re.findall(r"[a-z]{3,}", (a + " " + b).lower())), set(re.findall(r"[a-z]{3,}", b.lower()))
    return len(ta & tb) / max(len(tb), 1)
