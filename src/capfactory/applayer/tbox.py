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
        ("min_fidelity", "optional"), ("sample_size_norm", "optional"),
        ("control_design_norm", "optional"),
        ("effect_reporting_norm", "optional"),
        ("negative_result_norm", "optional"),
        ("exemplar_venues", "optional"))),
    "FigureAsset": ("图表资产（08）", (
        ("fig_label", "must"), ("caption", "optional"), ("kind", "optional"),
        ("for_contribution", "optional"), ("placement", "optional"))),
    # 任务级实例：只在「本次写作」真正引用时才建，不随全量挖掘产出
    "CitedPaper": ("本次写作实际引用的论文（按 run 实例化）", (
        ("run_id", "must"), ("cite_key", "must"), ("title", "must"),
        ("doi", "optional"), ("authors", "optional"), ("year", "optional"),
        ("venue", "optional"), ("layers", "optional"),
        ("existence", "optional"), ("metadata_ok", "optional"),
        ("context_ok", "optional"), ("context_quote", "optional"),
        ("cited_in", "optional"), ("recency_ratio", "optional"))),
    "SectionDraft": ("本次写作的章节实例（按 run 实例化）", (
        ("run_id", "must"), ("section", "must"), ("section_plan", "optional"),
        ("claims", "optional"), ("word_budget", "optional"),
        ("status", "optional"), ("cited", "optional"),
        ("evidence", "optional"))),
    "FailureCheck": ("本次自检结果（按 run 实例化）", (
        ("run_id", "must"), ("status", "must"), ("note", "optional"),
        ("checked_at", "optional"))),
    "ConsultedPaper": ("本次查过但未引的论文（按 run 实例化）", (
        ("run_id", "must"), ("paper_id", "must"), ("reason", "optional"),
        ("used_in", "optional"))),
    "RelatedPaper": ("本次检索召回的候选论文（task-r，不等于最终引用）", (
        ("run_id", "must"), ("paper_id", "must"), ("query", "optional"),
        ("score", "optional"), ("bm25", "optional"), ("vector", "optional"),
        ("domain_hint", "optional"), ("rank", "optional"),
        ("decision", "optional"), ("retrieved_at", "optional"))),
    "ResearchGap": ("本次写作要填补的空白（按 run 实例化）", (
        ("run_id", "must"), ("gap_id", "must"), ("gap_type", "must"),
        ("statement", "must"), ("evidence", "optional"),
        ("priority", "optional"), ("source_papers", "optional"),
        ("selected_at", "optional"))),
    "SectionPlan": ("章节计划（06）", (
        ("section", "must"), ("claims", "optional"),
        ("evidence_refs", "optional"), ("word_budget", "optional"))),
    "ReviewPoint": ("审稿关注点（09）", (
        ("axis", "must"), ("attack", "must"), ("response", "optional"),
        ("severity", "optional"))),
    # ===== 代码域（7 类，见 docs/schema/CODE_DOMAIN.md）=====
    "CodeUnit": ("代码文件/包（本地仓库实际结构）", (
        ("path", "must"), ("lang", "optional"),
        ("role", "optional"), ("loc", "optional"), ("sha256", "optional"))),
    "CodeSymbol": ("类/函数/方法（符号级）", (
        ("name", "must"), ("kind", "must"), ("signature", "optional"),
        ("qualname", "optional"), ("loc", "optional"), ("sha256", "optional"))),
    "Dependency": ("第三方依赖", (
        ("name", "must"), ("version", "optional"),
        ("declared_in", "optional"), ("used_by", "optional"))),
    "EntryPoint": ("可执行入口", (
        ("path", "must"), ("cmd", "optional"),
        ("args", "optional"), ("cwd", "optional"))),
    "TestUnit": ("测试单元", (
        ("name", "must"), ("path", "optional"),
        ("covers", "optional"), ("status", "optional"))),
    "EnvSpec": ("运行环境", (
        ("python", "optional"), ("cuda", "optional"),
        ("packages", "optional"), ("device", "optional"))),
    "RunArtifact": ("运行产物（按 run 实例化）", (
        ("run_id", "must"), ("kind", "must"), ("path", "optional"),
        ("sha256", "optional"), ("produced_by", "optional"))),
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
    "CITES": ("SectionPlan", "CitedPaper", "该节实际引用了哪篇"),
    "SEEKS_FROM": ("ResearchGap", "Paper", "该空白从哪些论文的论述中提炼"),
    "GAP_SUPPORTED_BY": ("ResearchGap", "CitedPaper", "该空白由哪些文献支撑"),
    "ANCHORS": ("ResearchGap", "Contribution", "该空白锚定了哪条贡献"),
    "OUTLINES": ("Paper", "SectionPlan", "论文的章节计划"),
    "CHALLENGED_BY": ("Contribution", "ReviewPoint", "该贡献可能被如何质疑"),
    "DRAFTS": ("Paper", "SectionDraft", "本次写作的章节实例"),
    "INSTANCE_OF": ("SectionDraft", "SectionPlan", "实例化的骨架"),
    "USES_EVIDENCE": ("SectionDraft", "Evidence", "该节用到的证据"),
    "CONSULTED": ("SectionDraft", "ConsultedPaper", "该节查过的论文"),
    "CHECKED": ("Paper", "FailureCheck", "本次失败模式自检"),
    "CHECK_OF": ("FailureCheck", "FailureMode", "检查的是哪条失败模式"),
    "RETRIEVED": ("SectionDraft", "RelatedPaper", "该节检索到哪些候选"),
    "ABOUT": ("RelatedPaper", "Paper", "候选指向库内哪篇论文"),
    "LED_TO": ("RelatedPaper", "CitedPaper", "该候选最终是否被引"),
    # ===== 代码域：域内 9 =====
    "CONTAINS": ("CodeUnit", "CodeSymbol", "文件包含符号"),
    "IMPORTS": ("CodeUnit", "CodeUnit", "同仓库文件依赖"),
    "CALLS": ("CodeSymbol", "CodeSymbol", "符号调用"),
    "INHERITS": ("CodeSymbol", "CodeSymbol", "类继承"),
    "DEPENDS_ON": ("CodeUnit", "Dependency", "三方依赖"),
    "IN_UNIT": ("EntryPoint", "CodeUnit", "入口所在文件"),
    "USES_ENV": ("EntryPoint", "EnvSpec", "入口所需环境"),
    "COVERS": ("TestUnit", "CodeSymbol", "测试覆盖"),
    "TEST_IN": ("TestUnit", "CodeUnit", "测试所在文件"),
    # ===== 代码域：跨域 8 =====
    "IMPLEMENTED_BY": ("AlgorithmModule", "CodeSymbol", "模块由哪个符号实现（本地）"),
    "EXECUTED_BY": ("ExperimentArm", "EntryPoint", "实验组靠哪个入口跑"),
    "PRODUCES": ("ExperimentArm", "RunArtifact", "实验组产出的产物"),
    "REPRODUCED_BY": ("LeaderboardEntry", "RunArtifact", "数值由哪次运行产生"),
    "COMPUTED_BY": ("MetricDefinition", "CodeSymbol", "指标由哪个函数算"),
    "ASSUMED_IN": ("Assumption", "CodeUnit", "假设隐含在代码哪处"),
    "DETECTABLE_IN": ("FailureMode", "CodeUnit", "该失败模式在代码哪处可检测"),
    "GROUNDED_IN": ("Evidence", "CodeUnit", "证据来自代码哪处"),
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
