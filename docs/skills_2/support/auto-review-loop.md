# auto-review-loop · Phase 14 角色切换 review → fix → re-review

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/auto-review-loop/SKILL.md`（626 行）
> 类型：support · Phase 14（MUST） · 判定：`scripts/verify_review_ledger.sh`（shell）、6 态 verdict。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 反驳预演 + 阶段5 自检 |
| **SciForge 26 节点** | `14` |
| **输入节点（对齐）** | `Contribution`；`SectionDraft`；`FailureMode`；`ReviewPoint` |
| **输出节点（对齐）** | `ReviewPoint`(task-w)；`FailureCheck`(task-r) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 `ReviewState`(round/last_score/model_ids) 与 `ReviewLedger`；`ReviewPoint` 是单条关注点，无法表达跨模型轮次 |

## 1. 解决的问题

### 1.1 核心问题
以固定角色序列做最多 4 轮 review → fix → re-review，合并保真门、盲区门与 S2 反驳门槛，产出可恢复的审查账本。

### 1.2 具体场景 / 为什么需要
- `Phase A → Phase B.1 → Phase B.2 → Phase C → Phase D in this exact sequence`。
- `effective_score = min(Phase A raw score, B.2 cap)` —— 单一 LLM 自评不可信，raw score≥6 也不得覆盖 fatal blind-spot。
- 跨模型 reviewer 避免同类领域失败被系统性漏掉。

### 1.3 不做的后果
- 自评虚高，投稿被拒；fatal blind-spot 被 raw score 掩盖。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `DerivationOutput` | 推导结果 | Phase 6a | 必须 |
| `Claim` | `CLAIMS_FROM_RESULTS.md` | Phase 10 | 必须 |
| `FinalProposal` | `primary_outcomes` | Phase 2 | 必须 |
| `DomainSignature` | `evidence_type` | Phase 1b | 可选（回退 derivational） |
| `ReviewState` | `round / status / timestamp` | 上一轮 | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Loop | `Phase A → Phase B.1 → Phase B.2 → Phase C → Phase D in this exact sequence` | 固定序列 |
| 计分 | `effective_score = min(Phase A raw score, B.2 cap)` | 盲区封顶 |
| 复审 | `Round N update… Now, as senior reviewer, re-read the updated artifacts and re-assess` | 角色切换 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `derivations/{problem_id}/` | 推导 |
| `CLAIMS_FROM_RESULTS.md` | 声明 |
| `FINAL_PROPOSAL.md` | primary outcomes |
| `domain-signature.json` / `domain-failure-modes.md` | 领域失败模式 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `ReviewState` | `round / last_score / last_verdict / status / response_class` |
| `BlindspotCheck` | `evidence_type / failure_modes_checked / unresolved_count / fatal_unresolved` |
| `ReviewLedger` | `verdict / details.rounds[]` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/AUTO_REVIEW.md` | rounds / Method Description | 日志 |
| `.sciforge/verdicts/REVIEW_STATE.json` | — | 状态 |
| `.sciforge/verdicts/BLINDSPOT_CHECK.json` | — | 盲区 |
| `.sciforge/verdicts/REVIEW_LEDGER.json` | — | 账本 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `experiment_redesign` 指令 | `/experiment-execution` | 补证据 |
| 分数与 verdict | `/citation-audit`、`/publishability-score` | 终门 |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| phase14 | skill 内 | `last_score ≥ 6` | `6` | L10 → Phase6 budget 4 |
| STOP | skill 内 | effective_score≥6 且 ready/almost | — | 结束 |
| 轮次 | skill 内 | max rounds | `4` | 超限 BLOCKED |
| fidelity | skill 内 | 默认 | `numerical` | — |
| 盲区封顶 | skill 内 | fatal cap=5 / severe cap=6 | `5 / 6` | 覆盖 raw score |
| rebuttal | 配置 | `SCIFORGE_REVIEW_THRESHOLD` | `8.0` | 触发 rebuttal |
| 账本校验 | `verify_review_ledger.sh` | `details.rounds[]` | — | 失败 FAIL |
| KILL | skill 内 | kill argument 成立 | — | L11 → Phase2 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/paper-compile` | Phase 14 `/auto-review-loop` | `/citation-audit`；`experiment_redesign` → `/experiment-execution` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `ReviewState / ReviewLedger` | `paperapp` 门产物 + `paperapp/gates.py` | 否 |
| fatal cap 覆盖 raw score | 主逻辑轴一票否决（DK-P4-18） | 否 |
| 4 轮上限 | `RUN_BUDGET.retry_counters` | 否 |
