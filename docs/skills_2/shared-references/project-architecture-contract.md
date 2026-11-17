# project-architecture-contract · 零隐藏状态、零自动造文件的产物模型

> 源文件：`skills/shared-references/project-architecture-contract.md`（138 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | 全部产物声明 |
| **输出节点（对齐）** | 路径/所有权约束 |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：单一 canonical path / producer 约束由属性表达 |

## 1. 解决的问题
### 1.1 核心问题
规定「单一真相源 + 显式所有权 + 无自动新建目录/文件」的项目结构原则。
### 1.2 为什么需要
防止 phantom artifacts 与 schema drift；`Every artifact MUST have one canonical path, one producer skill, and a declared set of consumer skills.`
### 1.3 不做的后果
多写者覆盖、消费者读错副本、自动补齐掩盖缺件。

## 2. 输入
### 2.1 输入知识节点
`artifact.canonical_path / producer / consumers / schema`；`run_id / phase`；`state.stale`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；依赖 `artifact-registry.md`、`output-protocol.md`、`output-manifest.md`。
### 2.3 输入产物
各 SKILL.md 的 Output Shape / Inputs 声明。

## 3. 输出
### 3.1 输出知识节点
6 条硬约束（单一 canonical path / 单一 producer / 声明 consumers / schema / 不自动造文件 / stale 标注）。
### 3.2 输出产物
无新增文件；约束所有 skill 的落盘行为。
### 3.3 传递片段
无。

## 4. 判定与门
违反任一硬约束 → FAIL；producer 之外写入 → 冲突；schema 变更走 `output-versioning.md`。

## 5. 上下游
所有 skill → 本契约 → artifact-registry / output-protocol / output-manifest / integration-contract。

## 6. 映射
本项目写入白名单 `nodecache/registry/materialize` 与本契约同源；DRIFT 拒写。
