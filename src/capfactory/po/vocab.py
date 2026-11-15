"""五维受控词表与注册器.

词表取值来自 ``问题导向本体与知识图谱架构_20261109`` 的真实实例数据
（ontology.json / problems.csv / 指标观测表.csv / nodes.csv / 论文问题算法评测矩阵.csv），
而不是凭空拟定；``load_report_vocab()`` 可在运行时从报告包补充新取值。

每个词表区分：
- ``values``  规范值（英文 snake_case，作为存储与比较的唯一形式）；
- ``aliases`` 中文/原文写法 → 规范值；
- ``closed``  是否封闭（封闭词表出现未知值即校验失败，避免静默污染）。

归一示例::

    default_registry.normalize("availability", "是｜明确开源")      -> "open_licensed"
    default_registry.normalize("metric_direction", "越高越好")      -> "higher"
    default_registry.normalize("missing_state", "本轮未抽取")       -> "not_extracted"
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 1. 报告包里抽取出的规范词表
# ---------------------------------------------------------------------------

# 问题维度：11 大类 / 26 子问题（problems.csv）
PROBLEM_CATEGORIES = {
    "P01": "靶点/疾病因果不确定", "P02": "训练数据质量、覆盖与标签噪声",
    "P03": "泄漏与分布外泛化", "P04": "生成条件控制与多约束满足",
    "P05": "结构几何、柔性与构象集合", "P06": "代理指标与实测终点脱节",
    "P07": "合成、表达与筛选漏斗", "P08": "ADMET与多目标开发性",
    "P09": "多肽特有可开发性", "P10": "实验闭环、复现和开放资源",
    "P11": "临床转化与AI贡献归因",
}
PROBLEM_SUBPROBLEMS = (
    "P01a", "P01b", "P02a", "P02b", "P02c", "P03a", "P03b",
    "P04a", "P04b", "P04c", "P05a", "P05b", "P05c",
    "P06a", "P06b", "P06c", "P07a", "P07b", "P08a", "P08b",
    "P09a", "P09b", "P10a", "P10b", "P11a", "P11b",
)
PROBLEM_GROUPS = (
    "生物学与靶点", "数据与泛化", "建模与生成", "结构与物理", "评测设计",
    "实验与治理", "转化与实验", "多肽专项", "临床证据", "转化与药化",
)
PAPER_PROBLEM_RELATIONS = ("ADDRESSES", "EXPOSES_LIMITATION", "ANALYST_RELEVANT_TO")

# 知识维度：归属 / 缺失 / 证据层级
ATTRIBUTIONS = (
    # 报告 §5.3 明列的四种基本归属
    "author_explicit", "author_measured", "analyst_synthesis", "analyst_derived",
    # ontology.json / CapabilityClaim 使用的综合层级
    "evidence_bounded_synthesis", "analyst_synthesis_of_author_results_and_limitations",
    # edges.csv 实例中真实出现的更细归属（共 12 种，均由报告包校验通过）
    "bibliographic", "source_locator", "source_supports_scoped_synthesis",
    "analyst_derived_from_author_counts", "inherited_metadata",
    "inherited_repository_audit", "method_attempt", "missingness_record",
    "publisher_correction",
)
MISSING_STATES = (
    "not_reported", "not_read", "not_extracted", "not_applicable",
    "not_measured", "failed", "withheld", "unknown",
)
EVIDENCE_MODALITIES = (
    "computational", "biochemical", "in_vitro", "cellular", "ex_vivo",
    "animal", "clinical_safety_PK", "clinical_efficacy", "see_assay",
)
EVIDENCE_LEVELS = ("mixed; consult individual evaluations",) + EVIDENCE_MODALITIES[:-1]
SOURCE_KINDS = ("published_article", "author_manuscript", "supplement", "correction", "preprint")
COVERAGE_LEVELS = ("main_fulltext_key_sections", "partial_main_full_supp",
                   "pmc_main_and_supp", "author_v2_main", "abstract_only")

# 算法数据维度
TASK_FAMILIES = (
    "peptide", "molecular_discovery", "multi_molecular", "single_cell",
    "property_prediction", "structure_prediction", "binding_affinity",
    "interaction_prediction", "molecular_generation", "docking", "admet",
    "virtual_screening", "representation_learning", "sequence_design",
    "evaluation_protocol", "optimization",
)
ALGORITHM_ARCHITECTURES = (
    "diffusion", "flow_matching", "transformer", "graph_neural_network",
    "protein_language_model", "rfdiffusion", "generative_adversarial", "vae",
    "autoregressive", "equivariant_network", "ensemble", "classical_ml",
    "docking_search", "generative_platform", "reinforcement_learning", "other",
)
SPLIT_RULES = (
    "random_holdout", "time_split", "scaffold_split", "target_cluster_split",
    "pocket_split", "homology_filtered_split", "patient_stratified",
    "external_independent_test", "campaign_split", "not_reported", "not_applicable",
)
OVERLAP_RISKS = ("none_declared", "possible", "high", "audited", "not_independently_rerun")
VERSION_STATUSES = ("as described by cited paper", "paper-specific; commit not fixed",
                    "supplement/source version", "pinned_commit", "versioned_release", "unknown")
OBJECTIVE_DIRECTIONS = ("maximize", "minimize", "context_dependent", "constraint")

# 代码维度：开放性多轴（报告 §5.5 明确反对"开源/闭源"二值）
AVAILABILITIES = (
    "open_licensed", "open_license_unverified", "open_restricted_use",
    "closed_commercial", "auxiliary_only", "not_read", "see_original_article",
)
LICENSES = (
    "MIT", "BSD-3-Clause", "Apache-2.0", "GPL-3.0", "CC-BY-4.0",
    "academic_noncommercial", "commercial_platform", "noncommercial_weights",
    "license_unverified", "not_read", "other",
)
ARTIFACT_KINDS = ("core", "auxiliary", "weights", "training_data", "dependency",
                  "environment", "output_artifact")
ARTIFACT_SCOPES = ("core_implementation", "auxiliary_scripts", "weights_only",
                   "data_only", "full_platform", "unspecified")
CODE_STATUSES = ("open_licensed", "open_license_unverified", "open_restricted_use",
                 "closed_commercial")

# 领域维度（D0–D10）：论文/能力/算法所属应用领域
DOMAIN_NAMES = {
    "D0": "通用算法（跨领域）",
    "D1": "分子生成与从头设计",
    "D2": "分子优化与多目标",
    "D3": "结构基/靶点条件设计",
    "D4": "分子性质/ADMET/毒性",
    "D5": "多肽与抗菌肽",
    "D6": "蛋白/抗体/RNA",
    "D7": "合成与逆合成/反应",
    "D8": "表征学习/数据集/基准",
    "D9": "AI4S/科学智能体",
    "D10": "材料/晶体/分子动力学",
}
# 算法族（A01–A18）：方法身份，与 Algorithm.architecture 互补
ALGO_NAMES = {
    "A01": "自回归/Transformer/LLM",
    "A02": "VAE/隐变量",
    "A03": "GAN/对抗",
    "A04": "扩散/分数模型",
    "A05": "流匹配/连续流/最优传输",
    "A06": "GFlowNet",
    "A07": "强化学习/偏好优化",
    "A08": "贝叶斯优化/主动学习",
    "A09": "GNN/消息传递",
    "A10": "等变/几何深度学习",
    "A11": "进化/遗传/树搜索",
    "A12": "对比/自监督预训练",
    "A13": "多模态/图文分子",
    "A14": "Agent/工具调用/RAG",
    "A15": "知识图谱/符号",
    "A16": "物理信息/神经算子/模拟",
    "A17": "不确定性/校准/OOD",
    "A18": "经典ML/描述符",
}

# 现有 task_family → 领域码（一对一主映射，多标签由 taxonomy 规则补充）
TASK_FAMILY_TO_DOMAIN = {
    "peptide": "D5", "property_prediction": "D4", "admet": "D4",
    "structure_prediction": "D3", "binding_affinity": "D3",
    "interaction_prediction": "D3", "docking": "D3",
    "molecular_generation": "D1", "sequence_design": "D5",
    "optimization": "D2", "virtual_screening": "D2",
    "representation_learning": "D8", "evaluation_protocol": "D8",
    "multi_molecular": "D6", "single_cell": "D9",
    "other": "D0",
}
# 现有 algorithm_family → 算法族码（细粒度由 architecture / 文本规则补充）
ALGORITHM_FAMILY_TO_CODE = {
    "descriptor": "A18", "classical_ml": "A18", "statistical": "A18",
    "ensemble": "A18", "deep_learning": "A01", "geometric_dl": "A10",
    "generative": "A04", "optimization": "A08", "simulation": "A16",
    "retrieval": "A14", "hybrid": "A14",
    # 已存在于 PO algorithm_architecture 的取值
    "diffusion": "A04", "flow_matching": "A05", "transformer": "A01",
    "graph_neural_network": "A09", "protein_language_model": "A01",
    "rfdiffusion": "A04", "generative_adversarial": "A03", "vae": "A02",
    "autoregressive": "A01", "equivariant_network": "A10",
    "docking_search": "A16", "generative_platform": "A14",
    "reinforcement_learning": "A07", "other": "A18",
}

# 指标维度
METRIC_DIRECTIONS = ("higher", "lower", "context_dependent")
UNIT_SCALES = ("ratio 0–1", "percent 0–100", "see observation unit", "concentration",
               "energy", "count", "score_as_reported")
VALUE_TYPES = ("number", "fraction", "count", "score", "boolean", "categorical")
AGGREGATIONS = (
    "derived_fraction", "reported_percent", "rounded_percent", "reported_value",
    "reported_aggregate", "mean", "correlation", "classification", "coverage_count",
    "median", "not_reported",
)
UNITS = ("1", "ratio", "count", "percent", "nM", "μM", "kcal/mol",
         "score_as_reported", "Å", "M", "mg/kg", "h", "not_applicable")
METRIC_NAMES = (
    # 报告 41 条观测中出现的 22 个指标
    "AMP_hit_fraction", "AMP_hit_percent", "AUPRC", "AUROC", "IC50", "Kd",
    "PB_valid_fraction", "Pearson_r", "QED", "Vina_Dock", "affinity_band_count",
    "binder_hit_fraction", "binder_nomination_fraction", "chirality_violation_percent",
    "docking_score", "evaluable_target_count", "interaction_recovery_percent",
    "low_haemolysis_percent", "pose_joint_success_percent", "pose_success_percent",
    "structural_hit_percent", "tumour_growth_inhibition_percent",
    # 现有验证器常用指标
    "roc_auc", "accuracy", "f1", "mcc", "rmse", "mae", "spearman", "rmsd",
    "tm_score", "validity", "uniqueness", "novelty", "diversity", "enrichment_factor",
)
STAGES = (
    "unranked_generated", "ranked_selected", "nominated", "synthesized", "tested",
    "selected_tested", "hit", "computational", "first_round", "not_applicable",
)
STAGE_TYPES = ("nominated", "synthesized", "hit", "generated", "tested")
OUTCOME_TYPES = ("synthesis_insufficient", "negative_measured", "not_measured",
                 "failed_assay", "withheld", "not_reported")
EVALUATION_KINDS = ("author_reported_not_rerun", "independent_rerun",
                    "in_house_replication", "platform_verification")
ENDPOINT_TYPES = ("binding_affinity", "pose_quality", "geometric_validity",
                  "antimicrobial_activity", "haemolysis", "cytotoxicity",
                  "solubility", "stability", "permeability", "pk_exposure",
                  "clinical_safety", "clinical_efficacy", "synthesis_yield")
ASSAY_KINDS = ("computational_benchmark", "biochemical_assay", "cell_assay",
               "animal_model", "clinical_study", "physical_structure")

# 可比性维度（报告 CQ3）
COMPARABILITY_DIMENSIONS = (
    "metric", "dataset_id", "dataset_version", "split_type", "input_condition",
    "sample_budget", "top_k", "threshold", "stage", "assay_id", "endpoint_id",
    "condition_hash", "subject", "target", "direction",
)

# 概念类与关系（ontology.json：34 类 / 38 关系；含报告新增 Assertion 共 35）
CONCEPT_CLASSES_FALLBACK = (
    "Paper", "PaperVersion", "ProblemCategory", "ResearchProblem", "ResearchQuestion",
    "ProblemContext", "Task", "Algorithm", "Workflow", "CapabilityClaim", "Limitation",
    "Dataset", "DatasetSplit", "EvaluationRun", "MetricDefinition", "MetricObservation",
    "ExperimentalCondition", "Assay", "Endpoint", "Molecule", "CandidateSet",
    "MoleculeState", "Target", "Evidence", "EvidenceFamily", "CodeArtifact",
    "WeightArtifact", "DataArtifact", "DesignCampaign", "SelectionStage",
    "NegativeOutcome", "Objective", "Organism", "Assertion",
    "Domain", "AlgorithmFamily", "Benchmark", "LeaderboardEntry",
)
RELATION_TYPES_FALLBACK = (
    "HAS_VERSION", "FORMULATES", "MOTIVATED_BY", "OPERATIONALIZED_AS", "ADDRESSED_BY",
    "IMPLEMENTS", "PROPOSES_WORKFLOW", "ABOUT_METHOD", "HAS_CLAIM", "EVALUATED_IN",
    "SUPPORTED_BY", "EXTRACTED_FROM", "USES_METRIC", "PRODUCES_OBSERVATION", "OF_METRIC",
    "HAS_CONDITION", "HAS_ASSAY", "MEASURES_ENDPOINT", "ABOUT_SUBJECT", "FOR_TARGET",
    "USES_DATASET", "HAS_SPLIT", "QUALIFIES", "BROADER", "ADDRESSES",
    "EXPOSES_LIMITATION", "ANALYST_RELEVANT_TO", "HAS_CODE", "HAS_WEIGHTS", "HAS_DATA",
    "MEMBER_OF", "REPORTS_CAMPAIGN", "HAS_STAGE", "HAS_NEGATIVE_OUTCOME",
    "HAS_OBJECTIVE", "HAS_STATE", "ON_ORGANISM", "CORRECTED_BY",
    "IN_DOMAIN", "USES_ALGO_FAMILY",
    "EVALUATED_ON", "BENCHMARK_FOR", "HAS_LEADERBOARD", "REPORTED_BY", "FROM_OBSERVATION",
)

# ---------------------------------------------------------------------------
# 2. 别名（报告中的中文/原始写法 → 规范值）
# ---------------------------------------------------------------------------
_ALIASES: Dict[str, Dict[str, str]] = {
    "availability": {
        "是｜明确开源": "open_licensed",
        "代码公开｜开源许可待核实": "open_license_unverified",
        "代码公开｜用途受限": "open_restricted_use",
        "否｜核心商业平台未开源（部分有辅助脚本）": "closed_commercial",
        "not_read": "not_read", "see_original_article": "see_original_article",
    },
    "license": {
        "BSD-3-Clause": "BSD-3-Clause", "MIT": "MIT",
        "MIT（论文明确声明）": "MIT", "源码 Apache-2.0；权重/输出非商业条款": "Apache-2.0",
        "仓库未见明确项目许可证": "license_unverified",
        "作者双许可：学术非商业/商业另行授权": "academic_noncommercial",
        "PandaOmics / Chemistry42 商业平台": "commercial_platform",
        "核心平台商业许可": "commercial_platform",
        "核心 Chemistry42 商业；第三方工具各自许可": "commercial_platform",
        "核心平台商业；其他代码/数据 CC-BY-4.0": "commercial_platform",
        "non-commercial terms reported in original": "noncommercial_weights",
    },
    "metric_direction": {"越高越好": "higher", "越大越好": "higher", "越低越好": "lower",
                         "越小越好": "lower", "依上下文": "context_dependent",
                         # 抽取时模型常把优化目标方向写成 maximize/minimize
                         "maximize": "higher", "maximise": "higher",
                         "minimize": "lower", "minimise": "lower",
                         "max": "higher", "min": "lower"},
    "missing_state": {
        "本轮未抽取": "not_extracted", "原文未报告": "not_reported",
        "未测": "not_measured", "未读到": "not_read", "不适用": "not_applicable",
        "实际失败": "failed", "未公开": "withheld", "未知": "unknown",
    },
    "task_family": {"多肽": "peptide", "分子发现": "molecular_discovery",
                    "单细胞": "single_cell", "多分子": "multi_molecular"},
    "algorithm_architecture": {
        "RFdiffusion": "rfdiffusion", "diffusion model": "diffusion",
        "flow matching": "flow_matching", "GNN": "graph_neural_network",
        "protein language model": "protein_language_model", "PLM": "protein_language_model",
        "transformer": "transformer", "ensemble": "ensemble", "GAN": "generative_adversarial",
    },
    "split_type": {"随机80/20": "random_holdout", "随机拆分": "random_holdout",
                   "时间切分": "time_split", "骨架切分": "scaffold_split",
                   "靶点簇切分": "target_cluster_split", "口袋切分": "pocket_split",
                   "同源过滤": "homology_filtered_split"},
    "overlap_risk": {"not independently rerun": "not_independently_rerun",
                     "未独立复跑": "not_independently_rerun"},
    "attribution": {"分析者归纳": "analyst_synthesis", "作者明确": "author_explicit",
                    "作者实测": "author_measured", "分析者派生": "analyst_derived"},
    "unit": {"ratio": "1", "分数": "1", "%": "percent", "百分比": "percent"},
    "source_kind": {"期刊版": "published_article", "作者稿": "author_manuscript",
                    "补充材料": "supplement", "更正通知": "correction",
                    "预印本": "preprint",
                    # 实例里真实出现、但规范名不同的写法
                    "arxiv_preprint": "preprint", "arxiv": "preprint",
                    "author_draft": "author_manuscript", "manuscript": "author_manuscript",
                    "journal_article": "published_article",
                    "conference_paper": "published_article",
                    "published": "published_article"},
    # qwen38 抽出的数值类型写法（continuous/float 实为 number）
    "value_type": {"float": "number", "continuous": "number", "real": "number",
                   "integer": "count", "int": "count", "percentage": "fraction",
                   "percent": "fraction", "ratio": "fraction", "bool": "boolean",
                   "discrete": "categorical", "category": "categorical"},
    # 湿实验写法统一到体外/生化
    "evidence_modality": {"wet_lab": "in_vitro", "wetlab": "in_vitro",
                          "in-vitro": "in_vitro", "in vivo": "animal",
                          "computational_prediction": "computational",
                          "simulation": "computational", "assay": "biochemical"},
    "aggregation": {"派生比例": "derived_fraction", "四舍五入百分比": "rounded_percent",
                    "均值": "mean", "相关系数": "correlation"},
    # 领域码：中文名与既有 task_family 值均可归一
    "domain_code": {**{name: code for code, name in DOMAIN_NAMES.items()},
                    **TASK_FAMILY_TO_DOMAIN},
    # 算法族码：中文名与既有 algorithm_family / architecture 值均可归一
    "algo_code": {**{name: code for code, name in ALGO_NAMES.items()},
                  **ALGORITHM_FAMILY_TO_CODE,
                  # 论文里高频的缩写与同义写法
                  "gan": "A03", "gans": "A03", "generative adversarial network": "A03",
                  "vae": "A02", "vaes": "A02", "variational autoencoder": "A02",
                  "autoregressive model": "A01", "transformer": "A01", "llm": "A01",
                  "gnn": "A09", "gcn": "A09", "graph convolutional network": "A09",
                  "graph neural network": "A09", "mpnn": "A09",
                  "diffusion model": "A04", "ddpm": "A04", "score-based": "A04",
                  "flow matching": "A05", "normalizing flow": "A05",
                  "reinforcement learning": "A07", "rl": "A07", "ppo": "A07",
                  "bayesian optimization": "A08", "active learning": "A08",
                  "mcts": "A11", "genetic algorithm": "A11", "evolutionary": "A11",
                  "equivariant network": "A10", "se(3)": "A10", "e(3)": "A10",
                  "knowledge graph": "A15", "kg": "A15",
                  "random forest": "A18", "svm": "A18", "xgboost": "A18",
                  "descriptor": "A18", "fingerprint": "A18"},
}

_VOCAB_SPECS: Tuple[Tuple[str, str, Sequence[str], bool], ...] = (
    ("problem_category", "问题大类 P01–P11", tuple(PROBLEM_CATEGORIES), True),
    ("problem_subproblem", "26 个可检验研究子问题", PROBLEM_SUBPROBLEMS, True),
    ("problem_group", "问题所属分析类别", PROBLEM_GROUPS, False),
    ("problem_status", "问题解决状态", ("open_or_partially_addressed", "open",
                                    "partially_addressed", "addressed", "unverified"), False),
    ("paper_problem_relation", "论文—问题边的三种语义", PAPER_PROBLEM_RELATIONS, True),
    ("attribution", "断言归属：作者 vs 分析者", ATTRIBUTIONS, True),
    ("missing_state", "缺失状态（缺失 ≠ false）", MISSING_STATES, True),
    ("evidence_modality", "证据层级（不可压成总分）", EVIDENCE_MODALITIES, True),
    ("evidence_level", "能力主张的证据层级汇总", EVIDENCE_LEVELS, False),
    ("source_kind", "论文版本类型", SOURCE_KINDS, True),
    ("coverage_level", "阅读覆盖等级", COVERAGE_LEVELS, False),
    ("task_family", "任务族", TASK_FAMILIES, False),
    ("algorithm_architecture", "算法架构族", ALGORITHM_ARCHITECTURES, False),
    ("split_type", "数据集划分规则", SPLIT_RULES, False),
    ("overlap_risk", "泄漏/同源重叠风险", OVERLAP_RISKS, False),
    ("version_status", "版本可固定程度", VERSION_STATUSES, False),
    ("objective_direction", "优化目标方向", OBJECTIVE_DIRECTIONS, True),
    ("availability", "代码/权重/数据开放性（多轴）", AVAILABILITIES, True),
    ("license", "许可证", LICENSES, False),
    ("artifact_kind", "代码资源类型", ARTIFACT_KINDS, True),
    ("artifact_scope", "资源覆盖范围", ARTIFACT_SCOPES, False),
    ("code_status", "源码开放状态", CODE_STATUSES, True),
    ("metric_direction", "指标优化方向", METRIC_DIRECTIONS, True),
    ("unit_scale", "指标量纲", UNIT_SCALES, False),
    ("value_type", "观测值类型", VALUE_TYPES, True),
    ("aggregation", "观测聚合方式", AGGREGATIONS, False),
    ("unit", "观测单位", UNITS, False),
    ("metric_name", "指标规范名", METRIC_NAMES, False),
    ("stage", "筛选漏斗阶段", STAGES, False),
    ("stage_type", "筛选阶段类型", STAGE_TYPES, False),
    ("outcome_type", "负结果类型", OUTCOME_TYPES, False),
    ("evaluation_kind", "评测性质", EVALUATION_KINDS, True),
    ("endpoint_type", "观测终点类型", ENDPOINT_TYPES, False),
    ("assay_kind", "测定/评测方法类型", ASSAY_KINDS, False),
    ("comparability_dimension", "指标可比性维度", COMPARABILITY_DIMENSIONS, True),
    ("domain_code", "领域分类 D0–D10", tuple(DOMAIN_NAMES), True),
    ("algo_code", "算法族 A01–A18", tuple(ALGO_NAMES), True),
    ("concept_class", "PO 概念类", CONCEPT_CLASSES_FALLBACK, True),
    ("relation_type", "PO 关系类型", RELATION_TYPES_FALLBACK, True),
    ("identifier_status", "分子/靶标标识符解析状态",
     ("unresolved_local_name", "sequence_only", "smiles_only", "registry_id_verified",
      "local label; chemical structure/registry ID unresolved"), False),
    ("independence_status", "证据独立性",
     ("independent", "shared_platform", "shared_data", "shared_team", "unknown"), False),
)


def _slug(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return s or "unknown"


@dataclass
class Vocabulary:
    """一个受控词表。"""

    name: str
    description: str = ""
    values: Tuple[str, ...] = ()
    aliases: Dict[str, str] = field(default_factory=dict)
    closed: bool = True
    source: str = "研究报告.md §5 / ontology.json / 实例 CSV"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VocabularyRegistry:
    """词表注册、归一与校验。"""

    def __init__(self) -> None:
        self._v: Dict[str, Vocabulary] = {}
        for name, desc, values, closed in _VOCAB_SPECS:
            self.register(Vocabulary(name=name, description=desc, values=tuple(values),
                                     aliases=dict(_ALIASES.get(name, {})), closed=closed))

    def register(self, v: Vocabulary) -> None:
        self._v[v.name] = v

    def get(self, name: str) -> Optional[Vocabulary]:
        return self._v.get(name)

    def names(self) -> List[str]:
        return sorted(self._v)

    def values(self, name: str) -> Tuple[str, ...]:
        v = self._v.get(name)
        return v.values if v else ()

    def normalize(self, name: str, value: Any) -> Tuple[Optional[str], bool]:
        """返回 ``(规范值, 是否合法)``。非封闭词表会把新值 slug 化后动态登记。"""
        v = self._v.get(name)
        if v is None:
            return None, False
        if value is None:
            return None, False
        raw = str(value).strip()
        if raw in v.values:
            return raw, True
        if raw in v.aliases:
            return v.aliases[raw], True
        # 忽略大小写/分隔符的宽松匹配
        low = raw.lower()
        for canonical in v.values:
            if canonical.lower() == low:
                return canonical, True
        for alias, canonical in v.aliases.items():
            if alias.lower() == low:
                return canonical, True
        # 编号零填充归一：D01 → D1，A5 → A05
        if re.fullmatch(r"[A-Z]\d{1,3}", raw):
            for cand in (f"{raw[0]}{int(raw[1:])}", f"{raw[0]}{int(raw[1:]):02d}"):
                if cand in v.values:
                    return cand, True
        if not v.closed:
            canonical = _slug(raw)
            v.values = tuple(dict.fromkeys(v.values + (canonical,)))
            v.aliases[raw] = canonical
            return canonical, True
        return None, False

    def validate(self, name: str, value: Any) -> List[str]:
        canonical, ok = self.normalize(name, value)
        if ok:
            return []
        v = self._v[name]
        return [f"{name}={value!r} 不在受控词表（{len(v.values)} 项）；"
                f"已有别名 {len(v.aliases)} 条；可先登记别名再写入"]

    def add_aliases(self, name: str, aliases: Dict[str, str]) -> int:
        v = self._v.get(name)
        if not v:
            return 0
        n = 0
        for raw, canonical in aliases.items():
            canonical, ok = self.normalize(name, canonical)
            if ok and canonical and raw not in v.aliases:
                v.aliases[raw] = canonical
                n += 1
        return n

    def add_values(self, name: str, values: Iterable[str]) -> int:
        v = self._v.get(name)
        if not v:
            return 0
        before = len(v.values)
        v.values = tuple(dict.fromkeys(v.values + tuple(str(x) for x in values if x)))
        return len(v.values) - before

    def summary(self) -> Dict[str, Any]:
        return {
            "n_vocabularies": len(self._v),
            "total_values": sum(len(v.values) for v in self._v.values()),
            "vocabularies": {k: {"n": len(v.values), "closed": v.closed,
                                 "aliases": len(v.aliases), "description": v.description}
                             for k, v in sorted(self._v.items())},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {k: v.to_dict() for k, v in sorted(self._v.items())}


default_registry = VocabularyRegistry()


# ---------------------------------------------------------------------------
# 3. 从报告包导入真实词表取值
# ---------------------------------------------------------------------------
def load_report_vocab(report_dir: str | Path,
                      registry: Optional[VocabularyRegistry] = None) -> Dict[str, Any]:
    """从报告交付包补充词表（幂等）。返回导入统计。

    读取：ontology.json（类/关系/missingStates）、problems.csv（问题树）、
    指标观测表.csv（指标/模态/单位/聚合/阶段）、nodes.csv（归属/可用性/许可等）、
    论文问题算法评测矩阵.csv（代码状态/许可/任务族）。
    """
    reg = registry or default_registry
    root = Path(report_dir)
    stats: Dict[str, Any] = {"root": str(root), "files": {}, "added": {}, "aliases": 0}

    def rows(name: str) -> List[Dict[str, str]]:
        p = root / name
        if not p.exists():
            return []
        with p.open(encoding="utf-8-sig", newline="") as fh:
            data = list(csv.DictReader(fh))
        stats["files"][name] = len(data)
        return data

    onto_path = root / "ontology.json"
    if onto_path.exists():
        onto = json.loads(onto_path.read_text(encoding="utf-8"))
        stats["added"]["concept_class"] = reg.add_values(
            "concept_class", [c["id"] for c in onto.get("classes", [])])
        stats["added"]["relation_type"] = reg.add_values(
            "relation_type", [r["id"] for r in onto.get("relations", [])])
        stats["added"]["missing_state"] = reg.add_values(
            "missing_state", onto.get("missingStates", []))
        stats["ontology_version"] = onto.get("version")

    edges = rows("edges.csv")
    if edges:
        stats["added"]["attribution_from_edges"] = reg.add_values(
            "attribution", [e["attribution"] for e in edges])
        reg.add_values("relation_type", [e["relation"] for e in edges])

    probs = rows("problems.csv")
    if probs:
        stats["added"]["problem_category"] = reg.add_values(
            "problem_category", [r["parent"] for r in probs])
        stats["added"]["problem_subproblem"] = reg.add_values(
            "problem_subproblem", [r["id"] for r in probs])
        reg.add_values("attribution", [r["attribution"] for r in probs])

    obs = rows("指标观测表.csv")
    if obs:
        stats["added"]["metric_name"] = reg.add_values("metric_name", [r["metric"] for r in obs])
        reg.add_values("evidence_modality", [r["modality"] for r in obs])
        reg.add_values("unit", [r["unit"] for r in obs])
        for r in obs:
            try:
                extra = json.loads(r.get("extra") or "{}")
            except json.JSONDecodeError:
                extra = {}
            for key, vocab in (("aggregation", "aggregation"), ("stage", "stage"),
                              ("split", "split_type")):
                if extra.get(key):
                    reg.add_values(vocab, [str(extra[key])])
            try:
                missing = json.loads(r.get("missingReasons") or "{}")
            except json.JSONDecodeError:
                missing = {}
            reg.add_values("missing_state", list(missing.values()))

    nodes = rows("nodes.csv")
    if nodes:
        field_to_vocab = {
            "attribution": "attribution", "availability": "availability",
            "license": "license", "evaluationKind": "evaluation_kind",
            "stageType": "stage_type", "outcomeType": "outcome_type",
            "evidenceLevel": "evidence_level", "modality": "evidence_modality",
            "sourceKind": "source_kind", "direction": "metric_direction",
            "unitScale": "unit_scale", "valueType": "value_type",
            "status": "problem_status", "category": "problem_group",
            "taskFamily": "task_family", "versionStatus": "version_status",
            "leakageAudit": "overlap_risk", "coverageLevel": "coverage_level",
            "identifierStatus": "identifier_status", "aggregation": "aggregation",
            "independenceStatus": "independence_status", "scope": "artifact_scope",
        }
        aliases: Dict[str, Dict[str, str]] = {}
        seen: Dict[str, set] = {}
        for n in nodes:
            try:
                props = json.loads(n.get("properties") or "{}")
            except json.JSONDecodeError:
                props = {}
            for field, vocab in field_to_vocab.items():
                val = props.get(field)
                if not isinstance(val, str) or not val.strip():
                    continue
                canonical, ok = reg.normalize(vocab, val)
                if ok and canonical and val != canonical:
                    aliases.setdefault(vocab, {})[val] = canonical
                elif not ok and reg.get(vocab) and not reg.get(vocab).closed:
                    canonical, _ = reg.normalize(vocab, val)
                    if canonical:
                        aliases.setdefault(vocab, {})[val] = canonical
                if canonical and field in ("availability", "license"):
                    seen.setdefault(field, set()).add(canonical)
        for vocab, mapping in aliases.items():
            stats["aliases"] += reg.add_aliases(vocab, mapping)
        stats["observed_canonical"] = {k: sorted(v) for k, v in seen.items()}

    matrix = rows("论文问题算法评测矩阵.csv")
    if matrix:
        code_alias = {
            "是｜明确开源": "open_licensed",
            "代码公开｜开源许可待核实": "open_license_unverified",
            "代码公开｜用途受限": "open_restricted_use",
            "否｜核心商业平台未开源（部分有辅助脚本）": "closed_commercial",
        }
        stats["aliases"] += reg.add_aliases("code_status", code_alias)
        stats["aliases"] += reg.add_aliases("availability", code_alias)
        reg.add_values("license", [r["license"] for r in matrix])
        reg.add_values("task_family", [r["taskFamily"] for r in matrix
                                       if "taskFamily" in r])
    stats["summary"] = reg.summary()
    return stats
