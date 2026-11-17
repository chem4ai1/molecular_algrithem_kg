# domain-adaptation-guide · 7 步接线与验收测试

> 源文件：`skills/shared-references/domain-adaptation-guide.md`（734 行） · 类型：shared-reference（执行指南）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 |
| **SciForge 26 节点** | `1b` |
| **输入节点（对齐）** | `Paper` |
| **输出节点（对齐）** | `DomainProfile`/`EvidenceNorm`/`FailureMode` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：7 步接线产物全部落在已有节点 |

## 1. 解决的问题
### 1.1 核心问题
用 7 步执行 + 18 项验收测试保证领域签名真正接到所有 skill。
### 1.2 为什么需要
`Domain adaptation is a wiring layer, not a discipline branch.`；`Skipping any step breaks domain adaptation.`
### 1.3 不做的后果
签名产出但下游不读，领域适配形同虚设。

## 2. 输入
### 2.1 输入知识节点
`evidence_type / primary_domain / verification_approach / writing_style / citation_format / failure_modes / data_availability`；`startup-log`。
### 2.2 输入 prompt 模板 / 契约
`Every skill reads refine-logs/domain-signature.json at startup...`；`The agent MUST follow these steps in order.`
### 2.3 输入产物
`domain-signature-consumer.md`、`domain-failure-modes.md`、`startup-protocol.md`、`domain-adaptation-contract.md`。

## 3. 输出
### 3.1 输出知识节点
domain-signature fields；startup-log entries；FANTASY verdict；Report.Results / Overall。
### 3.2 输出产物
`refine-logs/domain-signature.json`、`startup-log.md`、`fantasy-log.md`、Acceptance Test Report（ACCEPTED/REJECTED）。
### 3.3 传递片段
`WARNING: No domain signature found. Using default behavior.`；`Domain adaptation applied: idea-discovery → evidence_type=causal_inference → weights adjusted`。

## 4. 判定与门
Step0 4 prerequisites；7 步顺序；6/18 checks 全过；Joint confidence >0.5；FANTASY 或 MOSTLY_FANTASY + Phase12 → BLOCKED；ACCEPTED（全过）/ REJECTED（任一失败）。

## 5. 上下游
`/domain-learner` → 本指南 → `/idea-discovery`、`/adversarial-falsification`、`/paper-writing`、验收测试。

## 6. 映射
`applayer/miner.py::Paper.evidence_type → EvidenceNorm / FailureMode / SectionPlan` 是本项目对应接线点。
