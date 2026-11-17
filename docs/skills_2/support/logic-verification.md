# logic-verification · 6 维一致性 + 20 类问题 + 3 轮上限

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/logic-verification/SKILL.md`（303 行）
> 类型：support · Phase 8（MUST） · 判定：skill 内 + 6 态 verdict。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `8` |
| **输入节点（对齐）** | `Assumption`；`Evidence`；`Contribution` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `LogicIssue`(issue_class/severity/evidence_ref) 与 `DerivationStep`(expr/verified/tool)；现有节点无法逐步审计推导链 |

## 1. 解决的问题

### 1.1 核心问题
对推导包做 6 维一致性审计与 20 类问题分类，修复复审至收敛（最多 3 轮），产出证明审计 verdict。

### 1.2 具体场景 / 为什么需要
- `Correctness matters more than declaring success` —— 正确性优先于「完成」。
- 禁止带 FATAL / CRITICAL 开放问题静默通过；反例 pass 必做（没找到也要记候选）。
- 3 轮未收敛 → `NOT YET COHERENT` 升级。

### 1.3 不做的后果
- 关键引理错误未发现，整段推导结论作废。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `DerivationOutput` | 推导结果 | Phase 6a | 必须 |
| `Problem` | `Q-id` | 文档头 | 必须 |
| `Paper` | `main.tex + sections` | Phase 12 | 可选 |
| `SymPyOutput` | 机器验证结果 | Phase 6a | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `assurance-contract.md` | 6 态 |
| 原则 | `Correctness matters more than declaring success` | 正确性优先 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `derivations/{problem_id}/derivation_output.md` | 待审 |
| `paper/main.tex`、`paper/sections/*.tex` | 论文稿 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `LogicVerification` | `verdict / q_id / n_fatal / n_critical / n_major / n_minor / issues` |
| `LogicVerification` | `counterexample_pass / review_rounds / argument_status` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/ARGUMENT_SKELETON.md` | DAG / 假设账 / 微主张 | 骨架 |
| `.sciforge/audits/LOGIC_VERIFICATION.md` | 逐轮日志 | 审计 |
| `.sciforge/verdicts/LOGIC_VERIFICATION.json` | verdict | 机读 |
| `.sciforge/logs/LOGIC_CHECK_STATE.json` | 恢复态 | 断点续跑 |
| `UNRECOVERABLE_ARGUMENT.md` | 升级文档 | 3 轮未过 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（verdict 由下游门读） | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| PASS | skill 内 | 0 FATAL/CRITICAL/MAJOR + 假设 discharge + `counterexample_pass=executed` | `0` | — |
| WARN | skill 内 | 0 FATAL/CRITICAL + MAJOR caveat | — | 继续 |
| FAIL | skill 内 | open FATAL / CRITICAL | — | BA 回 Phase 2 |
| 轮次上限 | skill 内 | `MAX_REVIEW_ROUNDS` | `3` | `UNRECOVERABLE_ARGUMENT` |
| 前置缺失 | skill 内 | no derivation / no Q-id | → BLOCKED | — |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/theory-derivation` | Phase 8 `/logic-verification` | `/leakage-audit`、`/result-to-claim`、`/quality-gate`、`/paper-writing` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `LogicIssue(issue_class, severity)` | `paperapp` gate 产物 | 建议新增 `LogicIssue` |
| `counterexample_pass=executed` | `DK-P3-05` 反例必做 | 否 |
| 3 轮上限 | `RUN_BUDGET.retry_counters` | 否 |
