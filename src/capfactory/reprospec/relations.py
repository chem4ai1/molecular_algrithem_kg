"""P0-1：关系名单一真相源（GGR 蓝图 §3.3 / 差距 G8）。

问题背景（2026-11-14 实测）：
  * ``sciforge/repro/phasegraph.json`` R2 的 reads 写 ``REALIZED_BY`` /
    ``IMPLEMENTS_MODULE``，这两个名字在语义层 v4.1 里**不存在**；
  * 语义层实际关系是 ``MODULE_IMPLEMENTED_BY`` / ``HAS_MODULE``
    （``capfactory/semantic/tbox_v4.py:91-102``）；
  * ``planner.py`` 又绕开图、改读 ``relation_index.json`` 的派生链名
    （``algorithm_code`` / ``data_paper``）。三套口径并存会让门判定与真实图脱节。

本模块提供：
  1. ``SEMANTIC_RELATIONS`` / ``APP_RELATIONS``：与 tbox 定义逐字一致的规范名
  2. ``LEGACY_ALIASES``：旧名 → 规范名（只做解析，不改图数据）
  3. ``resolve_relation()`` / ``canonicalize_reads()``：给读取方用
  4. ``validate_phasegraph()``：给 CI / 测试用，检查 reads 是否全部可解释
  5. ``RELATION_INDEX_CHAINS``：**显式声明** planner 对 relation_index 的依赖，
     把它与 TBox 关系区分开（派生链不是关系）

约定：TBox 关系是「图上真实存在的边」；relation_index 链是「预先算好的多跳路径」，
两者不得混用。字段名别名（research_problem→research_question 等）单列在
``FIELD_ALIASES``，不改变任何现有读取行为。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

# ---------------------------------------------------------------------------
# 规范关系名（与 tbox_v4.py:91 / applayer/tbox.py:APP_RELATIONS 保持一致）
# ---------------------------------------------------------------------------
SEMANTIC_RELATIONS: Dict[str, Tuple[str, str, str]] = {
    "PROPOSES_METHOD": ("Paper", "Algorithm", "论文提出算法"),
    "HAS_CODE": ("Paper", "CodeRepository", "论文关联代码仓库"),
    "EVALUATED_ON": ("Paper|Algorithm", "Benchmark", "在哪个基准上评测"),
    "HAS_MODULE": ("Algorithm", "AlgorithmModule", "算法由哪些模块构成"),
    "MODULE_IMPLEMENTED_BY": ("AlgorithmModule", "CodeFunction", "模块由哪个函数实现"),
    "HAS_FUNCTION": ("CodeRepository", "CodeFunction", "仓库包含函数"),
    "BELONGS_TO_MODULE": ("CodeFunction", "AlgorithmModule", "函数所属模块（反向）"),
    "RELATED_TO": ("Paper", "Paper|Algorithm", "相关文献/方法"),
    "SUBCLASS_OF": ("Algorithm", "Algorithm", "算法继承/改进关系"),
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

# P0-3：复现应用层新增的 4 条运行时关系（只写 app_repro_runtime.json，
# 不是挖掘器关系，因此不进 applayer.tbox.APP_RELATIONS，避免改变 8/9 基线）
REPRO_APP_RELATIONS: Dict[str, Tuple[str, str, str]] = {
    "VERIFIES": ("EvaluationResult", "AlgorithmModule|Benchmark|LeaderboardEntry",
                 "逐 SAU 判定所依据的图节点"),
    "DEVIATES_FROM": ("ReproductionResult", "LeaderboardEntry", "实跑值偏离的榜单基线"),
    "LINEAGE_OF": ("SourcePaper", "Paper", "出处论文所属的目标论文"),
    "GENERATED_BY": ("CodeGenerationTask", "AlgorithmModule", "代码任务由哪个模块派生"),
    "HAS_SAU": ("RubricNode", "RubricNode",
                "rubric 分支包含的逐条可判定 SAU"),
}

ALL_CANONICAL: frozenset = frozenset(
    set(SEMANTIC_RELATIONS) | set(APP_RELATIONS) | set(REPRO_APP_RELATIONS))

# ---------------------------------------------------------------------------
# 旧名 → 规范名。只用于「解析读取方的声明」，绝不回写图。
# ---------------------------------------------------------------------------
LEGACY_ALIASES: Dict[str, str] = {
    # phasegraph R2 的两个旧名（本次 P0-1 直接修掉 reads，别名保留给历史数据）
    "REALIZED_BY": "MODULE_IMPLEMENTED_BY",
    "IMPLEMENTS_MODULE": "HAS_MODULE",
    # 其它常见历史名
    "HAS_STEP": "HAS_MODULE",
    "HAS_MODULE_DETAIL": "HAS_MODULE",
    "EVALUATES_METHOD": "EVALUATED_ON",
    "PROPOSES_WORKFLOW": "PROPOSES_METHOD",
    "SOURCED_FROM": "RELATED_TO",
    "SOURCES_ALGORITHM": "PROPOSES_METHOD",
    "USES_DATASET": "EVALUATED_ON",
    "HAS_DATA_CONTRACT": "HAS_CONTRACT",
    "REPORTS_VALUE": "HAS_ENTRY",
    "OF_METRIC": "USES_METRIC",
}

# 字段名别名（语义层 v4 把若干旧字段收进 Paper/Benchmark 属性）
FIELD_ALIASES: Dict[str, str] = {
    "Paper.research_problem": "Paper.research_question",
    "Paper.algorithm_family": "Paper.flow_family",
}

# ---------------------------------------------------------------------------
# planner 对 relation_index.json 的派生链依赖（显式声明，不是 TBox 关系）
# ---------------------------------------------------------------------------
RELATION_INDEX_CHAINS: Dict[str, str] = {
    "paper_algorithm": "Paper → Algorithm 的预计算链",
    "paper_data": "Paper → Benchmark 的预计算链",
    "paper_paper": "Paper → Paper 的科技树链",
    "paper_code": "Paper → CodeRepository 的预计算链",
    "algorithm_code": "Algorithm → CodeFunction 的预计算链（对应 HAS_MODULE + MODULE_IMPLEMENTED_BY）",
    "data_paper": "Benchmark → 出处论文的预计算链（对应 RELATED_TO）",
}

# 复现七阶段应当读取的规范关系（供 validate / 文档生成）
REPRO_PHASE_READS: Dict[str, Tuple[str, ...]] = {
    "R0": (),  # 只读 Paper 属性
    "R1": ("PROPOSES_METHOD", "HAS_MODULE", "SUBCLASS_OF"),
    "R2": ("HAS_CODE", "HAS_FUNCTION", "MODULE_IMPLEMENTED_BY",
           "BELONGS_TO_MODULE"),
    "R3": ("EVALUATED_ON", "HAS_CONTRACT", "RELATED_TO"),
    "R4": ("HAS_METRIC", "HAS_ENTRY", "USES_METRIC", "SUPPORTED_BY"),
    "R5": (),  # 读 PLAN 文件
    "R6": (),  # 读结果文件
}

# 允许出现在 reads 里的节点类型名（不是关系）
NODE_TYPES: frozenset = frozenset({
    "Paper", "Algorithm", "AlgorithmModule", "CodeRepository",
    "CodeFunction", "Benchmark", "ResearchQuestion", "ProblemCategory",
    "LeaderboardEntry", "MetricDefinition", "DataContract", "Evidence",
    "Limitation", "SourcePaper",
})


def resolve_relation(name: str) -> str:
    """把可能的历史关系名解析成规范名；已是规范名则原样返回。

    未知名字也原样返回（由 ``validate_phasegraph`` 负责报错，这里不吞异常）。
    """
    return LEGACY_ALIASES.get(name, name)


def canonicalize_reads(reads: Iterable[str]) -> Tuple[List[str], List[Dict[str, str]]]:
    """规范化一组 reads 声明，返回 (规范列表, 替换记录)。

    ``Type.field`` 形式的字段声明会做 FIELD_ALIASES 映射；
    ``relation_index[chain]`` 与 ``*.json`` 形式视为非关系声明，原样保留。
    """
    out: List[str] = []
    replaced: List[Dict[str, str]] = []
    for raw in reads:
        s = str(raw)
        if s in FIELD_ALIASES:
            out.append(FIELD_ALIASES[s])
            replaced.append({"from": s, "to": FIELD_ALIASES[s], "kind": "field"})
            continue
        if s.startswith("relation_index[") or s.endswith(".json"):
            out.append(s)
            continue
        if "." in s:  # Type.field
            out.append(s)
            continue
        canon = resolve_relation(s)
        out.append(canon)
        if canon != s:
            replaced.append({"from": s, "to": canon, "kind": "relation"})
    return out, replaced


def validate_phasegraph(pg: Dict[str, Any]) -> List[str]:
    """检查 phasegraph 的 reads 是否全部可解释；返回问题描述列表（空 = 通过）。

    判定规则：
      * 关系名必须在 ``ALL_CANONICAL`` 内（若是别名，报「应改名为 X」）
      * ``Type.field`` 的类型必须在 ``NODE_TYPES`` 内
      * ``*.json`` / ``relation_index[...]`` 是产物/派生链，合法
      * fields ``kg.result`` 这类外部存储标记，合法
    """
    problems: List[str] = []
    for ph in pg.get("phases", []):
        pid = ph.get("id", "?")
        for raw in ph.get("reads", []) or []:
            s = str(raw)
            if s.endswith(".json") or s.startswith("relation_index[") \
                    or s.startswith("kg.") or s.startswith("relation["):
                continue
            if "." in s:
                typ = s.split(".", 1)[0]
                if typ not in NODE_TYPES:
                    problems.append(f"{pid}: 未知节点类型 {typ} ({s})")
                if s in FIELD_ALIASES:
                    problems.append(
                        f"{pid}: 字段名 {s} 应为 {FIELD_ALIASES[s]}")
                continue
            if s in NODE_TYPES:
                continue
            canon = resolve_relation(s)
            if canon != s:
                problems.append(f"{pid}: 关系 {s} 是历史别名，应改为 {canon}")
            elif s not in ALL_CANONICAL:
                problems.append(f"{pid}: 未知关系 {s}")
    return problems


def check_against_tbox() -> List[str]:
    """与真实 tbox 模块做一致性核对（惰性导入，避免循环依赖）。

    返回差异列表；空列表表示本模块常量与 ``semantic/tbox_v4.py`` /
    ``applayer/tbox.py`` 完全一致。
    """
    diffs: List[str] = []
    try:
        from capfactory.semantic import tbox_v4  # type: ignore
        real = set(tbox_v4.SEMANTIC_RELATIONS)
    except Exception as exc:  # noqa: BLE001
        return [f"无法导入 semantic.tbox_v4: {exc}"]
    if real != set(SEMANTIC_RELATIONS):
        diffs.append(f"语义层差异: 本模块独有 {sorted(set(SEMANTIC_RELATIONS)-real)} / "
                     f"tbox 独有 {sorted(real-set(SEMANTIC_RELATIONS))}")
    try:
        from capfactory.applayer import tbox as app_tbox  # type: ignore
        real_app = set(app_tbox.APP_RELATIONS)
    except Exception as exc:  # noqa: BLE001
        return diffs + [f"无法导入 applayer.tbox: {exc}"]
    if real_app != set(APP_RELATIONS):
        diffs.append(f"应用层差异: 本模块独有 {sorted(set(APP_RELATIONS)-real_app)} / "
                     f"tbox 独有 {sorted(real_app-set(APP_RELATIONS))}")
    return diffs


def snapshot() -> Dict[str, Any]:
    return {
        "n_semantic_relations": len(SEMANTIC_RELATIONS),
        "n_app_relations": len(APP_RELATIONS),
        "n_aliases": len(LEGACY_ALIASES),
        "n_relation_index_chains": len(RELATION_INDEX_CHAINS),
        "phase_reads": {k: list(v) for k, v in REPRO_PHASE_READS.items()},
    }
