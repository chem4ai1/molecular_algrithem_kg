# pipeline-adaptive-degradation · 可验证的降级路径

> 源文件：`skills/shared-references/pipeline-adaptive-degradation.md`（436 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `GateVerdict` |
| **输出节点（对齐）** | `FailureCheck.note` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `GateVerdict` 加 `degradation` 属性记录 trigger/substitute/impact |

## 1. 解决的问题
### 1.1 核心问题
把「跑不动就跳过」变成必须满足前置 + 强制替身 + 显式留痕的降级机制。
### 1.2 为什么需要
`Never silently degrade. Every fallback must be declared, justified, verified, and visible in the final report.`
### 1.3 不做的后果
用 skip 换通过率，论文声称完整实际缺关键阶段。

## 2. 输入
### 2.1 输入知识节点
`trigger.condition / evidence`；`substitute`；`label`；`reported_in_final`；`consequence_acknowledged`；`M1–M6`。
### 2.2 输入 prompt 模板 / 契约
`precondition + substitute + label + report`；`NO SILENT SKIP`。
### 2.3 输入产物
`domain-adaptation-guide.md`、`domain-contribution-protocol.md`、`startup-protocol.md`、`auto-pipeline/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`degradation_log`；`fallback.recorded_reason`；`boundary_verdict`；`PIPELINE_STATUS.md` 章节。
### 3.2 输出产物
`PIPELINE_STATUS.md`：Degradation Log 表（Stage / Trigger / Substitute / Impact / Reported）；`FINAL_REPORT.md`。
### 3.3 传递片段
无。

## 4. 判定与门
M1–M6 全覆盖；条件未满足直接降级 FAIL；替身必须执行并产出物；label 固定集；final report 可见；跳过无替代品 => BLOCKED。

## 5. 上下游
orchestrator / domain learner → 本契约 → 每个 phase 的 fallback 与 Final Report。

## 6. 映射
任何阶段降级都必须写清 trigger/substitute/impact/reported，禁止静默 skip。
