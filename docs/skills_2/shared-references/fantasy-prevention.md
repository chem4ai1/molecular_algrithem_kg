# fantasy-prevention · 理论主张的 5 门反幻想

> 源文件：`skills/shared-references/fantasy-prevention.md`（150 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 定主张 + 阶段5 自检 |
| **SciForge 26 节点** | `2.5`/`10` |
| **输入节点（对齐）** | `Claim`；`Assumption` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议新增的 `Claim`，5 门结果写入 `GateVerdict.checks[]`，不额外新增 |

## 1. 解决的问题
### 1.1 核心问题
阻止「理论自洽但无现实证据」的 fantasy claim；目标是标记而非消灭。
### 1.2 为什么需要
`Every theoretical claim must be traceable to either (a) a verified derivation, (b) a verified citation, or (c) an explicit assumption with a reasonability score.`
### 1.3 不做的后果
把猜想写成既定结论，或反之把有价值的标注猜想删掉。

## 2. 输入
### 2.1 输入知识节点
`Claim.derivation_chain / citation / assumptions.reasonability / counterexample_check / data_availability`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `/adversarial-falsification` 执行 5 gates。
### 2.3 输入产物
`adversarial-falsification/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`FantasyVerdict.gates_passed / verdict / failed_gates`；`FantasyLog.status`。
### 3.2 输出产物
`refine-logs/fantasy-log.md`：`Claim / Phase / Gate Failed / Reason / Action / Status`。
### 3.3 传递片段
FANTASY / MOSTLY_FANTASY 阻断 paper writing；WEAKLY_GROUNDED 必须写 Limitations。

## 4. 判定与门
| 门 | 判据 |
|---|---|
| Gate1 | derivation / citation / assumption 三源之一 |
| Gate2 | 3-layer verified reference |
| Gate3 | 致命假设 `reasonability<5` → WARN |
| Gate4 | 未压力测试 → WARN |
| Gate5 | 数据 NO → FANTASY |
| 分级 | 5/5 GROUNDED；4/5 MOSTLY；3/5 WEAKLY；2/5 MOSTLY_FANTASY；0–1/5 FANTASY |

## 5. 上下游
`/adversarial-falsification` 执行 → 本契约 → `/result-to-claim`、`/paper-writing`、`/rebuttal`。

## 6. 映射
对「某算法优于基线/可迁移」类结论强制证据链、反例、数据可得性与假设评分。
