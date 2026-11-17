# multi-fidelity-evaluation · 想法三档保真度评估

> 源文件：`skills/shared-references/multi-fidelity-evaluation.md`（185 行） · 类型：shared-reference（协议）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `2.5` |
| **输入节点（对齐）** | `IdeaNode` |
| **输出节点（对齐）** | `IdeaDAG.fidelity_scores` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议的 `IdeaDAG`；三档分数是节点属性 |

## 1. 解决的问题
### 1.1 核心问题
用 low/mid/high 三档保真度逐级验证想法，避免「文本听起来好」直接进高成本评估。
### 1.2 为什么需要
`High cost / high fidelity validation is not available until a problem is narrowed to ONE idea.`；low 档是纯文本，不需要跑。
### 1.3 不做的后果
昂贵实验预算被大量未筛想法耗尽。

## 2. 输入
### 2.1 输入知识节点
`fidelity_scores.low{score, rationale, bottlenecks}`；`mid{score, method, evidence}`；`high{score, method, evidence}`；`bottleneck.identification`。
### 2.2 输入 prompt 模板 / 契约
`Scores are computed as weighted sums per level`；见 `idea-dag-schema.md`。
### 2.3 输入产物
`idea-dag-schema.md`、`mcts-search-protocol.md`、`idea-discovery/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
三档 score / rationale / method / bottlenecks；`evidence_strength`；`promotion_gate`。
### 3.2 输出产物
IDEA_DAG.json 中 `fidelity_scores`；`IDEA_CANDIDATES.md`。
### 3.3 传递片段
无。

## 4. 判定与门
low≥0.5→mid；mid≥0.65→high；high≥0.75→promoted；`mid<low*0.7` → retry/lower；bottleneck 必识别并带 remedy。

## 5. 上下游
`/idea-discovery` → 本协议 → idea_dag nodes → MCTS / novelty-check。

## 6. 映射
低=文本/结构一致，中=小规模分子性质代理，高=完整基准与消融；逐级 gate 后再投算量。
