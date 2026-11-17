# pipeline-integrity · 反「看似完成」的运行完整性

> 源文件：`skills/shared-references/pipeline-integrity.md`（243 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `16` |
| **输入节点（对齐）** | 全部产物；`RunArtifact` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 用 `RunArtifact` 存在性 + `FailureCheck` 记录三硬门，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
针对「FINAL REPORT 声称全套完成，但 PDF 不存在、章节空、verdict 缺失」这类假完成，设定完整性硬门。
### 1.2 为什么需要
`No FINAL_REPORT.md until three gates pass`；`Score means nothing if the paper doesn't exist.`
### 1.3 不做的后果
用户拿到空壳交付，且信誉受损。

## 2. 输入
### 2.1 输入知识节点
`compiled_pdf.exists / sections_nonempty / figures_embedded / OVERRIDE / manifest.phase_coverage`；`verdicts.complete`；`claim_audit`；`source_evidence`。
### 2.2 输入 prompt 模板 / 契约
`No Final Report until: compiled PDF exists, sections non-empty, figures embedded.`；`Do not use auto-pipeline to claim work that did not happen.`
### 2.3 输入产物
`auto-pipeline/SKILL.md` Phase16、`output-manifest.md`、`assurance-contract.md`、`artifact-registry.md`。

## 3. 输出
### 3.1 输出知识节点
`PipelineIntegrityGate`；`ARTIFACT_COMPLETE`；`MANIFEST_COVERAGE`；`SUBMISSION_READY`；`FinalReport`。
### 3.2 输出产物
`FINAL_REPORT.md`；`PIPELINE_STATUS.md`；`RUN_PREPRINT.md`；`LESSONS.json`；`FIGURE_AUDITS.json`。
### 3.3 传递片段
无。

## 4. 判定与门
三硬门（PDF 存在 / sections 非空 / 图嵌入）全 true；verdict 完整；evidence 必须来自产物；缺项 BLOCKED。

## 5. 上下游
auto-pipeline / artifact-registry / output-manifest → 本契约 → FINAL_REPORT 与用户交付。

## 6. 映射
`run` 结束前必须验证 `paper/main.pdf` 存在、章节非空、图嵌入；否则 `pipeline_integrity=BLOCKED`。
