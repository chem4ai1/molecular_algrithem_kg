# paper-modes · 按验证类型选论文章节集

> 源文件：`skills/shared-references/paper-modes.md`（207 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 章节规划 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `Contribution`；`EvidenceNorm` |
| **输出节点（对齐）** | `SectionPlan`(claims/word_budget) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：`SectionPlan` 已有 claims/evidence_refs/word_budget |

## 1. 解决的问题
### 1.1 核心问题
按 `verification_type` 选 4+1 条 structure path 与对应的章节集，避免所有论文同一模板。
### 1.2 为什么需要
`Mode determines WHICH sections exist, not their content.`；内容写法由 `discipline-writing.md` 负责。
### 1.3 不做的后果
理论实验混合论文套错结构。

## 2. 输入
### 2.1 输入知识节点
`verification_type ∈ pure_theory / derivational / empirical / computational / survey`；`MainOutputs`；`qual_fidelity`；`mode.metrics`；`mode.sections`。
### 2.2 输入 prompt 模板 / 契约
`Rules: 1) sections is a list of section identifiers... 2) MainOutputs... 3) qual_fidelity... 4) metrics... 5) sections contains no unknown section names.`
### 2.3 输入产物
`domain-adaptation-contract.md`、`verification-routing.md`、`paper-writing/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`PAPER_PLAN.md`：mode / reason / sections / MainOutputs / essential_results；`paper-mode.json`。
### 3.2 输出产物
`paper/PAPER_PLAN.md`、`refine-logs/paper-mode.json`；extras 数组。
### 3.3 传递片段
无。

## 4. 判定与门
仅 5 合法 mode；`_FOUND` 占位符 → BLOCKED；extras 已知且有序（Outcomes/Analysis before Conclusion），不允许 duplicate / Headings / References / Abstract。

## 5. 上下游
`/verification-routing` → 本契约 → `/paper-writing`、`/auto-review-loop`、`/publishability-score`。

## 6. 映射
`verification_type` 决定章节集；`Paper.evidence_norm` 决定 essential_results。
