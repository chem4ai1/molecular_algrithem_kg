# skill-config · 单一配置源与 no-op 迁移契约

> 源文件：`skills/shared-references/skill-config.md`（100 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `RunState`(配置) |
| **输出节点（对齐）** | 无 |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `RunState` 作为单一配置源载体 |

## 1. 解决的问题
### 1.1 核心问题
把 skill 的可配置项集中到一处，迁移 skill 的 discipline 配置为 general no-op。
### 1.2 为什么需要
避免每个 SKILL.md 内嵌配置副本造成漂移。
### 1.3 不做的后果
改了配置只有部分 skill 生效。

## 2. 输入
### 2.1 输入知识节点
`RunConfig.effort / assurance / output_language / plugin_router`；`DISCIPLINE_CONTEXT` no-op；`config.source`。
### 2.2 输入 prompt 模板 / 契约
`configuration must be loaded from a single external source`；与 `discipline-context.md`、`effort-contract.md`、`assurance-contract.md` 同源。
### 2.3 输入产物
`AGENT_DOC.md`、`config.yaml`、各 SKILL.md。

## 3. 输出
### 3.1 输出知识节点
`config` 单一真源；no-op discipline 设置。
### 3.2 输出产物
无新增文件；配置由全局源注入。
### 3.3 传递片段
无。

## 4. 判定与门
无机械门；不得在 SKILL.md 内复制配置值。

## 5. 上下游
全局 config → 本契约 → 所有 skill 与 orchestrator。

## 6. 映射
`src/capfactory/paperapp/config.yaml` 与 `paperapp/config.py` 是本项目单一配置源。
