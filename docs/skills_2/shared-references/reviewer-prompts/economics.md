# reviewer-prompts/economics · 经济学专属 reviewer persona（已迁移）

> 源文件：`skills/shared-references/reviewer-prompts/economics.md`（52 行） · 类型：shared-reference（persona）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·历史存档 |
| **SciForge 26 节点** | — |
| **输入节点（对齐）** | 无 |
| **输出节点（对齐）** | 无 |
| **对齐状态** | 无法对齐 |
| **节点增补建议** | 不建议新增节点：已迁移的 persona 存档，不参与现行管线 |

## 1. 解决的问题
### 1.1 核心问题
记录经济学 reviewer persona 的旧格式标准（identification / external validity / mechanism）。
### 1.2 为什么需要
历史迁移产物；当前 OSS 已切换到 `/auto-pipeline` 单管线 + `discipline-context.md` general。
### 1.3 不做的后果
误把 persona 当活跃门，重新引入学科分支。

## 2. 输入
### 2.1 输入知识节点
`Reviewer.persona=economist`；`identification / external validity / mechanism`；`DISCIPLINE_CONTEXT`。
### 2.2 输入 prompt 模板 / 契约
`This file is retained ONLY as a historical migration reference. It is NOT loaded...`；`Do not condition on economics`.
### 2.3 输入产物
`discipline-context.md`（现行权威）。

## 3. 输出
### 3.1 输出知识节点
无活跃节点；仅历史标准（识别策略、外部效度、机制证据）。
### 3.2 输出产物
无新增文件。
### 3.3 传递片段
无。

## 4. 判定与门
无机械门；`Never reintroduce discipline dispatch`。

## 5. 上下游
历史 skill 迁移 → 本文件（仅存档）→ 现行 `discipline-context.md` general。

## 6. 映射
分子项目不建 chemistry persona，领域知识走 `DomainProfile` + `domain-failure-modes`。
