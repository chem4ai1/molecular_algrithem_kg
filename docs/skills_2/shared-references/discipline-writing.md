# discipline-writing · 跨领域逐节写法（Signature-Driven Writing）

> 源文件：`skills/shared-references/discipline-writing.md`（214 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionPlan`；`EvidenceNorm` |
| **输出节点（对齐）** | `SectionDraft`(task-w) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：逐节写法由 SectionDraft 的 INSTANCE_OF / USES_EVIDENCE 边承载 |

## 1. 解决的问题
### 1.1 核心问题
规定跨领域逐节写法：v2.1 起 `paper-modes.md` 定「哪些节」，本文件定「怎么写」。
### 1.2 为什么需要
OSS 无 per-discipline writing guide；保证 claim-support、notation、figure/table/equation/citation 一致。
### 1.3 不做的后果
每节写法随作者习惯漂移。

## 2. 输入
### 2.1 输入知识节点
`DomainSignature.evidence_type / writing_style / citation_format`；`PaperMode.section_set`；`Claim.support`；`Figure.render_script`；`Reference.key`；`Language.mode`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`/paper-writing` Section-Specific Guidelines；Signature-Driven Writing Rules 为分节规则源。
### 2.3 输入产物
`paper-modes.md` §2/§3；`citation-discipline.md`；`color-themes.md`；`output-versioning.md`；`main.tex`、`math_commands.tex`、`references.bib`。

## 3. 输出
### 3.1 输出知识节点
`Paper.section`；`Claim.acceptable_support`；`Notation.font_convention`；`Figure.caption / reference`；`Equation.cross_ref`；`Table.booktabs`；`Citation.format`；`Language.default/chinese`。
### 3.2 输出产物
`paper/main.tex`、`math_commands.tex`、`references.bib`、`figures`。
### 3.3 传递片段
Every claim has support；只用 `\cite/\citep/\citet` 且 key 必在 bib；never jet/rainbow/hsv。

## 4. 判定与门
`/citation-audit` final draft；禁 `\cite{TODO/forthcoming}`、禁混语言；显著性标记需 p 值阈值。

## 5. 上下游
`/domain-signature` → 本契约 → `/paper-writing` 逐节写法。

## 6. 映射
分子论文的 claim 必须挂到 `AlgorithmModule / Benchmark.model_results` 节点，图必须来自真实结果。
