# idea-dag-schema · 想法 DAG 的单一真源 schema

> 源文件：`skills/shared-references/idea-dag-schema.md`（241 行） · 类型：shared-reference（schema）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `2.5` |
| **输入节点（对齐）** | `IdeaNode`(paperapp) |
| **输出节点（对齐）** | `IdeaDAG.nodes/edges` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议新增的 `IdeaDAG`：现有 `IdeaNode` 无 multi-parent crossover 边 |

## 1. 解决的问题
### 1.1 核心问题
统一存储想法搜索空间、演化历史与保真度/UCB 状态；用 DAG 表示 mutation 与 crossover。
### 1.2 为什么需要
树不能表示 crossover 多父；普通图破坏时间因果；Fusion Node 以 DAG 替代 hyperedge。
### 1.3 不做的后果
融合想法谱系丢失；pruned idea 被重新评估。

## 2. 输入
### 2.1 输入知识节点
`DISCIPLINE_CONTEXT.discipline`；`DATA_INSIGHT_REPORT.md`；`idea_dag.nodes[].idea_sketch / fidelity_scores / ucb_score / visits`；`data_fit_flags`。
### 2.2 输入 prompt 模板 / 契约
`DAG is the optimal abstraction. Nodes = idea states. Edges = mutation (iteration) or crossover (combination).`
### 2.3 输入产物
`mcts-search-protocol.md`。

## 3. 输出
### 3.1 输出知识节点
`idea_dag.nodes / edges / root_ids / promoted_ids / pruned_ids`；`search_metadata.total_visits / max_iterations / best_idea_id`；`pruned_reason`。
### 3.2 输出产物
`refine-logs/IDEA_DAG.json`：`schema_version 1.1 / nodes / edges / metadata`。
### 3.3 传递片段
consumers MUST ignore unknown fields；pruned idea 可作 crossover_parent 但 never re-evaluate。

## 4. 判定与门
low≥0.5 → mid；mid≥0.65 → high；high≥0.75 → promoted，否则 pruned；`data_fit_flags` 任一 blocked → low fidelity prune；constrained → low score capped at 0.6。

## 5. 上下游
`/idea-discovery` Phase 2.5 → 本 schema → idea-discovery 自消费、novelty-check、auto-review-loop。

## 6. 映射
用 IDEA_DAG.json 记录分子生成策略的 mutation/crossover、EG 与 data_fit_flags。
