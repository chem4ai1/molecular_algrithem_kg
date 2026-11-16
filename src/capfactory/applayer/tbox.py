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
    # ===== S2：写作方法论节点（来自 docs/new/01-09）=====
    "Contribution": ("论文声称的贡献（04/06）", (
        ("statement", "must"), ("kind", "must"),
        ("novelty_basis", "optional"), ("section", "optional"),
        ("claimed_strength", "optional"), ("evidence", "optional"))),
    "ExperimentArm": ("实验组（05：main/baseline/ablation/hyperparam）", (
        ("kind", "must"), ("name", "must"), ("config", "optional"),
        ("n_seeds", "optional"), ("benchmark", "optional"),
        ("evidence", "optional"))),
    "Assumption": ("方法成立的前提（07 Type II）", (
        ("statement", "must"), ("scope", "optional"),
        ("applicability", "optional"), ("evidence", "optional"))),
    "FailureMode": ("领域失败模式（07）", (
        ("name", "must"), ("severity", "must"),
        ("detection", "optional"), ("domain_tags", "optional"))),
    "EvidenceNorm": ("领域证据规范（02/03）", (
        ("evidence_type", "must"), ("accepted_metrics", "optional"),
        ("min_fidelity", "optional"))),
    "FigureAsset": ("图表资产（08）", (
        ("fig_label", "must"), ("caption", "optional"), ("kind", "optional"),
        ("for_contribution", "optional"), ("placement", "optional"))),
    "CitationCheck": ("引用核验（08 三层）", (
        ("doi", "optional"), ("venue", "optional"), ("year", "optional"),
        ("existence", "optional"), ("metadata_ok", "optional"),
        ("context_ok", "optional"))),
    "SectionPlan": ("章节计划（06）", (
        ("section", "must"), ("claims", "optional"),
        ("evidence_refs", "optional"), ("word_budget", "optional"))),
    "ReviewPoint": ("审稿关注点（09）", (
        ("axis", "must"), ("attack", "must"), ("response", "optional"),
        ("severity", "optional"))),
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
    # ===== S2 关系 =====
    "DECLARES": ("Paper", "Contribution", "论文声明贡献"),
    "TESTED_BY": ("Contribution", "ExperimentArm", "该贡献由哪个实验组验证"),
    "RUNS": ("Paper", "ExperimentArm", "论文做了哪些实验组"),
    "ON": ("ExperimentArm", "Benchmark", "实验组跑在哪个基准"),
    "ASSUMES": ("Algorithm", "Assumption", "算法依赖的前提"),
    "CONFORMS_TO": ("Paper", "EvidenceNorm", "论文遵循的领域证据规范"),
    "APPLIES": ("EvidenceNorm", "FailureMode", "该规范下适用的失败模式"),
    "SHOWN_BY": ("Contribution", "FigureAsset", "该贡献由哪张图表支撑"),
    "CITES": ("Paper", "CitationCheck", "论文的引用核验"),
    "OUTLINES": ("Paper", "SectionPlan", "论文的章节计划"),
    "CHALLENGED_BY": ("Contribution", "ReviewPoint", "该贡献可能被如何质疑"),
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
