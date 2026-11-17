# mcts-search-protocol · 想法 DAG 上的 UCB 搜索协议

> 源文件：`skills/shared-references/mcts-search-protocol.md`（308 行） · 类型：shared-reference（协议）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `2.5` |
| **输入节点（对齐）** | `IdeaDAG`；`IdeaNode` |
| **输出节点（对齐）** | `IdeaNode.ucb_score`/`visits` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议的 `IdeaDAG`；UCB 状态作为 IdeaNode 属性 |

## 1. 解决的问题
### 1.1 核心问题
用 MCTS + UCB 平衡 exploration / exploitation，避开 BFS 太慢与 DFS 一条路死的陷阱。
### 1.2 为什么需要
`The goal is to balance exploration (trying under-visited ideas) and exploitation (deepening promising ideas)`；欠访问路径随 N_total 增长被重试。
### 1.3 不做的后果
局部伪技巧（`false trick`）长期占据搜索预算。

## 2. 输入
### 2.1 输入知识节点
`fidelity_scores.{low,mid,high}.score`；`visits`；`search_metadata.total_visits / exploration_constant_c`；`engineering_grounding.eg_tier`；`crossover_parents`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；Simulation starts at `low_fidelity`；mutation 只改 exactly one dimension；crossover 需 ≥2 parents；Max 1 crossover per iteration。
### 2.3 输入产物
`idea-dag-schema.md`。

## 3. 输出
### 3.1 输出知识节点
`node.ucb_score / V_idea`；state ∈ low/mid/high_fidelity / promoted / pruned；`promoted_ids / best_score / best_idea_id / total_iterations`。
### 3.2 输出产物
`refine-logs/IDEA_DAG.json`：`ucb_score / visits / promoted_ids`。
### 3.3 传递片段
无。

## 4. 判定与门
`UCB = V_idea + c√(lnN/n) + βEG`；βEG：READY +0.05 / CONSTRAINED 0 / HEAVY -0.05 / Extreme -0.10 / BLOCKED exclude；0.5 / 0.65 / 0.75 三档；`mid<low*0.7` 重试否则 prune；预算 cs-ml 30 GPU-h。

## 5. 上下游
`/idea-discovery` Phase 2.5 → 本协议 → IDEA_DAG 扩展/评估、`/novelty-check`。

## 6. 映射
对每个分子生成假设跑低文本 → 中 proxy dock/property → 高全训练/模拟；EG 避免只追易实现但平庸的 oracle 路线。
