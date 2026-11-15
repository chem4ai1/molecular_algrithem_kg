"""能力知识图谱与复刻流水线的数据结构.

设计原则
--------
1. **可执行**：每个 ``Capability`` 都挂接可运行的代码工件（artifact）与验证结果，
   与 xKG「概念节点—可执行节点」分层思想保持一致；
2. **可追溯**：所有字段都能回指到论文证据（``Evidence``）或执行日志（``VerificationReport``）；
3. **可演进**：``version`` / ``maturity`` / ``lessons`` 支持能力版本管理与失败经验沉淀。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from ..utils import now_iso, short_hash, slugify


def _filter_fields(cls: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    known = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in known}


# ---------------------------------------------------------------------------
# 基础构件
# ---------------------------------------------------------------------------
@dataclass
class IOField:
    """输入/输出字段定义（数据格式契约）。"""

    name: str
    dtype: str = "any"              # str / float / list[str] / ndarray / mol / fasta
    shape: str = ""                 # 例： [N] / [N, L, 4]
    unit: str = ""
    description: str = ""
    example: str = ""
    required: bool = True

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IOField":
        return cls(**_filter_fields(cls, d))


@dataclass
class MetricSpec:
    """评价指标定义。"""

    name: str                       # 例： accuracy / f1 / auc / rmse / spearman
    direction: str = "higher"       # higher / lower
    reported: Optional[float] = None  # 论文报告值
    dataset: str = ""               # 报告所在数据集
    note: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetricSpec":
        return cls(**_filter_fields(cls, d))


@dataclass
class Evidence:
    """论文/代码证据片段。"""

    source_id: str
    quote: str
    locator: str = ""               # 例： Sec.3.2 / Table 2 / README
    kind: str = "paper"             # paper / code / doc

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Evidence":
        return cls(**_filter_fields(cls, d))


@dataclass
class Capability:
    """一条可执行算法能力。"""

    id: str
    name: str
    summary: str = ""
    category: str = "model"         # data / representation / model / training / screening / evaluation / pipeline
    task: str = ""                  # 任务标识，如 peptide_toxicity_prediction
    inputs: List[IOField] = field(default_factory=list)
    outputs: List[IOField] = field(default_factory=list)
    method: str = ""                # 算法步骤/原理
    metrics: List[MetricSpec] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)   # 适用条件
    constraints: List[str] = field(default_factory=list)  # 局限/风险/伦理
    dependencies: List[str] = field(default_factory=list)  # 依赖包/硬件/数据
    evidence: List[Evidence] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.6
    maturity: float = 0.0           # 0=仅概念 1=已复刻并通过验证
    version: int = 1
    provenance: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    artifact_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # -- 序列化 --------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Capability":
        data = _filter_fields(cls, d)
        data["inputs"] = [IOField.from_dict(x) for x in d.get("inputs") or []]
        data["outputs"] = [IOField.from_dict(x) for x in d.get("outputs") or []]
        data["metrics"] = [MetricSpec.from_dict(x) for x in d.get("metrics") or []]
        data["evidence"] = [Evidence.from_dict(x) for x in d.get("evidence") or []]
        return cls(**data)

    @staticmethod
    def make_id(name: str, task: str = "", paper: str = "") -> str:
        return f"cap_{slugify(name, 40)}_{short_hash(name, task, paper, length=6)}"

    def text_for_index(self) -> str:
        """用于检索的拼接文本。"""
        parts = [self.name, self.task, self.summary, self.method, " ".join(self.tags),
                 " ".join(c for c in self.conditions)]
        return "\n".join(p for p in parts if p)


@dataclass
class PaperRecord:
    """论文元信息（研究对象/背景/进展的载体）。"""

    id: str
    title: str
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    url: str = ""
    arxiv_id: str = ""
    pdf_path: str = ""
    repo_url: str = ""
    repo_path: str = ""
    venue: str = ""
    # 结构化理解
    research_object: str = ""       # 研究对象
    background: str = ""            # 研究背景
    progress: str = ""              # 研究进展（本文所处位置）
    contributions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    datasets: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)
    full_text_path: str = ""
    source: str = "arxiv"
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PaperRecord":
        return cls(**_filter_fields(cls, d))

    @staticmethod
    def make_id(title: str) -> str:
        return f"paper_{short_hash(title.strip().lower(), length=10)}"


@dataclass
class Plan:
    """算法实现方案（多候选用）。"""

    id: str
    capability_id: str
    name: str
    approach: str
    steps: List[str] = field(default_factory=list)
    libraries: List[str] = field(default_factory=list)
    rationale: str = ""
    risks: List[str] = field(default_factory=list)
    expected_metrics: Dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    score_detail: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Artifact:
    """一次代码复刻产物。"""

    id: str
    capability_id: str
    plan_id: str
    code_path: str
    entry: str = "solution.py"
    task_type: str = "sequence_binary_classification"
    status: str = "generated"        # generated / repaired / verified / failed
    rounds: int = 1
    requirements: List[str] = field(default_factory=list)
    dataset_path: str = ""
    notes: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artifact":
        return cls(**_filter_fields(cls, d))


@dataclass
class VerificationReport:
    """统一验证报告。"""

    id: str
    artifact_id: str
    capability_id: str
    passed: bool = False
    contract: Dict[str, Any] = field(default_factory=dict)
    functional: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    stability: Dict[str, Any] = field(default_factory=dict)
    security: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    failures: List[str] = field(default_factory=list)
    logs: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VerificationReport":
        return cls(**_filter_fields(cls, d))


@dataclass
class Lesson:
    """失败经验（可复用知识）。"""

    id: str
    capability_id: str
    symptom: str
    root_cause: str
    fix: str
    error_signature: str = ""
    occurrences: int = 1
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchDirection:
    """研究方向建议。"""

    id: str
    title: str
    gap: str
    rationale: str
    supporting_capabilities: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    experiments: List[str] = field(default_factory=list)
    expected_impact: str = ""
    difficulty: str = "medium"
    priority: float = 0.0
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
