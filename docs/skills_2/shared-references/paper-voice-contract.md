# paper-voice-contract · 论文书面语气与禁区

> 源文件：`skills/shared-references/paper-voice-contract.md`（131 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionDraft`；`Claim.fidelity` |
| **输出节点（对齐）** | `SectionDraft`(voice) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：措辞强度由已建议的 `Claim.fidelity` 约束 |

## 1. 解决的问题
### 1.1 核心问题
把学术论文语气与「助手讲话」严格分开，避免 agent 自述、推销式措辞、自相矛盾语气。
### 1.2 为什么需要
论文的 voice 由 contract 决定，不由模型默认风格；`Phantom artifacts and schema drift` 同样适用于语气。
### 1.3 不做的后果
正文出现「我们在这项工作中证明了」但只有数值证据，或混入工具/过程自述。

## 2. 输入
### 2.1 输入知识节点
`Section.voice / claim_language / hedging_level`；`output-language.md` 7 维；`claim.fidelity`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `/paper-writing` 消费。
### 2.3 输入产物
`output-language.md`、`discipline-writing.md`、`citation-discipline.md`。

## 3. 输出
### 3.1 输出知识节点
`Claim.allowed_wording`（proven/supported/suggests）；`Section.voice`；`hedging_level`。
### 3.2 输出产物
`paper/sections/*.tex`；`main.tex`。
### 3.3 传递片段
措辞强度必须匹配 fidelity；禁「novel」无 baseline、禁绝对化形容。

## 4. 判定与门
无机械门；由 `/leakage-scan`、`/auto-review-loop` 与 claim fidelity 交叉校验。

## 5. 上下游
`/domain-signature` + `output-language` → 本契约 → `/paper-writing`、`/paper-compile`、`/rebuttal`。

## 6. 映射
`fidelity=symbolic/numerical/qualitative` 分别对应 `proven/supported/suggests`，越级即阻断。
