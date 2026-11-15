"""能力知识图谱的领域本体扩展.

原 ``kg/graph.py`` 有 8 类节点（paper/capability/dataset/metric/task/artifact/
lesson/direction）和 11 类边，全部围绕「一篇论文提出一条能力」。
蛋白质/分子场景还需要表达：

- 能力**作用于**哪个生物实体、哪种数据模态；
- 能力之间在**类型层面是否可组合**（表示 → 预测 → 筛选的流水线）；
- 一条能力**在哪个评测协议/基线**下被验证（否则指标不可比）；
- 能力之间的**迁移 / 约束 / 超越**关系（用于推理与缺口分析）。

本模块只做「类型注册 + 边语义约束 + 领域实体写入」，不改动原有存储格式：
新节点依然是 ``{"id","type","label","attrs"}``，老代码、老导出器、老前端全部兼容。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils import short_hash
from .bio_schema import (
    ALGORITHM_FAMILIES, BIO_ENTITIES, MODALITIES, MODALITY_COMPATIBILITY,
    TASK_FAMILIES, ProteinCapability, modalities_compatible,
)

# ---------------------------------------------------------------------------
# 节点类型扩展
# ---------------------------------------------------------------------------
EXTRA_NODE_TYPES = (
    "bio_entity",       # 蛋白 / 多肽 / 小分子 / 复合物 …
    "modality",         # 序列 / 3D 结构 / 分子图 / SMILES / MSA …
    "representation",   # 具体表示法：AAC / DPC / ESM embedding / ECFP …
    "task_family",      # 任务族（受控词表）
    "protocol",         # 评测协议：数据集 + 划分 + 指标方向
    "baseline",         # 可比较的基线方法及其报告值
    # AlgoGraph 投影类型（块级 code_block 不投影，保留在细粒度子图）
    "func_name",        # PKG Name 节点：函数标识符
    "implementation",   # PKG Impl 节点：完整函数实现
    "causal_node",      # Causal Algorithm Design 七类因果节点
    "paper_module",     # 论文细粒度方法模块
    "capability_version",  # 版本化的能力代码工件容器
)

BASE_NODE_TYPES = ("paper", "capability", "dataset", "metric", "task",
                   "artifact", "lesson", "direction")
ALL_NODE_TYPES = tuple(dict.fromkeys(BASE_NODE_TYPES + EXTRA_NODE_TYPES))

# ---------------------------------------------------------------------------
# 边语义表：rel -> (允许的源类型, 允许的目标类型, 语义说明, 是否参与能力链推理)
# ---------------------------------------------------------------------------
EDGE_SEMANTICS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...], str, bool]] = {
    # 原有关系（补齐语义说明，便于统一校验）
    "PROPOSES":      (("paper",), ("capability",), "论文提出能力", False),
    "IMPLEMENTS":    (("paper",), ("capability",), "代码仓库实现能力", False),
    "STUDIES":       (("paper",), ("task",), "论文研究任务", False),
    "USES_DATASET":  (("paper", "capability"), ("dataset",), "使用数据集", False),
    "APPLIES_TO":    (("capability",), ("task",), "能力适用于任务", False),
    "EVALUATED_BY":  (("capability",), ("metric",), "能力用该指标评价", False),
    "REALIZED_BY":   (("capability",), ("artifact",), "能力由代码工件实现", False),
    "VERIFIED_BY":   (("capability", "artifact"), ("artifact",), "验证报告", False),
    "FAILED_WITH":   (("capability",), ("lesson",), "失败经验", False),
    "DEPENDS_ON":    (("direction",), ("capability",), "方向依赖能力", False),
    "SIMILAR_TO":    (("capability",), ("capability",), "语义相似", False),
    "SUGGESTS":      (("direction",), ("capability",), "建议补齐能力", False),
    # 新增领域关系
    "ACTS_ON":       (("capability",), ("bio_entity",), "能力作用的生物实体", False),
    "HAS_MODALITY":  (("capability", "bio_entity"), ("modality",), "数据模态", False),
    "IN_TASK_FAMILY": (("capability",), ("task_family",), "归属任务族", False),
    "USES_REPRESENTATION": (("capability",), ("representation",), "使用的表示法", False),
    "INPUT_OF":      (("representation", "modality"), ("capability",), "输入数据契约", False),
    "OUTPUT_OF":     (("capability",), ("representation", "modality"), "输出数据契约", False),
    "COMPOSES_WITH": (("capability",), ("capability",), "输出可接下游输入（可组合）", True),
    "BENCHMARKED_ON": (("capability", "baseline"), ("protocol",), "在指定协议下评测", False),
    "OUTPERFORMS":   (("capability",), ("baseline",), "在同一协议下严格优于基线", False),
    "CONSTRAINS":    (("capability",), ("capability",), "上游约束下游适用域", True),
    "TRANSFERS_TO":  (("capability",), ("capability",), "跨实体/跨任务迁移", True),
    "DERIVES_FROM":  (("capability",), ("capability",), "由已有能力改造而来", True),
}

# AlgoGraph 子图的边（由 algograph.schema.validate_graph 自行做严格校验，
# 这里只登记语义与是否参与能力链，避免主图巡检把它们当成未知关系）。
_ALGO_TYPES = ("capability_version", "func_name", "implementation", "causal_node",
               "paper_module", "code_block", "module", "class_unit",
               "external_symbol", "unresolved_site", "data_artifact",
               "test_case", "metric_binding")
EDGE_SEMANTICS.update({
    "DECLARES":     ((_ALGO_TYPES), (_ALGO_TYPES), "模块/类声明函数或类", False),
    "HAS_IMPL":     ((_ALGO_TYPES), (_ALGO_TYPES), "PKG Name→Impl", False),
    "HAS_BLOCK":    ((_ALGO_TYPES), (_ALGO_TYPES), "PKG Impl→顶层语法块", False),
    "NESTS":        ((_ALGO_TYPES), (_ALGO_TYPES), "PKG 父块→子块", False),
    "PROJECTS_TO":  ((_ALGO_TYPES), (_ALGO_TYPES), "块→父函数实现的反向投影", False),
    "IN_FUNCTION":  ((_ALGO_TYPES), (_ALGO_TYPES), "块→函数标识符的反向投影", False),
    "CALLS":        ((_ALGO_TYPES), (_ALGO_TYPES), "站点级调用边", True),
    "FLOWS_TO":     ((_ALGO_TYPES), (_ALGO_TYPES), "参数/返回数据流边", True),
    "IMPORTS":      ((_ALGO_TYPES), (_ALGO_TYPES), "import 绑定", False),
    "INHERITS":     ((_ALGO_TYPES), (_ALGO_TYPES), "类继承", False),
    "PART_OF":      ((_ALGO_TYPES), (_ALGO_TYPES), "单元归属能力版本", False),
    "SPECIFIES":    ((_ALGO_TYPES), (_ALGO_TYPES), "论文模块→因果节点", False),
    "REALIZES":     ((_ALGO_TYPES), (_ALGO_TYPES), "代码单元→因果节点", False),
    "GROUNDS_TO":   ((_ALGO_TYPES), (_ALGO_TYPES), "代码因果节点→论文因果节点", False),
    "CAUSES":       ((_ALGO_TYPES), (_ALGO_TYPES), "因果依赖边", True),
    "ASSERTS":      ((_ALGO_TYPES), (_ALGO_TYPES), "断言/指标绑定", False),
})

ALL_EDGE_TYPES = tuple(EDGE_SEMANTICS)
ALGOGRAPH_NODE_TYPES = frozenset(_ALGO_TYPES)

# ---- 问题导向本体（PO）扩展：34 类概念 / 39 类关系 ----
# 单一事实源在 capfactory/po/concepts.py；此处 try/except 保证 kg 层可独立加载。
try:
    from ..po.concepts import CONCEPT_CLASSES as _PO_CLASSES
    from ..po.concepts import RELATION_DOMAIN_RANGE as _PO_RELATIONS
except Exception:  # pragma: no cover
    _PO_CLASSES, _PO_RELATIONS = (), {}

PO_NODE_TYPES = frozenset(_PO_CLASSES)
EXTRA_NODE_TYPES = tuple(dict.fromkeys(EXTRA_NODE_TYPES + tuple(_PO_CLASSES)))
ALL_NODE_TYPES = tuple(dict.fromkeys(BASE_NODE_TYPES + EXTRA_NODE_TYPES))
for _rel, (_dom, _rng) in _PO_RELATIONS.items():
    EDGE_SEMANTICS.setdefault(_rel, (tuple(_dom), tuple(_rng),
                                     f"PO 关系 {_rel}", False))
ALL_EDGE_TYPES = tuple(EDGE_SEMANTICS)


def node_type_ok(node_type: str) -> bool:
    return node_type in ALL_NODE_TYPES


def validate_edge(source_type: str, target_type: str, rel: str) -> List[str]:
    """检查一条边是否符合本体约束，返回问题列表（空 = 合法）。"""
    problems: List[str] = []
    spec = EDGE_SEMANTICS.get(rel)
    if not spec:
        return [f"未知关系类型 {rel!r}"]
    # 细粒度子图的端点类型由 algograph.schema.validate_graph 严格校验；
    # 主图本体不重复施加 capability 层的类型约束。
    if (source_type in ALGOGRAPH_NODE_TYPES or target_type in ALGOGRAPH_NODE_TYPES
            or source_type in PO_NODE_TYPES or target_type in PO_NODE_TYPES):
        return []
    allowed_src, allowed_dst, _desc, _chain = spec
    if source_type not in allowed_src:
        problems.append(f"{rel} 源类型应为 {allowed_src}，实际 {source_type!r}")
    if target_type not in allowed_dst:
        problems.append(f"{rel} 目标类型应为 {allowed_dst}，实际 {target_type!r}")
    return problems


def chain_relations() -> Tuple[str, ...]:
    """返回参与能力链推理的关系。"""
    return tuple(r for r, v in EDGE_SEMANTICS.items() if v[3])


# ---------------------------------------------------------------------------
# 领域实体写入
# ---------------------------------------------------------------------------
def _nid(prefix: str, name: str) -> str:
    return f"{prefix}::{short_hash((name or '').lower(), length=8)}"


def add_domain_entities(graph, capabilities: Iterable[ProteinCapability],
                        *, auto_compose: bool = True) -> Dict[str, Any]:
    """把 ``ProteinCapability`` 的领域语义投影到图谱节点与边上。

    ``graph`` 为 ``capfactory.kg.KnowledgeGraph`` 实例（鸭子类型即可）。
    返回写入统计。已存在的节点按 id 幂等更新，可重复调用。
    """
    caps = list(capabilities)
    stats = {"nodes_added": 0, "edges_added": 0, "composable_pairs": 0,
             "protocol_nodes": 0, "problems": []}

    for cap in caps:
        before_nodes, before_edges = len(graph.nodes), len(graph.edges)
        if cap.id not in graph.nodes:
            # 允许领域能力独立存在；写入一个最小 capability 节点以保持图连通
            graph.add_node(cap.id, "capability", cap.name or cap.id,
                           summary=cap.summary, task=cap.task,
                           task_family=cap.task_family,
                           algorithm_family=cap.algorithm_family,
                           evidence_grade=cap.evidence_grade,
                           confidence=cap.confidence, maturity=cap.maturity,
                           domain_schema="protein_v1")

        # 1) 生物实体 / 模态 / 任务族
        eid = _nid("bio", cap.bio_spec.entity)
        graph.add_node(eid, "bio_entity", cap.bio_spec.entity,
                       alphabet=cap.bio_spec.alphabet,
                       structure_source=cap.bio_spec.structure_source)
        graph.add_edge(cap.id, eid, "ACTS_ON")

        mid = _nid("mod", cap.bio_spec.modality)
        graph.add_node(mid, "modality", cap.bio_spec.modality)
        graph.add_edge(cap.id, mid, "HAS_MODALITY")

        fid = _nid("family", cap.task_family)
        graph.add_node(fid, "task_family", cap.task_family)
        graph.add_edge(cap.id, fid, "IN_TASK_FAMILY")

        # 2) 表示法（从 IO 的 canonical_form / modality 推导）
        for io in list(cap.inputs) + list(cap.outputs):
            rep = io.canonical_form or io.modality
            if not rep:
                continue
            rid = _nid("rep", rep)
            graph.add_node(rid, "representation", rep,
                           modality=io.modality, dtype=io.dtype, shape=io.shape)
            graph.add_edge(cap.id, rid, "USES_REPRESENTATION")

        # 3) 评测协议 + 指标可比 key
        for m in cap.metrics:
            if not m.name:
                continue
            pid = _nid("proto", m.comparable_key())
            graph.add_node(pid, "protocol", m.protocol or m.comparable_key(),
                           metric=m.name, dataset=m.dataset, split=m.split,
                           direction=m.direction, comparable_key=m.comparable_key())
            graph.add_edge(cap.id, pid, "BENCHMARKED_ON")
            stats["protocol_nodes"] += 1

        stats["nodes_added"] += len(graph.nodes) - before_nodes
        stats["edges_added"] += len(graph.edges) - before_edges

    # 4) 能力组合边：上游输出模态 → 下游输入模态，且任务族不同/实体一致
    if auto_compose:
        before = len(graph.edges)
        for up in caps:
            for down in caps:
                if up.id == down.id:
                    continue
                if not _composable(up, down):
                    continue
                graph.add_edge(up.id, down.id, "COMPOSES_WITH", 0.8,
                               evidence="output/input modality compatible")
                stats["composable_pairs"] += 1
        stats["edges_added"] += len(graph.edges) - before

    # 5) 本体一致性巡检
    for e in graph.edges:
        s, t = graph.nodes.get(e["source"]), graph.nodes.get(e["target"])
        if not s or not t:
            continue
        problems = validate_edge(s["type"], t["type"], e["type"])
        if problems:
            stats["problems"].append({"edge": e["type"], "issues": problems[:1]})
    stats["problems"] = stats["problems"][:20]
    return stats


def _composable(up: ProteinCapability, down: ProteinCapability) -> bool:
    """判定两条能力在数据契约上能否串成流水线。"""
    if not up.outputs or not down.inputs:
        return False
    if up.bio_spec.entity != down.bio_spec.entity and "unknown" not in (
            up.bio_spec.entity, down.bio_spec.entity):
        return False
    out_modalities = {o.modality for o in up.outputs if o.modality}
    in_modalities = {i.modality for i in down.inputs if i.modality}
    return any(modalities_compatible(o, i)
               for o in out_modalities for i in in_modalities)


def composable_pairs(capabilities: Iterable[ProteinCapability]) -> List[Tuple[str, str]]:
    """纯函数版组合判定，供推理引擎与测试使用。"""
    caps = list(capabilities)
    return [(a.id, b.id) for a in caps for b in caps
            if a.id != b.id and _composable(a, b)]


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
def ontology_document() -> Dict[str, Any]:
    """机器可读的本体清单（Web API / 文档生成共用）。"""
    return {
        "schema_version": "protein_v1",
        "node_types": list(ALL_NODE_TYPES),
        "base_node_types": list(BASE_NODE_TYPES),
        "extra_node_types": list(EXTRA_NODE_TYPES),
        "controlled_vocabularies": {
            "bio_entity": list(BIO_ENTITIES), "modality": list(MODALITIES),
            "task_family": list(TASK_FAMILIES),
            "algorithm_family": list(ALGORITHM_FAMILIES),
        },
        "edge_types": [
            {"rel": rel, "source": list(v[0]), "target": list(v[1]),
             "semantics": v[2], "chain": v[3]}
            for rel, v in EDGE_SEMANTICS.items()
        ],
        "chain_relations": list(chain_relations()),
        "compatibility": {k: list(v) for k, v in MODALITY_COMPATIBILITY.items()},
    }
