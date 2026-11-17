# domain-contribution-protocol · unknown evidence_type 的 PR 演进

> 源文件：`skills/shared-references/domain-contribution-protocol.md`（198 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·本体治理 |
| **SciForge 26 节点** | `16` 回写 |
| **输入节点（对齐）** | `DomainProfile` |
| **输出节点（对齐）** | 新 `evidence_type` 注册 |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用 paperapp 已有 `ClassRegistrationProposal`，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
把 `unknown_evidence_type` 经 PR 变成 first-class signature，而不是临时补丁。
### 1.2 为什么需要
有限字母表 + 领域持续演进；需要 bounded review contract。
### 1.3 不做的后果
每遇到新领域就改核心 schema，造成回归与漂移。

## 2. 输入
### 2.1 输入知识节点
`unknown_evidence_type / evidence_type / TDAL verdict / weakest_dimension / schema_version / worked example`。
### 2.2 输入 prompt 模板 / 契约
`turns that unknown type into a first-class supported signature via PR`；`schema_version must be bumped`。
### 2.3 输入产物
`domain-adaptive-pipeline.md` M1、`adaptive-degradation.md` M3、`domain-learner`、`signature-consumer`、`adaptation-contract`、`CONTRIBUTING.md`。

## 3. 输出
### 3.1 输出知识节点
`domain-signature-spec.Proposed evidence_type`；`adaptive-matrix-rows.M1/M3/mixed-domain`；`falsification-test.Test results/Regression check`；`learner-prompt.Recognition signals`；`schema_version 1.(x+1)`。
### 3.2 输出产物
PR1 `domain-signature-spec.md`；PR2 `adaptive-matrix-rows.md`；PR3 `falsification-test.md`（3+3 verdicts）；PR4 `domain-learner-prompt.md`。
### 3.3 传递片段
`classify evidence_type: <name> with confidence ≥ 0.7`；低于阈值回落最近已有类型。

## 4. 判定与门
3 条件全满足；任一已有领域回归 verdict 改变 → REJECTED；6 checks；14 天 review / 30 天 revise；case-by-case 不 bump；无真实 flag / 无 3+3 / 绕审 bump → REJECT。

## 5. 上下游
orchestrator / adaptive-pipeline / degradation → 本契约 → 社区 PR + core review。

## 6. 映射
`paperapp/registry.py::register_class → registry.json / PROMOTION_LOG.jsonl` 是本项目对应的类注册升级路径。
