"""应用层任务规格：只有复现 / 生成两类任务才构建应用节点。

约定（用户 2026-11-13 明确）：
  - 语义层抽取与回填阶段**不产生任何应用层节点**；
  - 页面默认图 = 纯语义层快照；
  - 在「论文复现」或「生成论文」任务启动时，按 TaskSpec 只构建该任务需要的
    应用类与关系，写入独立图文件 app_<task>.json。
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

TASK_SPECS: Dict[str, Dict[str, Any]] = {
    "reproduction": {
        "label": "论文复现",
        "goal": "把论文的方法/数值/代码复现出来并比对",
        # P0-3：后 8 类是「复现运行时类」，由 reprospec.application 在
        # run 启动时写入独立图 app_repro_runtime.json；挖掘器不产生它们，
        # 因此 app_reproduction.json 与页面默认快照保持不变。
        "classes": ("LeaderboardEntry", "MetricDefinition", "DataContract",
                    "Evidence", "Limitation", "SourcePaper",
                    "MethodLock", "CodeGenerationTask", "StaticCheck",
                    "CompileReport", "ExperimentNode", "ReproductionResult",
                    "EvaluationResult", "ClaimAnchor", "RubricNode"),
        "relations": ("HAS_ENTRY", "USES_METRIC", "HAS_METRIC",
                      "HAS_CONTRACT", "SUPPORTED_BY", "HAS_LIMITATION",
                      "SITUATED_IN", "VERIFIES", "DEVIATES_FROM",
                      "LINEAGE_OF", "GENERATED_BY", "HAS_SAU"),
        "runtime_extends": "capfactory.reprospec.application",
        "miners": ("metrics", "leaderboard", "contracts", "evidence",
                   "limitations", "source_papers"),
        "reads": ("Benchmark.model_results[]", "Benchmark.metrics[]",
                  "Algorithm.limitations", "Paper-RELATED_TO->Paper",
                  "application_hints.json（Tool/Formula）"),
        "outputs": ("榜单行与动态 SOTA", "指标定义与单位",
                    "数据契约", "单元格级证据", "局限清单", "科技树出处"),
        "file": "storage_cf/sciforge/app_reproduction.json",
    },
    "writing": {
        "label": "论文写作",
        "goal": "为论文生成提供约束与素材：贡献、实验组、假设、失败模式、"
                "证据规范、图表、引用、章节、审稿点",
        "classes": ("Contribution", "ExperimentArm", "Assumption", "FailureMode",
                    "EvidenceNorm", "FigureAsset", "CitedPaper", "ResearchGap",
                    "SectionPlan", "ReviewPoint",
                    "MetricDefinition", "DataContract", "Evidence",
                    "Limitation", "SourcePaper"),
        "relations": ("DECLARES", "TESTED_BY", "RUNS", "ON", "ASSUMES",
                      "CONFORMS_TO", "APPLIES", "SHOWN_BY", "CITES",
                      "SEEKS_FROM", "GAP_SUPPORTED_BY", "ANCHORS",
                      "OUTLINES", "CHALLENGED_BY",
                      "HAS_METRIC", "HAS_CONTRACT", "SUPPORTED_BY",
                      "HAS_LIMITATION", "SITUATED_IN"),
        "miners": ("contributions", "experiment_arms", "assumptions",
                   "failure_modes", "evidence_norms", "figures",
                   "section_plans", "review_points",
                   "metrics", "contracts", "evidence", "limitations",
                   "source_papers"),
        "reads": ("Paper.contributions/figures/section_map/evidence_type",
                  "Algorithm.assumptions/novelty_basis",
                  "Module.is_novel_component",
                  "Benchmark.protocol/metrics[].contribution_link",
                  "Benchmark.model_results[].outcome_class/seeds"),
        "outputs": ("贡献与验证关系", "实验组矩阵", "方法假设",
                    "失败模式清单", "领域证据规范", "图表归属",
                    "引用核验位", "章节计划", "审稿关注点"),
        "file": "storage_cf/sciforge/app_writing.json",
    },
}

SEMANTIC_SNAPSHOT = "storage_cf/sciforge/batch10_app_v1.json"


ALIASES = {"generation": "writing"}   # 旧名保留，内部统一到 writing


def spec(task: str) -> Dict[str, Any]:
    task = ALIASES.get(task, task)
    if task not in TASK_SPECS:
        raise ValueError("未知应用层任务：" + str(task)
                         + "；可选 " + ", ".join(TASK_SPECS))
    return TASK_SPECS[task]


def snapshot() -> Dict[str, Any]:
    return {"tasks": {k: {"label": v["label"], "goal": v["goal"],
                          "classes": list(v["classes"]),
                          "relations": list(v["relations"]),
                          "miners": list(v["miners"]),
                          "file": v["file"]}
                      for k, v in TASK_SPECS.items()},
            "semantic_snapshot": SEMANTIC_SNAPSHOT,
            "rule": "抽取/回填期不构建应用节点；任务启动时按 spec 构建"}


def out_path(task: str | None) -> Path:
    task = ALIASES.get(task, task) if task else task
    return Path(SEMANTIC_SNAPSHOT if task is None else spec(task)["file"])
