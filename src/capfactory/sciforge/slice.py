"""
按任务切片：从全图导出"结构化子图 + 语义契约"
===========================================================================

【为什么需要这个模块】
intake 相位原来是 `{t: len(graph.by_type(t)) for t in 6 类}`，输出的是计数。
计数的问题：
  1. 没有语义——"Paper: 20" 不告诉你这 20 篇讲什么、彼此什么关系；
  2. 下游无人消费——实测全仓库只有 `flow.py:102` 写入，零处读取；
  3. 类名脆弱——图里存 `MetricObservation`，数 `Observation` 得 0，静默出错。

本模块把 intake 的产出换成两样东西：
  * `subgraph`（POGraph）——按"链式模板"导出的真子图，节点带语义位置；
  * `contract`（dict）——每条链、每一环的三态 + 缺口 + 指纹，给门和 LLM 用。

【核心概念：ChainTemplate（链式模板）】
不是"按深度 BFS"（实测单篇论文 3 跳可达 346-467 节点 = 全图 53%，等于没切），
而是"按关系链走"：给一条链的每一环声明 `(节点类型, 关系名, 是否必须)`，
只有这条链上的边才会进子图。

一条链的形状：
    Paper --FORMULATES--> ResearchQuestion --OPERATIONALIZED_AS--> Task
          --ADDRESSED_BY--> Algorithm

链在 `contract` 里被渲染成带三态的文本树（见 `render_chain`）：
    Paper paper:01
      ├─FORMULATES──> ResearchQuestion question:01
      │   └─OPERATIONALIZED_AS──> Task task:01
      │       └─ADDRESSED_BY──> Algorithm algo:01
      └─HAS_CLAIM──> CapabilityClaim claim:01   [ABSENT]

【四种切片视图（slice view）】
    full        —— 全部链（默认，用于审计/抽取核对）
    reproduction—— 复现：走"实现链"，要 code/metric/evidence
    de_novo     —— 生成：走"问题链"，要 problem/taxonomy/空覆盖
    extraction  —— 抽取：全链 + 只输出缺口，不给具体实例（避免上下文爆炸）

【已知断链（实测，不是 bug 是数据缺口）】
  * `Benchmark` 入度为 0：`EVALUATED_ON` 是空关系，`Paper` 无法直接连到 `Benchmark`。
    → benchmark 链在 contract 里标 `BROKEN`，并给出候选（Workflow→USES_DATASET→Dataset）。
  * `CodeArtifact / WeightArtifact / DataArtifact` 出度为 0：代码仓是叶子，无法下钻
    到 CodeModule/CodeFunction（这些类只在 V2 本体里，PO 图里没有）。
    → code 链在 `code.*` 叶子处终止，`contract.code.drilldown = False`。

【怎么用】
    from capfactory.po import POGraph
    from capfactory.sciforge.slice import slice_for_task, render_contract

    g = POGraph.load(Path("storage_cf/po/report_graph.json"))
    sl = slice_for_task(g, "reproduction", anchor="paper:01")

    sl.subgraph      # POGraph，可直接 save / 统计
    sl.contract      # dict，含 chains / coverage / gaps / fingerprint
    print(render_contract(sl.contract))   # 人类可读的链式树

    sl.blockers      # list[str]，硬阻塞项，intake 用它判 PASS/BLOCKED
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..po import POGraph

# ---------------------------------------------------------------------------
# 链式模板定义
# ---------------------------------------------------------------------------
# 每一环：(来源类型, 关系名, 目标类型, 是否必须)
# 关系名后面的 `|` 表示多选一（如 HAS_CODE|HAS_WEIGHTS）。
# 只有出现在模板里的关系才进子图 —— 这是"给结构"和"给噪声"的分界线。

Step = Tuple[str, str, str, bool]

# 主链：问题 → 任务 → 方法（所有视图都需要）
CHAIN_PROBLEM: List[Step] = [
    ("Paper", "FORMULATES", "ResearchQuestion", True),
    ("ResearchQuestion", "MOTIVATED_BY", "ProblemContext", False),
    ("ResearchQuestion", "OPERATIONALIZED_AS", "Task", True),
    ("Task", "ADDRESSED_BY", "Algorithm", True),
]

# 方法链：工作流 → 实现 → 数据集（复现必需）
CHAIN_METHOD: List[Step] = [
    ("Paper", "PROPOSES_WORKFLOW", "Workflow", True),
    ("Workflow", "IMPLEMENTS", "Algorithm", True),
    ("Workflow", "USES_DATASET", "Dataset", False),
    ("Dataset", "HAS_SPLIT", "DatasetSplit", False),
    ("Workflow", "HAS_OBJECTIVE", "Objective", False),
]

# 主张链：论文声称了什么、由什么证据支撑
CHAIN_CLAIM: List[Step] = [
    ("Paper", "HAS_CLAIM", "CapabilityClaim", True),
    ("CapabilityClaim", "ABOUT_METHOD", "Workflow", False),
    ("CapabilityClaim", "SUPPORTED_BY", "Evidence", False),
    ("Evidence", "EXTRACTED_FROM", "PaperVersion", True),
    ("Paper", "HAS_VERSION", "PaperVersion", False),
]

# 评测链：跑了什么实验、得到什么数值、用什么指标
# 首环必须从 Paper 出发（HAS_CLAIM），否则 anchor 是 Paper 时源类型不匹配，
# 会退化成"全图 20 个 CapabilityClaim"，把别篇论文的标定也拉进来。
CHAIN_EVAL: List[Step] = [
    ("Paper", "HAS_CLAIM", "CapabilityClaim", True),
    ("CapabilityClaim", "EVALUATED_IN", "EvaluationRun", True),
    ("EvaluationRun", "USES_METRIC", "MetricDefinition", True),
    ("EvaluationRun", "PRODUCES_OBSERVATION", "MetricObservation", True),
    ("MetricObservation", "HAS_CONDITION", "ExperimentalCondition", False),
    ("MetricObservation", "OF_METRIC", "MetricDefinition", False),
    ("MetricObservation", "SUPPORTED_BY", "Evidence", False),
    ("EvaluationRun", "HAS_ASSAY", "Assay", False),
    ("Assay", "MEASURES_ENDPOINT", "Endpoint", False),
    ("Benchmark", "HAS_LEADERBOARD", "LeaderboardEntry", False),
    ("LeaderboardEntry", "REPORTED_BY", "PaperVersion", False),
    ("LeaderboardEntry", "FROM_OBSERVATION", "MetricObservation", False),
]

# 实现链：代码/权重/数据产物（当前是叶子，无下钻）
CHAIN_CODE: List[Step] = [
    ("Paper", "HAS_CODE", "CodeArtifact", True),
    ("Paper", "HAS_WEIGHTS", "WeightArtifact", False),
    ("Paper", "HAS_DATA", "DataArtifact", False),
]

# 问题链：论文解决了什么、暴露了什么、属于哪个分类
CHAIN_PROBLEM_FORM: List[Step] = [
    ("Paper", "ADDRESSES", "ResearchProblem", True),
    ("Paper", "ANALYST_RELEVANT_TO", "ResearchProblem", False),
    ("Paper", "EXPOSES_LIMITATION", "ResearchProblem", False),
    ("ResearchProblem", "BROADER", "ProblemCategory", False),
    ("Limitation", "QUALIFIES", "CapabilityClaim", False),
]

# 分类链：领域与方法族（用于找空覆盖）
CHAIN_TAXONOMY: List[Step] = [
    ("Paper", "IN_DOMAIN", "Domain", True),
    ("Paper", "USES_ALGO_FAMILY", "AlgorithmFamily", True),
    ("Algorithm", "USES_ALGO_FAMILY", "AlgorithmFamily", False),
]

# 设计活动链（仅 supporting 维度，数据极少：1 campaign / 3 stage）
CHAIN_CAMPAIGN: List[Step] = [
    ("Paper", "REPORTS_CAMPAIGN", "DesignCampaign", False),
    ("DesignCampaign", "HAS_STAGE", "SelectionStage", False),
    ("DesignCampaign", "HAS_NEGATIVE_OUTCOME", "NegativeOutcome", False),
]

CHAIN_MAP: Dict[str, List[Step]] = {
    "problem": CHAIN_PROBLEM,
    "method": CHAIN_METHOD,
    "claim": CHAIN_CLAIM,
    "eval": CHAIN_EVAL,
    "code": CHAIN_CODE,
    "problem_form": CHAIN_PROBLEM_FORM,
    "taxonomy": CHAIN_TAXONOMY,
    "campaign": CHAIN_CAMPAIGN,
}

# ---------------------------------------------------------------------------
# 四种切片视图
# ---------------------------------------------------------------------------
# chains: 要导出哪些链；require: 哪些链缺失即硬阻塞（BLOCKED）
# max_nodes: 子图节点上限，超了按"先必须环、后可选环"截断

SLICE_PROFILES: Dict[str, Dict[str, Any]] = {
    "full": {
        "chains": list(CHAIN_MAP),
        "require": (),
        "max_nodes": 400,
        "desc": "全部链，用于审计与抽取核对",
    },
    "reproduction": {
        # 复现要回答：方法是什么、实现在哪、怎么评测、证据在哪
        "chains": ["problem", "method", "claim", "eval", "code", "taxonomy"],
        "require": ("method", "claim", "eval"),
        "max_nodes": 150,
        "desc": "复现：走实现链（workflow→code→eval→evidence）",
    },
    "de_novo": {
        # 生成要回答：问题是什么、哪个领域空着、哪些方法族没被组合
        "chains": ["problem", "problem_form", "method", "taxonomy"],
        "require": ("problem", "taxonomy"),
        "max_nodes": 200,
        "desc": "生成：走问题链（problem→taxonomy→空覆盖）",
    },
    "extraction": {
        # 抽取核对：全链但只报缺口，实例截断到 3 个（避免上下文爆炸）
        "chains": list(CHAIN_MAP),
        "require": (),
        "max_nodes": 120,
        "samples_only": 3,
        "desc": "抽取：全链 + 缺口，每环只留 3 个实例",
    },
}

# ---------------------------------------------------------------------------
# 已知断链（数据缺口，写入 contract 的 `broken` 字段）
# ---------------------------------------------------------------------------
KNOWN_BROKEN: Dict[str, Dict[str, str]] = {
    "benchmark": {
        "issue": "EVALUATED_ON 是空关系，Paper 无法直达 Benchmark（Benchmark 入度 0）",
        "workaround": "Workflow --USES_DATASET--> Dataset，再用 Benchmark --HAS_LEADERBOARD--> LeaderboardEntry 反查",
    },
    "code_drilldown": {
        "issue": "CodeArtifact/WeightArtifact/DataArtifact 出度均为 0，代码仓是叶子",
        "workaround": "需接 V2 的 CodeModule/CodeFunction，或用 AST 现场解析仓库",
    },
    "problem_empty": {
        "issue": "Assertion / MoleculeState / Organism 三类零实例",
        "workaround": "抽取侧补齐，或从 schema 中移除",
    },
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class StepResult:
    """一环的执行结果。"""
    src_type: str
    rel: str
    dst_type: str
    required: bool
    nodes: List[str] = field(default_factory=list)
    # present: 有实例；partial: 只有部分源节点有出边；absent: 一条都没有
    state: str = "absent"

    def to_dict(self) -> Dict[str, Any]:
        return {"rel": self.rel, "dst_type": self.dst_type,
                "required": self.required, "state": self.state,
                "n": len(self.nodes), "nodes": self.nodes}


@dataclass
class ChainResult:
    """一条链的执行结果（可嵌套成树）。"""
    name: str
    steps: List[StepResult] = field(default_factory=list)
    state: str = "absent"          # 由 required 环决定：present/partial/absent
    missing_required: List[str] = field(default_factory=list)
    failed_required: bool = False  # 是否因必须环零实例而中断
    children: List["ChainResult"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"chain": self.name, "state": self.state,
                "missing_required": self.missing_required,
                "steps": [s.to_dict() for s in self.steps],
                "children": [c.to_dict() for c in self.children]}


@dataclass
class GraphSlice:
    """intake 的正式产物：子图 + 契约 + 指纹。"""
    view: str
    anchor: Optional[str]
    subgraph: POGraph
    contract: Dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return self.contract["fingerprint"]

    @property
    def blockers(self) -> List[str]:
        return self.contract["blockers"]

    @property
    def ok(self) -> bool:
        return not self.blockers


# ---------------------------------------------------------------------------
# 核心：按链导出子图
# ---------------------------------------------------------------------------
def _split_rel(rel: str) -> List[str]:
    """`HAS_CODE|HAS_WEIGHTS` → ['HAS_CODE', 'HAS_WEIGHTS']"""
    return [r.strip() for r in rel.split("|") if r.strip()]


def _out_edges(graph: POGraph, node_id: str, rels: Iterable[str]
               ) -> List[Tuple[str, str]]:
    """取某节点的出边中，关系名在 rels 里的那些 → [(relation, target_id)]"""
    allowed = set(rels)
    return [(a.relation, a.target) for a in graph.assertions
            if a.source == node_id and a.relation in allowed]


def _anchor_nodes(graph: POGraph, anchor: Optional[str], src_type: str,
                  reached: Optional[set] = None) -> List[str]:
    """确定这一环的起点集合。

    优先级：
      1. anchor 本身（类型匹配时）
      2. 已被链触及且类型匹配的节点（保证只沿本文相关的路径走）
      3. 全图该类型的全部节点（无 anchor 或前两者都空时的兜底）

    第 2 条是关键：否则 `ResearchQuestion --OPERATIONALIZED_AS--> Task`
    会把全图 20 个 Task 都拉进来，子图立刻失去"本文相关"的语义。
    """
    if anchor and anchor in graph.nodes and graph.nodes[anchor].type == src_type:
        return [anchor]
    if reached:
        same = [n for n in reached
                if n in graph.nodes and graph.nodes[n].type == src_type]
        if same:
            return same
    return [n.id for n in graph.by_type(src_type)]


def _reachable(graph: POGraph, anchor: str, max_hops: int = 3) -> set:
    """从 anchor 出发、**只沿链模板中的关系、只走正向**的可达集合。

    三个约束缺一不可（都是实测踩过的坑）：
      1. 只沿链模板关系走 —— 否则 `IN_DOMAIN` / `USES_ALGO_FAMILY` 这些
         "多论文共享的分类边"会把邻域扩到全图（实测 20 个 Paper 全进）。
      2. 只走正向 —— 反向走 `EXTRACTED_FROM`（Evidence→PaperVersion）会
         顺藤摸到别的论文的 Evidence，再摸到别的 claim。
      3. 限 3 跳 —— 再深就退化成全图（实测无约束 3 跳 = 53% 覆盖）。

    这个集合只作硬边界用：链命中的节点若不在集合内，一律丢弃。
    """
    # 收集所有链模板里出现过的关系名
    tmpl_rels: set = set()
    for steps in CHAIN_MAP.values():
        for _s, rel, _d, _r in steps:
            tmpl_rels.update(_split_rel(rel))

    # 只有「多论文共享的枢纽边」需要排除在传播之外：
    #   IN_DOMAIN        —— 20 篇论文共享 11 个 Domain，一跳即全图
    #   USES_ALGO_FAMILY —— 共享 18 个 AlgorithmFamily，同理
    # 注意 SUPPORTED_BY / EXTRACTED_FROM 不能排除：它们是本文独占的证据链
    # （claim→evidence→version），排除会导致证据链断裂（实测 43 节点且 claim 链 ABSENT）。
    NON_PROPAGATING = {"IN_DOMAIN", "USES_ALGO_FAMILY", "BROADER"}
    tmpl_rels -= NON_PROPAGATING

    adj: Dict[str, List[str]] = {}
    for a in graph.assertions:
        if a.relation in tmpl_rels:
            adj.setdefault(a.source, []).append(a.target)

    seen = {anchor}
    frontier = [anchor]
    for _ in range(max_hops):
        nxt: List[str] = []
        for x in frontier:
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    nxt.append(y)
        frontier = nxt
        if not frontier:
            break
    return seen


# 终止类：作为链的终点，命中不受锚点邻域约束（它们被排除在传播之外）。
# 只放"共享分类枢纽"：Domain / AlgorithmFamily / ProblemCategory。
# 不能放 Task —— 它是 ResearchQuestion 的专属下游，共享会引入别篇的 Task。
_TERMINAL_TYPES: set = {"Domain", "AlgorithmFamily", "ProblemCategory"}


def _run_chain(graph: POGraph, name: str, steps: Sequence[Step],
               anchor: Optional[str], samples_only: Optional[int] = None,
               allowed: Optional[set] = None
               ) -> Tuple[ChainResult, set]:
    """执行一条链，返回 (链结果, 命中节点 id 集合)。

    逐环推进：每环以上一环命中的节点为源，取指定关系的出边。
    某环命中为空 → 该环 absent；若该环 required → 整链 state=absent。
    链在第一个 absent 的必须环处停止推进（后面的环没有意义）。
    """
    result = ChainResult(name=name)
    visited: set = set()
    # 当前"活跃源集合"：第一环用 anchor/全量，后续用上一环的命中
    frontier: Optional[List[str]] = None

    for src_type, rel, dst_type, required in steps:
        rels = _split_rel(rel)
        if frontier is None:
            sources = _anchor_nodes(graph, anchor, src_type, reached=visited)
        else:
            # 只从上一环命中里、且类型匹配的节点继续
            sources = [s for s in frontier
                       if s in graph.nodes and graph.nodes[s].type == src_type]
            if not sources:
                # 上一环类型与本环期望源类型不同（如 Task→Algorithm 之后又要
                # 从 CapabilityClaim 出发）。此时**只回退到已触及节点**，绝不
                # 回退到全量 —— 否则 EVALUATED_IN 会把全图 41 个 run 都拉进来。
                reach = [n for n in visited
                         if n in graph.nodes and graph.nodes[n].type == src_type]
                if reach:
                    sources = reach
                elif anchor is None:
                    # 无 anchor 的"全图视图"才允许全量，这是 full/extraction 的语义
                    sources = [n.id for n in graph.by_type(src_type)]
                else:
                    # 有 anchor 但上游没触及相关类型：此环直接判定为空
                    sources = []

        hits: List[str] = []
        seen = set()
        for s in sources:
            for r, t in _out_edges(graph, s, rels):
                tnode = graph.nodes.get(t)
                if tnode is None or tnode.type != dst_type:
                    continue
                # 锚点可达性硬约束：不在 anchor 邻域内的节点一律丢弃，
                # 防止跨论文污染（否则 EVALUATED_IN 会把 41 个 run 全算进来）。
                # 例外：分类/归属类终点（Domain/AlgoFamily）本来就被排除在传播之外，
                # 它们是"终止环"，命中即合法，不受邻域约束。
                if (allowed is not None and t not in allowed
                        and dst_type not in _TERMINAL_TYPES):
                    continue
                if t not in seen:
                    seen.add(t)
                    hits.append(t)

        if samples_only is not None and len(hits) > samples_only:
            hits = hits[:samples_only]

        step = StepResult(src_type=src_type, rel=rel, dst_type=dst_type,
                          required=required, nodes=hits)
        if hits:
            # partial：只有部分源节点有出边（说明链路不完整但不致命）
            n_src = max(1, len(sources))
            step.state = "present" if len(hits) >= n_src else "partial"
        else:
            step.state = "absent"

        result.steps.append(step)
        # 命中节点进结果集；来源节点单独记（用于保证中间环节点进子图，
        # 但**不能**混进命中集合，否则 sources 退化到全量时会带入大量孤立节点）。
        visited.update(hits)
        for s in sources:
            if s in graph.nodes:
                visited.add(s)

        if not hits:
            if required:
                result.failed_required = True
                result.missing_required.append(rel)
                break
            else:
                # 可选环缺失：记录后继续（后续环可能从别的源接上）
                frontier = []
                continue
        frontier = hits

    # 链状态只看「必须环有没有实例」，不看是否完全覆盖：
    #   present —— 所有必须环都有实例，且每环自身也是 present（全覆盖）
    #   partial —— 必须环都有实例，但某环只覆盖了部分源节点
    #   absent  —— 有必须环零实例（循环里已 break 并记录 failed_required）
    req_steps = [s for s in result.steps if s.required]
    if result.failed_required or any(not s.nodes for s in req_steps):
        result.state = "absent"
    elif not req_steps:
        result.state = "present"
    elif all(s.state == "present" for s in req_steps):
        result.state = "present"
    else:
        result.state = "partial"
    return result, visited


# ---------------------------------------------------------------------------
# 覆盖与缺口
# ---------------------------------------------------------------------------
def _coverage(graph: POGraph, sub: POGraph) -> Dict[str, Any]:
    """空覆盖统计：schema 有类/关系但图上零实例，或子图内零实例。"""
    from ..po.concepts import CONCEPT_SPECS, RELATION_DOMAIN_RANGE

    used_classes = {n.type for n in sub.nodes.values()}
    used_rels = {a.relation for a in sub.assertions}
    graph_classes = {n.type for n in graph.nodes.values()}
    graph_rels = {a.relation for a in graph.assertions}

    return {
        "classes_empty_in_graph": sorted(set(CONCEPT_SPECS) - graph_classes),
        "relations_empty_in_graph": sorted(set(RELATION_DOMAIN_RANGE) - graph_rels),
        "classes_missing_in_slice": sorted(set(CONCEPT_SPECS) - used_classes),
        "relations_missing_in_slice": sorted(set(RELATION_DOMAIN_RANGE) - used_rels),
    }


def _gaps(graph: POGraph, chains: List[ChainResult]) -> List[Dict[str, Any]]:
    """把链缺口翻译成 phase 1 可直接消费的 gap 列表。"""
    out: List[Dict[str, Any]] = []
    for c in chains:
        for s in c.steps:
            if s.required and not s.nodes:
                out.append({"rule": "R_chain", "chain": c.name, "rel": s.rel,
                            "gap": f"{s.src_type} 无 {s.rel} 指向 {s.dst_type}",
                            "severity": "高"})
            elif not s.required and not s.nodes:
                out.append({"rule": "R_chain_optional", "chain": c.name,
                            "rel": s.rel,
                            "gap": f"{s.src_type} 缺 {s.rel} → {s.dst_type}",
                            "severity": "低"})
    # 已知断链转成结构性缺口
    for key, info in KNOWN_BROKEN.items():
        out.append({"rule": "R_struct", "chain": key, "gap": info["issue"],
                    "workaround": info["workaround"], "severity": "中"})
    return out


def _blockers(view: str, chains: List[ChainResult],
              sub: POGraph) -> List[str]:
    """硬阻塞：profile 声明的必须链，其必须环没有实例。

    只用 `missing_required`（哪个必须环断了）判定，不看链的 state：
    链 state=partial 表示"链路可走但不完整"，属于警告而非阻塞。
    """
    req = SLICE_PROFILES[view]["require"]
    if not sub.nodes:
        return ["subgraph_empty"]
    blocks: List[str] = []
    by_name = {c.name: c for c in chains}
    for name in req:
        c = by_name.get(name)
        if c is None:
            blocks.append(f"chain_missing:{name}")
        elif c.missing_required:
            blocks.append(f"chain_broken:{name}({','.join(c.missing_required)})")
    return blocks


# ---------------------------------------------------------------------------
# 契约渲染（人可读的链式树）
# ---------------------------------------------------------------------------
_STATE_MARK = {"present": "✓", "partial": "~", "absent": "✗"}


def render_contract(contract: Dict[str, Any], view: Optional[str] = None) -> str:
    """把 contract 渲染成你画的那种链式树（带三态标记）。

    输出示例：
        Paper paper:01
          ├─FORMULATES──> ResearchQuestion ✓ [question:01]
          │   └─OPERATIONALIZED_AS──> Task ✓ [task:01]
          ...
    """
    v = view or contract.get("view", "full")
    lines: List[str] = [
        f"# GraphSlice  view={v}  anchor={contract.get('anchor')}",
        f"# nodes={contract['subgraph']['n_nodes']}  "
        f"assertions={contract['subgraph']['n_assertions']}  "
        f"fingerprint={contract['fingerprint'][:16]}…",
        f"# blockers={contract['blockers'] or '无'}",
        "",
    ]

    def walk(chain: Dict[str, Any], depth: int) -> None:
        steps = chain["steps"]
        for i, s in enumerate(steps):
            mark = _STATE_MARK[s["state"]]
            pad = "  " * depth + ("├─" if i < len(steps) - 1 else "└─")
            rel_flag = "" if s["required"] else " (可选)"
            nodes = ", ".join(s["nodes"][:3])
            more = f" …共{s['n']}" if s["n"] > 3 else ""
            lines.append(f"{pad}{s['rel']}──> {s['dst_type']} "
                         f"{mark}{rel_flag} [{nodes}{more}]")

    for c in contract["chains"]:
        lines.append(f"## {c['chain']}  →  {c['state'].upper()}")
        walk(c, 1)
        if c["missing_required"]:
            lines.append(f"   ⚠ 缺必须环: {c['missing_required']}")
        lines.append("")

    cov = contract["coverage"]
    lines.append("## 空覆盖")
    if cov["classes_empty_in_graph"]:
        lines.append(f"  类(全图无实例): {cov['classes_empty_in_graph']}")
    if cov["relations_empty_in_graph"]:
        lines.append(f"  关系(全图无边): {cov['relations_empty_in_graph']}")
    lines.append("")

    lines.append(f"## 缺口 ({len(contract['gaps'])} 条)")
    for g in contract["gaps"][:10]:
        lines.append(f"  [{g['severity']}] {g.get('chain')}: {g['gap']}")
    if len(contract["gaps"]) > 10:
        lines.append(f"  … 还有 {len(contract['gaps']) - 10} 条")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def slice_for_task(graph: POGraph, view: str = "full",
                   anchor: Optional[str] = None) -> GraphSlice:
    """按视图切出子图 + 契约。

    参数：
        graph  : 源图（只读，不会被修改）
        view   : SLICE_PROFILES 的键之一
        anchor : 锚点节点 id（如 "paper:01"）；None 表示全图
    返回：
        GraphSlice(subgraph, contract)
    """
    if view not in SLICE_PROFILES:
        raise ValueError(f"未知视图 {view!r}，可选：{sorted(SLICE_PROFILES)}")
    prof = SLICE_PROFILES[view]
    samples_only = prof.get("samples_only")

    sub = POGraph(f"slice::{view}::{anchor or 'all'}")
    chains: List[ChainResult] = []
    touched: set = set()

    # 锚点邻域：有 anchor 时先算可达集合，作为所有链的硬边界
    allowed = _reachable(graph, anchor) if (anchor and anchor in graph.nodes) else None

    for cname in prof["chains"]:
        cr, hits = _run_chain(graph, cname, CHAIN_MAP[cname], anchor,
                              samples_only=samples_only, allowed=allowed)
        chains.append(cr)
        touched |= hits

    # 把 anchor 自己也算进去
    if anchor and anchor in graph.nodes:
        touched.add(anchor)

    # 按 max_nodes 截断：优先级 anchor > required 链命中 > 其余
    # 注意 anchor 必须永远保留，否则边全断（它是一切的根）。
    cap = prof["max_nodes"]
    if len(touched) > cap:
        priority: List[str] = []
        if anchor and anchor in graph.nodes:
            priority.append(anchor)
        for c in chains:
            for s in c.steps:
                if s.required:
                    priority.extend(s.nodes)
        ordered = list(dict.fromkeys(priority + sorted(touched)))
        touched = set(ordered[:cap])
        # 截断后要保证 anchor 在
        if anchor and anchor in graph.nodes:
            touched.add(anchor)

    # 导节点
    for nid in touched:
        src = graph.nodes.get(nid)
        if src is None:
            continue
        sub.node(src.id, src.type, src.label, **dict(src.attrs))

    # 导边：两个端点都在子图内才导（保证子图闭合，无悬空边）
    # 注意 assert_rel 的签名是 (source, target, relation) —— target 在前！
    for a in graph.assertions:
        if a.source in sub.nodes and a.target in sub.nodes:
            sub.assert_rel(a.source, a.target, a.relation,
                           attribution=a.attribution,
                           evidence_ids=a.evidence_ids)

    contract: Dict[str, Any] = {
        "view": view,
        "anchor": anchor,
        "desc": prof["desc"],
        "chains": [c.to_dict() for c in chains],
        "coverage": _coverage(graph, sub),
        "gaps": _gaps(graph, chains),
        "known_broken": KNOWN_BROKEN,
        "subgraph": {"n_nodes": len(sub.nodes),
                     "n_assertions": len(sub.assertions)},
    }
    # 指纹：对契约的稳定部分哈希（不含 subgraph 统计，避免节点数抖动影响锁）
    stable = {k: v for k, v in contract.items() if k != "subgraph"}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    contract["fingerprint"] = "sha256:" + hashlib.sha256(
        payload.encode("utf-8")).hexdigest()

    contract["blockers"] = _blockers(view, chains, sub)
    return GraphSlice(view=view, anchor=anchor, subgraph=sub, contract=contract)


def slice_views() -> List[str]:
    """可用的视图名列表。"""
    return list(SLICE_PROFILES)
