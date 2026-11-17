# grounding-check · 理论结果的落地概率清单

> 源文件：`skills/shared-references/grounding-check.md`（80 行） · 类型：shared-reference（清单）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `10`/`12` |
| **输入节点（对齐）** | `Claim`；`Evidence` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议的 `Claim`；A–E 清单结果写入 `FailureCheck.note` |

## 1. 解决的问题
### 1.1 核心问题
检查理论结果是否在假设、反事实、数据算力与声明范围上具备落地概率。
### 1.2 为什么需要
数学完美但假设不现实等于零实际价值；连接 "theoretically sound" 与 "likely to work in practice"。
### 1.3 不做的后果
不可落地的理论结论直接进论文。

## 2. 输入
### 2.1 输入知识节点
`CLAIMS_FROM_RESULTS.md`；`confidence.grounding / theoretical`；A1–A4、B1–B4、C1–C4、D1–D4、E1–E5。
### 2.2 输入 prompt 模板 / 契约
`MANDATORY: After /result-to-claim produces CLAIMS_FROM_RESULTS.md, before /paper-writing begins`；`If someone tried to implement this, would it work?`
### 2.3 输入产物
`result-to-claim/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`verdict ∈ GROUNDED / MOSTLY GROUNDED / UNGROUNDED`；A–E verdicts；`confidence gap`；limitations。
### 3.2 输出产物
`CLAIMS_FROM_RESULTS.md`：grounding verdict / confidence gap。
### 3.3 传递片段
`Output: GROUNDED / MOSTLY GROUNDED / UNGROUNDED`。

## 4. 判定与门
All checks PASS → GROUNDED；1–3 WARN 无 FAIL → MOSTLY；Any FAIL → UNGROUNDED（写作前必改）；`reasonability<5` 需 workaround；failure modes≥3；analogy≥1。

## 5. 上下游
`/result-to-claim` → 本清单 → `/paper-writing`、`/auto-review-loop`。

## 6. 映射
生成模型/筛选规则写成 claim 前，逐项核验小样本、分布漂移、算力、可复现与适用 regime。
