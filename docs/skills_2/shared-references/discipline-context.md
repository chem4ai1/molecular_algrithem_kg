# discipline-context · 单一 general 管线，无学科分支

> 源文件：`skills/shared-references/discipline-context.md`（91 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `Paper`；`DISCIPLINE_CONTEXT` |
| **输出节点（对齐）** | 无（general no-op） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：单一 general 管线约束，不产生节点 |

## 1. 解决的问题
### 1.1 核心问题
规定 OSS 只有单一 `/auto-pipeline`，迁移 skill 的 `DISCIPLINE_CONTEXT` 是 general no-op stub。
### 1.2 为什么需要
防 4 overlays × 16 = 64 膨胀、任意聚类/跨学科误路由；领域方法交运行时。
### 1.3 不做的后果
重新引入学科分派，管线组合爆炸。

## 2. 输入
### 2.1 输入知识节点
`DISCIPLINE_CONTEXT.discipline / sub_discipline / target_venue`；`Pipeline.discipline`；`Reviewer.persona`；`SourcePriority.default`；`RecencyWindow.months`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`Treat every run as discipline=general`；删除 "if discipline=economics"。
### 2.3 输入产物
`venue-profiles.md`、`idea-dag-schema.md`、`mcts-search-protocol.md`、`multi-fidelity-evaluation.md`、`assurance-contract.md`。

## 3. 输出
### 3.1 输出知识节点
`DISCIPLINE_CONTEXT.discipline=general`；`Pipeline.branch=none`；`Reviewer.persona=senior-reviewer-agnostic`；`Framework=none`；INV-G1。
### 3.2 输出产物
`DISCIPLINE_CONTEXT.yaml`（`discipline/sub_discipline/target_venue`）；无新增产物。
### 3.3 传递片段
禁 overlays / domain-specific persona；Always 交 `/theory-derivation`、`/dynamic-sandbox`。

## 4. 判定与门
无机械门；`Never reintroduce discipline dispatch`。

## 5. 上下游
migrated skills → 本契约 → OSS 通用 skills / general 行 / INV-G1。

## 6. 映射
分子项目不设 chemistry branch，按 `general + runtime reasoning` 设计。
