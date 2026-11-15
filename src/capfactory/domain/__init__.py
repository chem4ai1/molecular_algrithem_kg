"""蛋白质 / 分子算法能力领域层.

在 CapFactory 原有「通用算法能力」之上补齐生物分子领域语义：

- ``bio_schema``   : 领域本体数据结构 + JSON Schema + 校验（本次新增的核心 schema）
- ``ontology``     : 图谱节点/边类型扩展与 OWL/Turtle 导出
- ``extract``      : 结构化知识抽取（词典 + 规则 + 证据锚定 + 代码反推）
- ``reasoning``    : 领域推理（能力链 / 适用性 / 指标可比性 / 检索重排 / 缺口）
- ``contracts``    : 蛋白质与分子任务的接口契约（插件式注册）
- ``validation``   : v2 验证路径（回归指标 + SciForge 机械门）

设计约束：**零新增第三方依赖、完全离线可用、不修改原流水线默认行为**。
"""

from .bio_schema import (
    ALGORITHM_FAMILIES,
    BIO_ENTITIES,
    EVIDENCE_GRADES,
    MODALITIES,
    TASK_FAMILIES,
    ApplicabilityDomain,
    BioSpec,
    ComputeBudget,
    DomainEvidence,
    DomainIOField,
    MetricProfile,
    ProteinCapability,
    json_schema,
    validate_capability,
)

__all__ = [
    "BIO_ENTITIES", "MODALITIES", "TASK_FAMILIES", "ALGORITHM_FAMILIES",
    "EVIDENCE_GRADES", "BioSpec", "DomainIOField", "MetricProfile",
    "ApplicabilityDomain", "ComputeBudget", "DomainEvidence",
    "ProteinCapability", "json_schema", "validate_capability",
]
