"""应用层 TBox：只做「从语义层挖掘出来的派生视图」，不直接抽取。

分层依据（参考 semantica-main 的 ontology → reasoning/decisions）：
  语义层（capfactory.semantic）：Paper/Algorithm/AlgorithmModule/CodeRepository/
        CodeFunction/Benchmark/Observation/Section —— 客观事实，可抽取
  应用层（本模块）：ResearchQuestion/ProblemCategory/LeaderboardEntry/
        MetricDefinition/DataContract/Evidence/Limitation/SourcePaper
        —— 全部由语义层**确定性挖掘**得到，用于复现与论文发掘

应用层节点必须带 `derived_from`（语义层节点 id 列表）、`miner`（挖掘器名）
与 `layer="application"`；语义层节点带 `layer="semantic"`。
**两层用 `layer` 属性区分，不用类型名前缀**（应用层类名与 legacy 同名是允许的，
因为它们在独立图文件里）。
"""
from __future__ import annotations
from typing import Any, Dict, Tuple

APP_VERSION = "v1.0-application"

APP_CLASSES: Dict[str, Tuple[str, Tuple[Tuple[str, str], ...]]] = {
    "ResearchQuestion": ("研究问题（从 Paper.research_question 提升为节点，便于聚类）", (
        ("question", "must"), ("paper_id", "must"),
        ("problem_category", "optional"), ("keywords", "optional"))),
    "ProblemCategory": ("问题类别（从 Paper.problem_category 聚类）", (
        ("code", "must"), ("label", "must"), ("n_papers", "optional"))),
    "LeaderboardEntry": ("榜单行（从 Benchmark.model_results 展开）", (
        ("benchmark", "must"), ("model", "must"), ("metric", "must"),
        ("value", "must"), ("unit", "optional"), ("is_sota", "optional"),
        ("paper_id", "optional"))),
    "MetricDefinition": ("指标定义（从 Benchmark.metrics 去重归一）", (
        ("name", "must"), ("direction", "should"), ("unit", "optional"),
        ("n_benchmarks", "optional"), ("sota_model", "optional"))),
    "DataContract": ("数据契约（从 Benchmark 输入输出/规模字段聚合）", (
        ("benchmark", "must"), ("input_form", "should"),
        ("output_form", "should"), ("n_samples", "optional"),
        ("scale", "optional"), ("modality", "optional"))),
    "Evidence": ("证据（从 Observation 溯源字段提升）", (
        ("quote", "must"), ("kind", "should"), ("paper_id", "optional"),
        ("source", "optional"))),
    "Limitation": ("局限（从 Algorithm.limitations 文本提升）", (
        ("statement", "must"), ("algorithm", "must"), ("kind", "optional"))),
    "SourcePaper": ("出处论文（从 Paper-RELATED_TO->Paper 科技树）", (
        ("title", "must"), ("ref_paper", "optional"),
        ("relation", "optional"), ("resolved", "optional"))),
}

APP_RELATIONS: Dict[str, Tuple[str, str, str]] = {
    "FORMULATES": ("Paper", "ResearchQuestion", "论文提出研究问题"),
    "IN_CATEGORY": ("ResearchQuestion", "ProblemCategory", "问题所属类别"),
    "HAS_ENTRY": ("Benchmark", "LeaderboardEntry", "基准包含榜单行"),
    "USES_METRIC": ("LeaderboardEntry", "MetricDefinition", "该行用哪个指标"),
    "HAS_METRIC": ("Benchmark", "MetricDefinition", "基准使用指标"),
    "HAS_CONTRACT": ("Benchmark", "DataContract", "基准的数据契约"),
    "SUPPORTED_BY": ("LeaderboardEntry", "Evidence", "数值的证据"),
    "HAS_LIMITATION": ("Algorithm", "Limitation", "算法的局限"),
    "SITUATED_IN": ("Paper", "SourcePaper", "论文在科技树中的位置"),
}


def snapshot() -> Dict[str, Any]:
    return {"version": APP_VERSION,
            "n_classes": len(APP_CLASSES),
            "n_relations": len(APP_RELATIONS),
            "classes": sorted(APP_CLASSES),
            "derived_from": "semantic v4.0",
            "miners": ["questions", "categories", "leaderboard",
                       "metrics", "contracts", "evidence", "limitations",
                       "source_papers"]}


def class_snapshot() -> Dict[str, Any]:
    return {k: {"definition": d,
                "fields": [{"name": f, "level": lv} for f, lv in fs]}
            for k, (d, fs) in APP_CLASSES.items()}


def check_domain_range(src: str, rel: str, dst: str) -> bool:
    r = APP_RELATIONS.get(rel)
    if not r:
        return False
    return src == r[0] and dst == r[1]
