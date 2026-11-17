# kill-argument · 约 200 词最强拒稿论证与逐点裁决

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/kill-argument/SKILL.md`（350 行）
> 类型：support · Phase 14 · 代码佐证：`scripts/validate_verdicts.py`（PASS 须 `still_unresolved=0`）。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 反驳预演 |
| **SciForge 26 节点** | `14` |
| **输入节点（对齐）** | `Contribution`；`ReviewPoint`；`SectionDraft` |
| **输出节点（对齐）** | `ReviewPoint`(task-w, severity=fatal) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-w 节点 `KillArgument`(attack/decomposed_points/still_unresolved)：`ReviewPoint` 是分散关注点，缺「最强拒稿论证」这一整体对象 |

## 1. 解决的问题

### 1.1 核心问题
写一段约 200 词、最多 250 词的**单一最强拒稿论证**，拆成 3–7 点逐条裁决，暴露承重型未解问题。

### 1.2 具体场景 / 为什么需要
- 平衡弱点表会漏掉最致命的拒稿段落；强制承诺、不淡化。
- `construct the single best argument to reject this research in approximately 200 words`。
- 成立时必须回 Phase 2 换题（BA），默认需要人工确认。

### 1.3 不做的后果
- 自欺式通过审查；承重型问题被一句「limitation」带过。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `DerivationOutput` | 推导结果 | Phase 6a | 必须（或 CLAIMS_FROM_RESULTS） |
| `Claim` | `CLAIMS_FROM_RESULTS.md` | Phase 10 | 必须 |
| `Derivation / VerificationReport / PaperDraft` | 辅助材料 | 可选 | 可选 |
| `PriorReviews` | — | **禁止使用** | 禁用 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `assurance-contract.md` | 6 态 verdict |
| 攻击指令 | `construct the single best argument to reject this research in approximately 200 words` | 强制对抗 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `derivations/{problem_id}/{derivation_output.md, verification_report.md}` | 理论 / 数值 |
| `CLAIMS_FROM_RESULTS.md` | 主张 |
| `src/derivations/{problem_id}/derivation.py` | 证明 |
| paper draft | 上下文 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `KillArgument` | `verdict / reason_code / audited_input_hashes` |
| `KillDetail` | `decomposed_points[] / counts / net_assessment / top_action_items` |
| `AttackMemo` | 逐字攻击文本 |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `paper/KILL_ARGUMENT.md` | attack / adjudication | 人读 |
| `.sciforge/verdicts/KILL_ARGUMENT.json` | verdict / counts | 机读 |
| `.sciforge/traces/kill-argument/<date>_runNN/` | 双 trace | 可追溯 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| verbatim attack memo + per-point adjudication | 人工确认 / `/auto-review-loop` | KILL 决策依据 |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 词数 | skill 内 | ~200 / ≤250 | `250` | 超限重写 |
| 点数 | skill 内 | 3–7 点 | `3–7` | — |
| `unresolved_critical` | skill 内 | >0 | → FAIL | BA 回 Phase 2 |
| major / minor / 部分 critical | skill 内 | — | → WARN | 修复 |
| 0 unresolved | skill 内 | — | → PASS | — |
| 不适用 | skill 内 | not_theory_or_scope_paper | → NOT_APPLICABLE | — |
| 前置缺失 | skill 内 | paper_compile_failed / source_files_missing | → BLOCKED | — |
| PASS 校验 | `validate_verdicts.py` | `still_unresolved=0` | — | FAIL |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| stable review 或 KILL loopback | `/kill-argument` | 人工确认（除 `human_skip=true` / `kill_checkpoint=false`）→ Phase 2 换题 或 `/auto-review-loop` 修复 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `KillArgument` | `paperapp` `ChoicePoint("14")`（gate） | 否 |
| `still_unresolved=0` 才可 PASS | `DK-P4-12` 判据 | 否 |
| 人工确认 | `HumanDecision` + `APPROVAL_LOG.txt` | 否 |
