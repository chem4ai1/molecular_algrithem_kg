# output-language · 7 维输出语言与语气控制

> 源文件：`skills/shared-references/output-language.md`（183 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionDraft` |
| **输出节点（对齐）** | `SectionDraft.language`/`register` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `SectionDraft` 加 language/register 属性，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
规定助手输出语言的 7 个维度（language / register / audience / individualism / mimesis / density / affect），取代随手改 prompt。
### 1.2 为什么需要
`The default is register=5, audience=3, individualism=4, mimesis=4, density=4, affect=2.`；规格用户请求必须遵守。
### 1.3 不做的后果
风格靠反复手调 prompt，不可复用也不可预测。

## 2. 输入
### 2.1 输入知识节点
`OUTPUT_LANGUAGE` 7 维设置；`user prompt override`；`target.venue`。
### 2.2 输入 prompt 模板 / 契约
`Mimesis = 4 — stylistic alignment to target...`；`Mimesis = 5 — extremal mimesis forbidden.`
### 2.3 输入产物
`paper-voice-contract.md`、`discipline-writing.md`。

## 3. 输出
### 3.1 输出知识节点
7 维设置；venue-specific tone；nonverbal formatting；中文输出译文契约；English academic register。
### 3.2 输出产物
无新增文件；影响所有 paper sections / review / rebuttal 文本。
### 3.3 传递片段
默认英语学术语气；中文输出译英文成果；禁极端模仿。

## 4. 判定与门
无机械门；`register=5 / audience=3 / individualism=4 / mimesis=4 / density=4 / affect=2`；`Mimesis=5 forbidden`。

## 5. 上下游
全局 output config → 本契约 → paper-writing / rebuttal / review / 所有助手文本。

## 6. 映射
输出中文解读时按 density/affect 控制，保持学术语气；论文正文按 venue tone。
