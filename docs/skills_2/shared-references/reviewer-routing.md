# reviewer-routing · 评审输入/输出路由与结果落地

> 源文件：`skills/shared-references/reviewer-routing.md`（182 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 + 阶段5 |
| **SciForge 26 节点** | `14` |
| **输入节点（对齐）** | `ReviewPoint` |
| **输出节点（对齐）** | `ReviewPoint.severity` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：FATAL/WEAK 等分级已由 severity 字段承载 |

## 1. 解决的问题
### 1.1 核心问题
规定评审路由、reviewer 隔离、结果按设计稿/统计/机制/叙事分类落地，并区分 `WEAK / FATAL / NOVELTY_FAILURE / CONTRADICTION`。
### 1.2 为什么需要
`Reviewer output must be physically isolated from the writer`；`never fused into one grand "revision prompt"`；评审等级决定修复路径。
### 1.3 不做的后果
自评串味、修订方向错误（把 FATAL 当 WEAK 改措辞）。

## 2. 输入
### 2.1 输入知识节点
`Feedback.class ∈ design/statistical/mechanistic/narrative`；`Feedback.severity ∈ FATAL/WEAK/NOVELTY_FAILURE/CONTRADICTION`；`route`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `auto-review-loop/SKILL.md` 消费。
### 2.3 输入产物
`reviewer-independence.md`、`review-tracing.md`、`output-protocol.md`。

## 3. 输出
### 3.1 输出知识节点
`ReviewState`；`route.target`；`fix_plan`；`verdict`。
### 3.2 输出产物
`AUTO_REVIEW.md`、`REVIEW_STATE.json`、`REVIEW_REPORT.md`、`KILL_ARGUMENT.md`。
### 3.3 传递片段
无。

## 4. 判定与门
FATAL → 停止定稿；WEAK → 修复清单；NOVELTY_FAILURE → BA 回 Phase2；CONTRADICTION → 回 Phase8/10；物理隔离。

## 5. 上下游
auto-review-loop → 本契约 → kill-argument / paper-writing / result-to-claim / Phase2。

## 6. 映射
按致命度决定回退：FATAL 阻断，NOVELTY_FAILURE 换题，WEAK 修稿；评审与写作严格隔离。
