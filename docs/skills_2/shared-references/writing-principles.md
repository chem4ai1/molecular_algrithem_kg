# writing-principles · 12 条写作原则

> 源文件：`skills/shared-references/writing-principles.md`（104 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionDraft`；`Claim` |
| **输出节点（对齐）** | `SectionDraft` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `Claim`；12 条原则是文本约束，不建类 |

## 1. 解决的问题
### 1.1 核心问题
给出 12 条写作原则，约束结构与措辞（contribution 明确、claim 有证据、baseline 公平、图与文一致）。
### 1.2 为什么需要
`paper-modes.md` 管章节集、`discipline-writing.md` 管逐节写法，本文件管跨节通用原则。
### 1.3 不做的后果
章节齐全但论证松散、结论越级、图不支撑 claim。

## 2. 输入
### 2.1 输入知识节点
`Claim.statement / fidelity`；`Section.structure`；`Figure.claim`；`Baseline.comparison`；`Reference.support`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `/paper-writing`、`/auto-review-loop` 消费。
### 2.3 输入产物
`paper-modes.md`、`discipline-writing.md`、`paper-voice-contract.md`。

## 3. 输出
### 3.1 输出知识节点
12 条原则；`Section.compliance`；`Claim.support_check`。
### 3.2 输出产物
`paper/sections/*.tex`、`AUTO_REVIEW.md`。
### 3.3 传递片段
无。

## 4. 判定与门
无机械门；由 leakage-scan / claim-audit / auto-review-loop 检查越级措辞与无证据贡献声明。

## 5. 上下游
`/paper-modes` + `/discipline-writing` → 本原则 → `/paper-writing`、`/auto-review-loop`。

## 6. 映射
贡献声明必须链到 `Claim.fidelity` 与具体节点；图必须绑定 claim（DK-P4-01）。
