# domain-failure-modes · 领域失败模式目录

> 源文件：`skills/shared-references/domain-failure-modes.md`（105 行） · 类型：shared-reference（目录）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 + 阶段4 + 阶段5 |
| **SciForge 26 节点** | `2.5`/`7`/`14` |
| **输入节点（对齐）** | `FailureMode`(global) |
| **输出节点（对齐）** | `FailureMode.detection` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：`FailureMode` 已有 severity/detection/domain_tags 字段 |

## 1. 解决的问题
### 1.1 核心问题
把「每个领域知道自己怎么失败」做成可查询目录，供证伪与泄露审计消费。
### 1.2 为什么需要
`Every domain knows how it fails.`；`This catalog makes that knowledge available to the agent.`
### 1.3 不做的后果
审稿盲区检查靠 LLM 自由联想，无领域针对性。

## 2. 输入
### 2.1 输入知识节点
`evidence_type / methodology_profile / failure_mode_profile.common_failures`；`Failure Mode.Description / Domains / Detection Method / Severity`。
### 2.2 输入 prompt 模板 / 契约
`queries this catalog using the signature's evidence_type and methodology_profile`；`selected failure modes are added to /adversarial-falsification and /leakage-audit`。
### 2.3 输入产物
`/domain-signature`、`/domain-learner`、`domain-signature-consumer.md`、`BLINDSPOT_CHECK.schema.json`。

## 3. 输出
### 3.1 输出知识节点
`FailureMode{name, description, domains, detection_method, severity}`；selected failure modes。
### 3.2 输出产物
`/adversarial-falsification` 的 failure_mode_source；`/leakage-audit` 的 selected modes；`BLINDSPOT_CHECK.schema.json` 的 severity score cap；`startup-log.md`。
### 3.3 传递片段
`The agent must check if a failure mode applies.`；`Do not treat this as a checklist. Treat it as a reference`。

## 4. 判定与门
无机械门；Severity=fatal/severe；catalog never complete；severity domain-dependent；only known, well-documented；无 speculative。

## 5. 上下游
`/domain-signature`（hint）+ `/domain-learner` → 本目录 → `/adversarial-falsification`、`/leakage-audit`、`/auto-review-loop`。

## 6. 映射
本项目 `FailureCheck{status,note}+CHECK_OF` 可承载选中失败模式。
