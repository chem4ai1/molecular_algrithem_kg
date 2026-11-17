# schemas/README · 23 个 JSON Schema 索引

> 源文件：`skills/shared-references/schemas/README.md`（54 行） · 类型：shared-reference（索引）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | schema 文档 |
| **输出节点（对齐）** | 字段权威（无节点） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：索引文档，不产生节点 |

## 1. 解决的问题
### 1.1 核心问题
索引 23 个 schema 文件，规定「schema 是字段唯一权威，prose 只是解释」。
### 1.2 为什么需要
防 schema drift；所有 skill 输出必须按 schema 校验。
### 1.3 不做的后果
prose 与 schema 不一致时消费者按错字段解析。

## 2. 输入
### 2.1 输入知识节点
`schema.file / required_fields / validator`；`prose.description`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `artifact-registry.md` 指定 schema，各 skill 引用。
### 2.3 输入产物
23 个 JSON Schema（含 `PROOF_AUDIT.schema.json`、`PUBLISHABILITY_SCORE.schema.json`、`FIGURE_AUDITS.schema.json` 等）。

## 3. 输出
### 3.1 输出知识节点
schema 目录清单；字段名/类型/required。
### 3.2 输出产物
无新增文件；作为字段权威被下游引用。
### 3.3 传递片段
无。

## 4. 判定与门
输出不符合 schema → FAIL；字段变更走 `output-versioning.md`。

## 5. 上下游
artifact-registry → 本索引 → 各 skill 产物校验与 verifier。

## 6. 映射
本项目 `src/capfactory/*/schemas/` 同样需要索引与必填字段校验。
