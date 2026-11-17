# verification-routing · 验证模式路由（experiment / theory / hybrid）

> 源文件：`skills/shared-references/verification-routing.md`（305 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 + 阶段1 |
| **SciForge 26 节点** | `6` |
| **输入节点（对齐）** | `IdeaNode`；`DomainProfile` |
| **输出节点（对齐）** | `VerificationRoute` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 global 节点 `VerificationRoute`(verification_type/na_verdicts)：现有节点无法表达「哪些门不适用及理由」，Phase16 需据此判 verdicts_incomplete |

## 1. 解决的问题
### 1.1 核心问题
定义 `verification_type` 的确定方式，并把模式传给 paper-modes、理论/实验门和结果保真度。
### 1.2 为什么需要
路线决定哪些门适用；`na_verdicts` 必须显式列出不适用的门与理由，否则 Phase16 verdicts_incomplete。
### 1.3 不做的后果
理论论文被逼跑不存在的实验；实验论文漏掉推导审计。

## 2. 输入
### 2.1 输入知识节点
`Idea.mechanism / falsifiable_claim`；`DomainSignature.evidence_type / reasoning_paradigm`；`verification_type`；`na_verdicts[]`。
### 2.2 输入 prompt 模板 / 契约
`— verification_type: theoretical-computational`；`— verification_type: derivation-with-numerical-check`。
### 2.3 输入产物
`paper-modes.md`、`domain-adaptation-contract.md`、`auto-review-loop/SKILL.md`、`quality-gate/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`verification_type` ∈ pure_theory / derivational / empirical / computational / survey；`VERIFICATION_ROUTING.json`；`na_verdicts[]`。
### 3.2 输出产物
`.sciforge/verdicts/VERIFICATION_ROUTING.json`：`verification_type / reason / domains / falsifiability`。
### 3.3 传递片段
无。

## 4. 判定与门
模式必须可追溯到 idea 与 signature；不适用门须有 `NOT_APPLICABLE` verdict + 理由；缺失 → Phase16 BLOCKED。

## 5. 上下游
`/idea-discovery` + `/domain-learner` → 本契约 → `/paper-modes`、Phase6a/6b、Phase8/9/10、Phase16。

## 6. 映射
`VerificationRoute` 落 `paperapp` 应用层；`human` 可经 `ChoicePoint("6")` 选择 experiment-first / theory-only / hybrid。
