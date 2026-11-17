# reviewer-independence · 跨模型、盲审、强制反例的评审独立性

> 源文件：`skills/shared-references/reviewer-independence.md`（285 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 反驳预演 + 阶段5 |
| **SciForge 26 节点** | `14` |
| **输入节点（对齐）** | `ReviewPoint` |
| **输出节点（对齐）** | `ReviewState`/`ReviewLedger` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `ReviewState`/`ReviewLedger`；model_ids 为关键属性 |

## 1. 解决的问题
### 1.1 核心问题
确保 reviewer 不是 agent 自评：blind trace、强制反例、跨模型复核、证据引用。
### 1.2 为什么需要
`reviewer is a separate process or model`；`with supporting evidence (file path + line or quote)`；`autoReviewer` 从未运行不算 review。
### 1.3 不做的后果
自评虚高、同类领域盲区被系统性漏掉、无人能指出「图里没有这张表」。

## 2. 输入
### 2.1 输入知识节点
`reviewer.model_id / independence / trace_id / reviewer_role`；`counterexample`；`weakest claim`；`evidence.quote`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；被 auto-review-loop / kill-argument / citation-audit 消费。
### 2.3 输入产物
`review-tracing.md`、`assurance-contract.md`、`output-protocol.md`。

## 3. 输出
### 3.1 输出知识节点
`ReviewReport`；`BLINDSPOT_CHECK`；`ReviewLedger`；`counterexample_pass`；`verdict`。
### 3.2 输出产物
`REVIEW_REPORT.md`、`BLINDSPOT_CHECK.json`、`REVIEW_LEDGER.json`、`REVIEW_STATE.json`。
### 3.3 传递片段
无。

## 4. 判定与门
跨模型 ≥2 个 model_id；每条 finding 必引证据；强制反例必做；有 FATAL 不得 PASS；trace 可追。

## 5. 上下游
auto-review-loop / auto-pipeline → 本契约 → kill-argument / citation-audit / publishability-score。

## 6. 映射
`ReviewState.model_ids[]` 至少 2 个，fatal cap 覆盖 raw score（DK-P4-11）。
