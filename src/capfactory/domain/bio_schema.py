"""蛋白质 / 分子「算法能力」本体 Schema.

设计动机
--------
原 ``capfactory.schema.Capability`` 是一个**扁平**结构：``task`` / ``inputs`` /
``outputs`` / ``metrics`` 都是自由字符串或简单字典。它足以描述"肽毒性二分类"，
但无法回答蛋白质/分子算法落地时必须回答的问题：

1. 作用于什么**生物实体**（蛋白 / 多肽 / 小分子 / 复合物）？什么**模态**（序列 / 3D 结构 / 分子图 / SMILES / MSA）？
2. 输入输出在**领域语义上**是否可拼接？（ESM embedding 能接 GAT 吗？SMILES 能直接喂 AAC 吗？）
3. 两个能力报告的 AUC 0.95 与 0.93 **可比吗**？（数据集、划分、指标方向、评测协议是否一致？）
4. 这条能力的**适用域**是什么？（序列长度、物种、数据量、结构是否必需）
5. 需要多少**算力**、是否确定性、依赖哪些包？
6. 每个字段的**证据等级与置信度**是多少？是否真的能在原文中锚定？

因此本模块把能力拆成 6 个正交切面：

    BioSpec(实体/模态)  →  DomainIOField(数据契约)  →  TaskFamily(任务族)
    →  MetricProfile(可比指标)  →  ApplicabilityDomain(适用域)
    →  ComputeBudget(算力)  →  DomainEvidence(可锚定证据)

并保留 ``to_legacy_capability()`` 向下兼容，使新 schema 能直接写入现有
``KnowledgeGraph``，不需要重建存储层。

所有 dataclass 字段统一使用 ``str`` / 基础类型（枚举只作为常量集合与校验表），
保证 ``dataclasses.asdict`` + ``json.dumps`` 零摩擦。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from ..utils import now_iso, short_hash, slugify

# ---------------------------------------------------------------------------
# 受控词表（Controlled Vocabularies）
# ---------------------------------------------------------------------------

BIO_ENTITIES = (
    "protein", "peptide", "antibody", "enzyme", "small_molecule",
    "complex", "nucleic_acid", "cell", "unknown",
)

MODALITIES = (
    "sequence", "structure_3d", "molecular_graph", "smiles", "fingerprint",
    "msa", "surface", "embedding", "image", "text", "tabular", "unknown",
)

TASK_FAMILIES = (
    "property_prediction", "structure_prediction", "binding_affinity",
    "interaction_prediction", "molecular_generation", "docking",
    "admet", "virtual_screening", "representation_learning",
    "sequence_design", "evaluation_protocol", "optimization",
    # 与领域分类 D0–D10 对齐的任务族（报告包与 AlgoGraph 使用）
    "peptide", "multi_molecular", "single_cell", "other",
)

ALGORITHM_FAMILIES = (
    "descriptor", "classical_ml", "deep_learning", "geometric_dl",
    "generative", "optimization", "statistical", "simulation",
    "ensemble", "retrieval", "hybrid",
    # 与算法族 A01–A18 对齐的架构值（PO Algorithm.architecture 同源）
    "diffusion", "flow_matching", "transformer", "graph_neural_network",
    "protein_language_model", "equivariant_network", "vae", "autoregressive",
    "rfdiffusion", "docking_search", "generative_platform",
    "reinforcement_learning", "other",
)

EVIDENCE_GRADES = ("A", "B", "C", "D")
# A = 论文原文 + 开源代码双证；B = 论文原文可引用；C = 仅代码反推；D = 启发式/占位

# 报告 §5.3：方向不总是 higher/lower（如「肠道限制性药物要限制全身暴露」）
METRIC_DIRECTIONS = ("higher", "lower", "context_dependent")

# 模态之间的可拼接关系：上游输出能否直接作为下游输入
MODALITY_COMPATIBILITY: Dict[str, Tuple[str, ...]] = {
    "sequence": ("sequence", "embedding", "tabular", "msa", "structure_3d"),
    "smiles": ("smiles", "molecular_graph", "fingerprint", "embedding", "tabular"),
    "molecular_graph": ("molecular_graph", "embedding", "tabular"),
    "structure_3d": ("structure_3d", "molecular_graph", "surface", "embedding", "tabular"),
    "msa": ("msa", "embedding", "tabular"),
    "fingerprint": ("fingerprint", "embedding", "tabular"),
    "embedding": ("embedding", "tabular"),
    "tabular": ("tabular",),
    "image": ("image", "embedding", "tabular"),
    "text": ("text", "embedding", "tabular"),
    "surface": ("surface", "embedding", "tabular"),
    "unknown": tuple(MODALITIES),
}

# 每个任务族的典型主指标（用于抽取补全与可比性检查）
TASK_METRIC_PRIORS: Dict[str, Tuple[str, ...]] = {
    "property_prediction": ("roc_auc", "accuracy", "mcc", "f1", "spearman", "rmse"),
    "structure_prediction": ("tm_score", "rmsd", "lddt", "gdtts"),
    "binding_affinity": ("spearman", "pearson", "rmse", "mae", "auc"),
    "interaction_prediction": ("aupr", "roc_auc", "mcc", "f1"),
    "molecular_generation": ("validity", "uniqueness", "novelty", "diversity"),
    "docking": ("rmsd", "success_rate", "enrichment_factor"),
    "admet": ("roc_auc", "rmse", "mae", "spearman"),
    "virtual_screening": ("enrichment_factor", "auroc", "hit_rate"),
    "representation_learning": ("spearman", "roc_auc", "accuracy", "retrieval_recall"),
    "sequence_design": ("validity", "diversity", "fitness"),
    "evaluation_protocol": ("mcc", "roc_auc", "aupr"),
    "optimization": ("fitness", "success_rate", "regret"),
}

LOWER_IS_BETTER = {"rmse", "mae", "rmsd", "brier", "regret", "cross_entropy", "loss"}


def default_direction(metric_name: str) -> str:
    """按指标名给出默认优化方向。"""
    return "lower" if (metric_name or "").lower() in LOWER_IS_BETTER else "higher"


def modalities_compatible(out_modality: str, in_modality: str) -> bool:
    """上游输出模态能否直接喂给下游输入模态。"""
    if not out_modality or not in_modality:
        return False
    if out_modality == in_modality:
        return True
    return in_modality in MODALITY_COMPATIBILITY.get(out_modality, ())


# ---------------------------------------------------------------------------
# 切面 1：生物实体与数据模态
# ---------------------------------------------------------------------------
@dataclass
class BioSpec:
    """能力所作用的生物实体与数据形态。"""

    entity: str = "peptide"
    modality: str = "sequence"
    alphabet: str = "amino_acid_1letter"   # amino_acid_1letter / smiles / pdb / atom_graph / ...
    length_min: int = 1
    length_max: int = 2000
    organism: List[str] = field(default_factory=list)
    structure_required: bool = False
    structure_source: str = ""             # pdb / alphafold / esmfold / md / none
    notes: str = ""

    def text(self) -> str:
        return " ".join(filter(None, [self.entity, self.modality, self.alphabet,
                                     self.structure_source, " ".join(self.organism)]))


# ---------------------------------------------------------------------------
# 切面 2：领域数据契约
# ---------------------------------------------------------------------------
@dataclass
class DomainIOField:
    """带领域语义的输入/输出契约。

    相比原 ``IOField`` 增加 ``modality`` / ``canonical_form`` / ``value_range`` /
    ``validator``，使「能力链推理」可以在类型层面判定两个能力是否可组合。
    """

    name: str
    modality: str = "sequence"
    dtype: str = "list[str]"
    shape: str = "[N]"
    unit: str = ""
    value_range: str = ""
    canonical_form: str = ""               # 归一化约定，如 uppercase / canonical SMILES
    validator: str = ""                    # 校验函数名，如 validate_smiles
    description: str = ""
    example: str = ""
    required: bool = True

    def to_legacy(self) -> Dict[str, Any]:
        """降级为原 ``IOField`` 可接受的字典。"""
        return {
            "name": self.name, "dtype": self.dtype, "shape": self.shape,
            "unit": self.unit, "description": self.description,
            "example": self.example, "required": self.required,
            "modality": self.modality, "canonical_form": self.canonical_form,
        }

    @classmethod
    def from_any(cls, d: Any) -> "DomainIOField":
        if isinstance(d, cls):
            return d
        d = d if isinstance(d, dict) else {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# 切面 3：可比指标
# ---------------------------------------------------------------------------
@dataclass
class MetricProfile:
    """一条**可比较**的指标声明 + 可选的一次原子观测。

    演进两阶段：
    - v1（原有）：``name/direction/reported/dataset/split/protocol``，用
      ``comparable_key()`` 做 5 段比较；
    - v2（本次，依据问题导向报告 §3/§5.4/CQ3-5）：补齐 ``dataset_version /
      input_condition / sample_budget / top_k / threshold / stage / assay / endpoint /
      condition`` 等，用 ``comparable_key_v2()`` 做 15 维比较；并区分
      ``reported``（观测值）与 ``missing_state``（观测级缺失）——**缺失不是 0/false**。

    报告要求：比例必须带 numerator/denominator/筛选阶段/阈值；均值必须带
    聚合方式与误差类型；同一 IC50 在不同 pH/底物/物种下是不同观测，不得平均。
    """

    name: str
    direction: str = "higher"
    reported: Optional[float] = None
    dataset: str = ""
    split: str = ""                        # holdout / cv5 / independent_test / train
    protocol: str = ""                     # 如 "ToxinPred3 original 80/20 split"
    unit: str = ""
    note: str = ""
    # ---- v2：观测语义 ----
    value_type: str = "number"             # number / fraction / count / score
    aggregation: str = ""                  # derived_fraction / mean / reported_percent …
    modality: str = ""                     # computational / biochemical / in_vitro / animal …
    missing_state: str = ""                # not_reported / not_measured / not_extracted …
    missing_reasons: Dict[str, str] = field(default_factory=dict)
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    stage: str = ""                        # nominated / synthesized / tested …
    threshold: str = ""
    top_k: str = ""
    sample_budget: str = ""
    input_condition: str = ""
    condition: Dict[str, Any] = field(default_factory=dict)   # pH / substrate / dose …
    dataset_version: str = ""
    assay_id: str = ""
    endpoint_id: str = ""
    subject: str = ""
    target: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    source_version: str = ""

    def comparable_key(self) -> str:
        """v1 五段键（保留兼容）；新代码请用 ``comparable_key_v2()``。"""
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")
        return "|".join(norm(x) for x in (self.name, self.dataset, self.split,
                                          self.protocol, self.direction))

    def comparable_key_v2(self) -> str:
        """v2 十五维键：回答报告 CQ3/CQ4/CQ5 的可比性判定。"""
        from ..po.comparability import comparability_key
        return comparability_key(self).key()

    def observation_state(self) -> str:
        """``measured`` / ``missing:<state>``；禁止把 None 当 0。"""
        if self.reported is not None:
            return "measured"
        return f"missing:{self.missing_state or 'not_reported'}"

    def is_comparable_with(self, other: "MetricProfile") -> Dict[str, Any]:
        from ..po.comparability import compare_observations
        return compare_observations(self, other)

    def validate_observation_semantics(self) -> List[str]:
        """SHACL xone + 比例/条件约束的轻量 Python 版。"""
        problems: List[str] = []
        if (self.reported is None) == (not self.missing_state):
            problems.append("reported 与 missing_state 必须恰好有一个（缺失不是 0/false）")
        if self.reported is not None:
            if self.direction not in METRIC_DIRECTIONS:
                problems.append(f"direction={self.direction!r} 非法")
            if self.value_type == "fraction" and not (0.0 <= self.reported <= 1.0):
                problems.append("fraction 类型观测值必须在 [0,1]")
        if self.numerator is not None and self.denominator in (None, 0):
            problems.append("比例观测必须给出非零 denominator（报告 CQ4）")
        if self.aggregation == "derived_fraction" and self.denominator is None:
            problems.append("derived_fraction 缺少分母")
        if (self.reported is not None and self.name.lower() in ("ic50", "kd")
                and not self.condition and not self.protocol):
            problems.append("IC50/Kd 缺少实验条件（pH/底物/物种）或协议，易被错误比较")
        return problems

    def to_legacy(self) -> Dict[str, Any]:
        return {"name": self.name, "direction": self.direction,
                "reported": self.reported, "dataset": self.dataset,
                "note": " ".join(filter(None, [self.split, self.protocol, self.note]))}

    def to_observation(self) -> Dict[str, Any]:
        """报告 §5.4 的「指标观测最小模板」。"""
        return {
            "metric": self.name, "subject": self.subject, "target": self.target,
            "value": self.reported, "unit": self.unit, "modality": self.modality,
            "condition": self.condition, "aggregation": self.aggregation,
            "numerator": self.numerator, "denominator": self.denominator,
            "stage": self.stage, "threshold": self.threshold,
            "sourceEvidence": list(self.evidence_ids), "sourceVersion": self.source_version,
            "missingReasons": dict(self.missing_reasons),
            "comparabilityKey": self.comparable_key_v2(),
        }

    @classmethod
    def from_any(cls, d: Any) -> "MetricProfile":
        d = d if isinstance(d, dict) else {}
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in known}
        if not data.get("direction"):
            data["direction"] = default_direction(str(data.get("name", "")))
        if data.get("reported") is None and not data.get("missing_state"):
            data["missing_state"] = "not_reported"
        return cls(**data)


# ---------------------------------------------------------------------------
# 切面 4：适用域
# ---------------------------------------------------------------------------
@dataclass
class ApplicabilityDomain:
    """能力成立的条件；推理引擎用它做前置检查，避免把能力用到错误模态/尺度。"""

    entities: List[str] = field(default_factory=list)
    modalities: List[str] = field(default_factory=list)
    length_min: int = 0
    length_max: int = 0                    # 0 = 不限
    min_samples: int = 0
    data_regime: str = ""                  # low_data / balanced / imbalanced / large_scale
    species: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)   # 明确排除的情形
    constraints: List[str] = field(default_factory=list)

    def check(self, spec: BioSpec, n_samples: int = 0) -> Tuple[bool, List[str]]:
        """返回 ``(是否适用, 违反项列表)``。空约束视为通配。"""
        violations: List[str] = []
        if self.entities and spec.entity not in self.entities and "unknown" not in self.entities:
            violations.append(f"实体不匹配：需要 {self.entities}，给定 {spec.entity}")
        if self.modalities and spec.modality not in self.modalities and "unknown" not in self.modalities:
            violations.append(f"模态不匹配：需要 {self.modalities}，给定 {spec.modality}")
        if self.length_max and (spec.length_min > self.length_max or spec.length_max < self.length_min):
            violations.append(
                f"长度越界：允许 [{self.length_min},{self.length_max}]，"
                f"给定 [{spec.length_min},{spec.length_max}]")
        if self.min_samples and 0 < n_samples < self.min_samples:
            violations.append(f"样本不足：需要 ≥{self.min_samples}，给定 {n_samples}")
        for ex in self.exclusions:
            if ex and ex.lower() in spec.text().lower():
                violations.append(f"命中排除条件：{ex}")
        return (not violations), violations


# ---------------------------------------------------------------------------
# 切面 5：算力与复现预算
# ---------------------------------------------------------------------------
@dataclass
class ComputeBudget:
    """复刻一条能力所需的资源，用于方案评分与可行性推理。"""

    device: str = "cpu"                    # cpu / gpu / multi_gpu
    runtime_seconds: int = 300
    memory_mb: int = 2048
    dependencies: List[str] = field(default_factory=list)
    deterministic: bool = True
    seed_policy: str = "fixed_42"
    parallelism: int = 1

    def feasible_on(self, *, cpu_only: bool = True, max_memory_mb: int = 8192,
                    max_runtime_s: int = 600) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if cpu_only and self.device in ("gpu", "multi_gpu"):
            issues.append(f"需要 {self.device}，目标环境仅 CPU")
        if self.memory_mb > max_memory_mb:
            issues.append(f"内存需求 {self.memory_mb}MB > 上限 {max_memory_mb}MB")
        if self.runtime_seconds > max_runtime_s:
            issues.append(f"时长 {self.runtime_seconds}s > 上限 {max_runtime_s}s")
        return (not issues), issues


# ---------------------------------------------------------------------------
# 切面 6：可锚定证据
# ---------------------------------------------------------------------------
@dataclass
class DomainEvidence:
    """一条带**原文锚定**状态的证据。

    ``anchored=False`` 表示 quote 无法在源文本中逐字找到（LLM 幻觉典型信号），
    抽取器会据此降置信度，Critic 可据此直接剔除该能力。
    """

    source_id: str = ""
    quote: str = ""
    locator: str = ""
    kind: str = "paper"                    # paper / code / doc / experiment
    anchored: bool = False
    char_span: List[int] = field(default_factory=list)
    # v2（报告 §5.1/§9）：证据必须绑定论文版本、原始文件 hash 与归属
    attribution: str = "author_explicit"
    paper_version_id: str = ""
    section: str = ""
    source_url: str = ""
    extraction_file_sha256: str = ""
    read_date: str = ""

    def anchor_in(self, source_text: str) -> "DomainEvidence":
        """在原文中做规范化空白后的逐字匹配，写回 ``anchored`` 与 ``char_span``。"""
        if not self.quote or not source_text:
            self.anchored, self.char_span = False, []
            return self
        norm = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731
        q, t = norm(self.quote), norm(source_text)
        idx = t.find(q)
        # 长度 >= 25 才做前缀回退，避免短词误命中
        if idx < 0 and len(q) >= 25:
            idx = t.find(q[: max(25, len(q) // 2)])
        self.anchored = idx >= 0
        self.char_span = [idx, idx + len(q)] if idx >= 0 else []
        return self

    def to_legacy(self) -> Dict[str, Any]:
        return {"source_id": self.source_id, "quote": self.quote,
                "locator": self.locator, "kind": self.kind,
                "attribution": self.attribution,
                "paper_version_id": self.paper_version_id,
                "section": self.section or self.locator,
                "extraction_file_sha256": self.extraction_file_sha256}


# ---------------------------------------------------------------------------
# 聚合：蛋白质/分子算法能力
# ---------------------------------------------------------------------------
@dataclass
class ProteinCapability:
    """一条完整、可校验、可写入图谱的领域算法能力。"""

    id: str = ""
    name: str = ""
    summary: str = ""
    task: str = ""
    task_family: str = "property_prediction"
    algorithm_family: str = "classical_ml"
    category: str = "model"                # 兼容原 Capability.category
    bio_spec: BioSpec = field(default_factory=BioSpec)
    inputs: List[DomainIOField] = field(default_factory=list)
    outputs: List[DomainIOField] = field(default_factory=list)
    method: str = ""
    metrics: List[MetricProfile] = field(default_factory=list)
    applicability: ApplicabilityDomain = field(default_factory=ApplicabilityDomain)
    compute: ComputeBudget = field(default_factory=ComputeBudget)
    evidence: List[DomainEvidence] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    field_confidence: Dict[str, float] = field(default_factory=dict)
    evidence_grade: str = "D"
    # v2（问题导向报告）：能力是「带适用范围的主张」，不是算法的布尔属性
    claim_scope: str = ""
    evidence_level: str = ""               # computational / biochemical / animal …
    attribution: str = "evidence_bounded_synthesis"
    limitations: List[str] = field(default_factory=list)
    problem_ids: List[str] = field(default_factory=list)   # P01–P11 / P06a 等
    po_claim_id: str = ""
    # 领域/算法族分类（D0–D10 / A01–A18），可由 task_family + 规则自动推导
    domain_codes: List[str] = field(default_factory=list)
    algo_codes: List[str] = field(default_factory=list)
    taxonomy_source: str = ""
    maturity: float = 0.0
    version: int = 1
    verification: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # -- 构造 -------------------------------------------------------------
    @staticmethod
    def make_id(name: str, task: str = "", source: str = "") -> str:
        return f"pcap_{slugify(name, 40)}_{short_hash(name, task, source, length=6)}"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.make_id(self.name, self.task,
                                   str(self.provenance.get("source_id", "")))
        for m in self.metrics:
            if not m.direction:
                m.direction = default_direction(m.name)
        if not self.dependencies and self.compute.dependencies:
            self.dependencies = list(self.compute.dependencies)

    # -- 序列化 -----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProteinCapability":
        d = dict(d or {})
        nested = {
            "bio_spec": BioSpec, "applicability": ApplicabilityDomain,
            "compute": ComputeBudget,
        }
        for key, klass in nested.items():
            raw = d.get(key) or {}
            known = {f.name for f in fields(klass)}
            d[key] = klass(**{k: v for k, v in raw.items() if k in known}) if isinstance(raw, dict) else klass()
        d["inputs"] = [DomainIOField.from_any(x) for x in d.get("inputs") or []]
        d["outputs"] = [DomainIOField.from_any(x) for x in d.get("outputs") or []]
        d["metrics"] = [MetricProfile.from_any(x) for x in d.get("metrics") or []]
        d["evidence"] = [
            e if isinstance(e, DomainEvidence) else DomainEvidence(
                **{k: v for k, v in (e or {}).items() if k in {f.name for f in fields(DomainEvidence)}})
            for e in d.get("evidence") or []
        ]
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    # -- 领域/算法族分类（D0–D10 / A01–A18） --------------------------------
    def infer_taxonomy(self) -> Dict[str, Any]:
        """由 ``task_family`` / ``algorithm_family`` + 文本规则推导 D/A 标签。

        与 PO 层共用同一套词表与规则（``capfactory/po/taxonomy.py``），
        保证能力节点与论文节点落在同一坐标系，可按领域/算法族做图查询。
        """
        from ..po.taxonomy import (
            ALGO_NAMES, ALGORITHM_FAMILY_TO_CODE, DOMAIN_NAMES,
            TASK_FAMILY_TO_DOMAIN, classify,
        )
        doms: List[str] = []
        if self.task_family in TASK_FAMILY_TO_DOMAIN:
            doms.append(TASK_FAMILY_TO_DOMAIN[self.task_family])
        algos: List[str] = []
        if self.algorithm_family in ALGORITHM_FAMILY_TO_CODE:
            algos.append(ALGORITHM_FAMILY_TO_CODE[self.algorithm_family])
        text = " ".join(str(x) for x in
                        (self.task, self.method, self.summary, self.category,
                         self.name) if x)
        from ..po.taxonomy import DOMAIN_FALLBACK
        for code in classify(text, "domain", limit=3):
            if code == DOMAIN_FALLBACK and doms:
                continue          # 已有明确领域时，不再追加 D0 兜底
            if code not in doms:
                doms.append(code)
        for code in classify(text, "algo", limit=3):
            if code not in algos:
                algos.append(code)
        self.domain_codes = doms[:3]
        self.algo_codes = algos[:3]
        self.taxonomy_source = "task_family+rule" if self.task_family else "rule"
        return {"domains": self.domain_codes,
                "domain_names": [DOMAIN_NAMES.get(c, c) for c in self.domain_codes],
                "algorithms": self.algo_codes,
                "algorithm_names": [ALGO_NAMES.get(c, c) for c in self.algo_codes],
                "source": self.taxonomy_source}

    def ensure_taxonomy(self) -> "ProteinCapability":
        """幂等：未分类时自动推断。"""
        if not self.domain_codes or not self.algo_codes:
            self.infer_taxonomy()
        return self

    # -- 兼容原图谱 -------------------------------------------------------
    def to_legacy_capability(self):
        """降级为 ``capfactory.schema.Capability``，可直接 ``graph.add_capability``。"""
        from ..schema import Capability, Evidence, IOField, MetricSpec

        self.ensure_taxonomy()

        def legacy(item: Any, klass: Any) -> Dict[str, Any]:
            """兼容 dataclass 实例与 dict（LLM 抽取常直接给 dict）。"""
            if hasattr(item, "to_legacy"):
                return item.to_legacy()
            known = {f.name for f in fields(klass)}
            d = item if isinstance(item, dict) else {}
            return klass(**{k: v for k, v in d.items() if k in known}).to_legacy()

        return Capability(
            id=self.id, name=self.name or self.id,
            summary=self.summary, category=self.category, task=self.task,
            inputs=[IOField.from_dict(legacy(i, DomainIOField)) for i in self.inputs],
            outputs=[IOField.from_dict(legacy(o, DomainIOField)) for o in self.outputs],
            method=self.method,
            metrics=[MetricSpec.from_dict(legacy(m, MetricProfile)) for m in self.metrics],
            conditions=list(self.conditions) + [f"适用实体: {self.bio_spec.entity}",
                                                f"模态: {self.bio_spec.modality}"],
            constraints=list(self.constraints) + self.applicability.constraints,
            dependencies=list(self.dependencies) or list(self.compute.dependencies),
            evidence=[Evidence.from_dict(legacy(e, DomainEvidence)) for e in self.evidence],
            tags=list(dict.fromkeys(self.tags + [self.task_family, self.algorithm_family,
                                                 f"grade_{self.evidence_grade}"]
                                                + [f"problem:{p}" for p in self.problem_ids]
                                                + [f"domain:{c}" for c in self.domain_codes]
                                                + [f"algo:{c}" for c in self.algo_codes])),
            confidence=self.confidence, maturity=self.maturity, version=self.version,
            provenance={**self.provenance, "domain_schema": "protein_v2_po",
                        "task_family": self.task_family,
                        "algorithm_family": self.algorithm_family,
                        "evidence_grade": self.evidence_grade,
                        "field_confidence": dict(self.field_confidence),
                        "claim_scope": self.claim_scope,
                        "evidence_level": self.evidence_level,
                        "attribution": self.attribution,
                        "problem_ids": list(self.problem_ids),
                        "po_claim_id": self.po_claim_id,
                        "domain_codes": list(self.domain_codes),
                        "algo_codes": list(self.algo_codes),
                        "taxonomy_source": self.taxonomy_source},
            verification=dict(self.verification),
            created_at=self.created_at, updated_at=self.updated_at,
        )

    def text_for_index(self) -> str:
        return "\n".join(filter(None, [
            self.name, self.task, self.task_family, self.algorithm_family,
            self.summary, self.method, self.bio_spec.text(),
            " ".join(self.tags), " ".join(self.conditions),
        ]))

    # -- 校验 -------------------------------------------------------------
    def validate(self) -> List[str]:
        return validate_capability(self.to_dict())


_REQUIRED_FIELDS = ("name", "task", "method")


def validate_capability(doc: Dict[str, Any]) -> List[str]:
    """结构化校验，返回问题列表（空 = 通过）。不依赖 jsonschema 包。"""
    problems: List[str] = []
    if not isinstance(doc, dict):
        return ["capability 不是对象"]
    for k in _REQUIRED_FIELDS:
        if not str(doc.get(k) or "").strip():
            problems.append(f"缺少必填字段 {k}")
    for k, vocab in (("task_family", TASK_FAMILIES), ("algorithm_family", ALGORITHM_FAMILIES),
                     ("evidence_grade", EVIDENCE_GRADES)):
        v = doc.get(k)
        if v and v not in vocab:
            problems.append(f"{k}={v!r} 不在受控词表 {vocab}")
    bio = doc.get("bio_spec") or {}
    if bio.get("entity") and bio["entity"] not in BIO_ENTITIES:
        problems.append(f"bio_spec.entity={bio['entity']!r} 不在受控词表")
    if bio.get("modality") and bio["modality"] not in MODALITIES:
        problems.append(f"bio_spec.modality={bio['modality']!r} 不在受控词表")
    if not (doc.get("inputs") or []):
        problems.append("缺少 inputs（数据契约不可为空）")
    if not (doc.get("outputs") or []):
        problems.append("缺少 outputs（数据契约不可为空）")
    for side in ("inputs", "outputs"):
        for i, fld in enumerate(doc.get(side) or []):
            m = fld.get("modality") if isinstance(fld, dict) else getattr(fld, "modality", "")
            if m and m not in MODALITIES:
                problems.append(f"{side}[{i}].modality={m!r} 不在受控词表")
    conf = doc.get("confidence", 0.5)
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        problems.append(f"confidence={conf!r} 超出 [0,1]")
    for i, m in enumerate(doc.get("metrics") or []):
        d = m.get("direction") if isinstance(m, dict) else getattr(m, "direction", "")
        if d and d not in METRIC_DIRECTIONS:
            problems.append(f"metrics[{i}].direction={d!r} 非法")
        rep = m.get("reported") if isinstance(m, dict) else getattr(m, "reported", None)
        if rep is not None and not isinstance(rep, (int, float)):
            problems.append(f"metrics[{i}].reported 不是数值")
        missing = (m.get("missing_state") if isinstance(m, dict)
                   else getattr(m, "missing_state", ""))
        if rep is not None and missing:
            problems.append(f"metrics[{i}] 同时给出 reported 与 missing_state"
                            "（报告 §5.3：缺失不是 false，二者互斥）")
    for i, pid in enumerate(doc.get("problem_ids") or []):
        if not re.fullmatch(r"P\d{2}[a-z]?", str(pid)):
            problems.append(f"problem_ids[{i}]={pid!r} 不符合 P01–P11 / P06a 编号")
    for i, code in enumerate(doc.get("domain_codes") or []):
        if not re.fullmatch(r"D(10|[0-9])", str(code)):
            problems.append(f"domain_codes[{i}]={code!r} 不符合 D0–D10")
    for i, code in enumerate(doc.get("algo_codes") or []):
        if not re.fullmatch(r"A(0[1-9]|1[0-8])", str(code)):
            problems.append(f"algo_codes[{i}]={code!r} 不符合 A01–A18")
    if doc.get("attribution") == "":
        problems.append("attribution 为空（必须区分作者声明与分析者归纳）")
    for i, e in enumerate(doc.get("evidence") or []):
        anchored = e.get("anchored") if isinstance(e, dict) else getattr(e, "anchored", False)
        if not anchored:
            problems.append(f"evidence[{i}] 未能在原文锚定（疑似幻觉证据）")
    return problems


def json_schema() -> Dict[str, Any]:
    """导出 draft-07 JSON Schema（供 ``/api/v2/schema`` 与外部校验器使用）。"""
    def obj(props: Dict[str, Any], required: List[str] = None) -> Dict[str, Any]:
        out = {"type": "object", "properties": props, "additionalProperties": True}
        if required:
            out["required"] = required
        return out

    def arr(item: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": "array", "items": item}

    string = {"type": "string"}
    number = {"type": "number"}
    enum = lambda *v: {"type": "string", "enum": list(v)}  # noqa: E731

    io = obj({
        "name": string, "modality": enum(*MODALITIES), "dtype": string, "shape": string,
        "unit": string, "value_range": string, "canonical_form": string,
        "validator": string, "description": string, "example": string,
        "required": {"type": "boolean"},
    }, ["name"])
    metric = obj({
        "name": string, "direction": enum(*METRIC_DIRECTIONS),
        "reported": {"type": ["number", "null"]}, "dataset": string, "split": string,
        "protocol": string, "unit": string, "note": string,
        # v2 观测语义（报告 §5.4 / CQ3-5）
        "value_type": string, "aggregation": string, "modality": string,
        "missing_state": string, "missing_reasons": {"type": "object"},
        "numerator": {"type": ["number", "null"]}, "denominator": {"type": ["number", "null"]},
        "stage": string, "threshold": string, "top_k": string, "sample_budget": string,
        "input_condition": string, "condition": {"type": "object"},
        "dataset_version": string, "assay_id": string, "endpoint_id": string,
        "subject": string, "target": string, "evidence_ids": arr(string),
        "source_version": string,
    }, ["name"])
    evidence = obj({
        "source_id": string, "quote": string, "locator": string,
        "kind": enum("paper", "code", "doc", "experiment"),
        "anchored": {"type": "boolean"}, "char_span": arr({"type": "integer"}),
        "attribution": string, "paper_version_id": string, "section": string,
        "source_url": string, "extraction_file_sha256": string, "read_date": string,
    })
    return obj({
        "id": string, "name": string, "summary": string, "task": string,
        "task_family": enum(*TASK_FAMILIES),
        "algorithm_family": enum(*ALGORITHM_FAMILIES), "category": string,
        "bio_spec": obj({
            "entity": enum(*BIO_ENTITIES), "modality": enum(*MODALITIES),
            "alphabet": string, "length_min": {"type": "integer"},
            "length_max": {"type": "integer"}, "organism": arr(string),
            "structure_required": {"type": "boolean"},
            "structure_source": string, "notes": string,
        }),
        "inputs": arr(io), "outputs": arr(io), "method": string,
        "metrics": arr(metric),
        "applicability": obj({
            "entities": arr(enum(*BIO_ENTITIES)), "modalities": arr(enum(*MODALITIES)),
            "length_min": {"type": "integer"}, "length_max": {"type": "integer"},
            "min_samples": {"type": "integer"}, "data_regime": string,
            "species": arr(string), "exclusions": arr(string), "constraints": arr(string),
        }),
        "compute": obj({
            "device": string, "runtime_seconds": {"type": "integer"},
            "memory_mb": {"type": "integer"}, "dependencies": arr(string),
            "deterministic": {"type": "boolean"}, "seed_policy": string,
            "parallelism": {"type": "integer"},
        }),
        "evidence": arr(evidence), "conditions": arr(string), "constraints": arr(string),
        "dependencies": arr(string), "tags": arr(string),
        "confidence": number, "field_confidence": {"type": "object",
                                                   "additionalProperties": number},
        "evidence_grade": enum(*EVIDENCE_GRADES), "maturity": number,
        # v2 能力主张语义（报告 §5.3 决策 2：能力不是算法布尔属性）
        "claim_scope": string, "evidence_level": string, "attribution": string,
        "limitations": arr(string), "problem_ids": arr(string), "po_claim_id": string,
        "domain_codes": arr(string), "algo_codes": arr(string), "taxonomy_source": string,
        "version": {"type": "integer"}, "verification": {"type": "object"},
        "provenance": {"type": "object"}, "created_at": string, "updated_at": string,
    }, ["name", "task", "method", "inputs", "outputs"])


def owl_turtle(prefix: str = "https://capfactory.local/bio#") -> str:
    """导出轻量 OWL 本体（Turtle），便于 Protege / rdflib 打开。"""
    lines = [
        f"@prefix bio: <{prefix}> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "", "bio:ProteinCapability a owl:Class ; rdfs:label \"蛋白质/分子算法能力\" .",
    ]
    groups = {
        "BioEntity": BIO_ENTITIES, "Modality": MODALITIES,
        "TaskFamily": TASK_FAMILIES, "AlgorithmFamily": ALGORITHM_FAMILIES,
    }
    for cls, values in groups.items():
        lines.append(f"bio:{cls} a owl:Class .")
        for v in values:
            lines.append(f"bio:{v.replace('-', '_')} a owl:NamedIndividual , bio:{cls} ; "
                         f"rdfs:label \"{v}\" .")
    for p in ("actsOn", "hasModality", "belongsToTaskFamily", "hasAlgorithmFamily",
              "hasInput", "hasOutput", "evaluatedBy", "composesWith",
              "benchmarkedOn", "constrainedBy", "derivedFrom"):
        lines.append(f"bio:{p} a owl:ObjectProperty .")
    for p in ("confidence", "maturity", "evidenceGrade", "reportedValue"):
        lines.append(f"bio:{p} a owl:DatatypeProperty .")
    return "\n".join(lines) + "\n"
