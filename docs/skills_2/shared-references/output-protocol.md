# output-protocol · 双层产物目录与执行即留痕

> 源文件：`skills/shared-references/output-protocol.md`（244 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | 全部阶段产物 |
| **输出节点（对齐）** | `RunArtifact`；`GateVerdict` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 同上；双层目录约定不新增类 |

## 1. 解决的问题
### 1.1 核心问题
统一双层输出目录（`.sciforge/verdicts/` 机器判定 + `.sciforge/audits/` 叙述报告）与执行证据。
### 1.2 为什么需要
`one verdict file per audited skill + one summary per phase`；`a dedicated log file with the skill name, timestamp, full prompt, and model response`。
### 1.3 不做的后果
只有总结无原始执行日志，无法证明门真的跑过。

## 2. 输入
### 2.1 输入知识节点
`artifact.path / role / producer / consumer`；`verdict.6 states`；`trace.log`；`sha256`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；被 orchestrator / artifact-registry / input-manifest 消费。
### 2.3 输入产物
`artifact-registry.md`（为保证唯一真相源，本所有者）。

## 3. 输出
### 3.1 输出知识节点
`artifact.path`；`MANIFEST.md`；6 态 verdict；`audited_input_hashes`。
### 3.2 输出产物
`refine-logs/`（研究内容）、`methods/`、`literature/`、`experiments/`、`derivations/`、`figures/`、`paper/`、`.sciforge/{verdicts,audits,manifest}/`。
### 3.3 传递片段
无。

## 4. 判定与门
6 态枚举；`state=PASS` 可继续；`FAIL/BLOCKED/ERROR` 阻 Final Report；manifest phase 完整性；SHA-256 必须记录。

## 5. 上下游
orchestrator / artifact-registry → 本契约 → 所有 skill 的落盘位置与日志格式。

## 6. 映射
所有 phase 产物按 `refine-logs/*` + `.sciforge/{verdicts,audits}/` 双层落盘，并记录输入 sha256。
