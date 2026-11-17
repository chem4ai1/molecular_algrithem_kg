# auto-pipeline · 单问题 26 节点 DAG 端到端编排器

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/orchestrator/auto-pipeline/SKILL.md`（575 行，v1.7.2）
> 类型：orchestrator · 代码佐证：`scripts/sciforge_audit.py`、`gap_gate.py`、`validate_verdicts.py`、`s2_audit.py`、`s2_ladder_gate.py`、`s2_ablation_gate.py`、`s2_integrity_gate.py`、`fairness_gate.py`、`completion_gate.py`、`claim_anchor_gate.py`、`kernel/sciforge/{rep,gates}.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段 0–5 编排 |
| **SciForge 26 节点** | `0`–`16` |
| **输入节点（对齐）** | 全部阶段输入；`ChoicePoint`/`HumanDecision`/`HumanIntent`(paperapp) |
| **输出节点（对齐）** | `GateVerdict`(paperapp)；`ReviewPoint`/`FailureCheck`(task)；`Lesson`(paperapp) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `RunState`(current_phase/next_action)、`RunBudget`(usage/limits/retry_counters)、`LoopBack`(kind∈in_phase/BA/pivot/supersede)；三者是运行态，不属于任何写作节点 |

## 1. 解决的问题

### 1.1 核心问题
把一个人给出的 Q-id 用一条 26 节点 DAG 编排成可投稿论文；**自身不做研究**，只负责路由 skill、读 verdict、卡硬门、触发有界回退。

### 1.2 具体场景 / 为什么需要
- 单 Q-id 全自动跑通 idea → 实验 → 审计 → 写作 → 编译 → 评审 → 引用 → 归档。
- 长程运行会漂移：`a phase loads ONLY its own SKILL.md + the references it declares; everything else is a path, never inlined prose`。
- `revision` / `deepen` 两种模式复用同一编排器与硬门。
- 回退必须有结构账本：3 轮上限、Loop-Back 登记表、全局预算账本。

### 1.3 不做的后果
- 各阶段靠 agent 记忆规则 → 长跑遗忘硬约束。
- 出现「FINAL REPORT 声称 21/21、PDF 已编译、score 92，但工作区无 PDF、章节空、11 个 verdict 缺失」的虚假完成。
- 三处 BA 各自 2 轮叠加成 6 轮空转；或预算花 40% 就宣布写完。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Problem` | `qid / text` | 用户 prompt | 必须 |
| `DomainSignature` | `confidence` | Phase 1b | 必须 |
| `VerificationRouting` | `route` | Phase 6 | 必须 |
| `RunBudget` | `limits` | 配置 | 必须 |
| `REP` | `fallbacks` | Phase 1 | 必须 |
| `InputManuscript` | `input / Review.comments` | 用户（revision/deepen） | 条件必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无 prompt 模板 | 消费 `methodology-and-context-contract.md`、`output-protocol.md`、`assurance-contract.md`、`citation-discipline.md`、`s2-protocol.md` | 上下文/产物/审计/引用/S2 契约 |
| bundle 指令 | `Execute phase {pid} per the skill contract`；`load only its declared references; produce the listed artifacts` | 阶段隔离 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/domain-signature.json` | 签名 |
| `VERIFICATION_ROUTING.json` | 路由 |
| `BUDGET_FLOOR.json` | 预算 |
| `EXPERIMENT_MATRIX.json` | 实验矩阵 |
| `.sciforge/RUNSTATE.json` | 恢复 |
| input_manuscript / review_comments | revision/deepen |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `REP` | `objectives / fallbacks` |
| `RunState` | `current_phase / next_action / status` |
| `RunBudget` | `usage / limits` |
| `PipelineVerdictSummary` | `verdicts` |
| `RunPreprint` | `idea / failures` |
| `Lessons` | `lessons` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/REP.json` | `objectives / fallbacks / budgets` | 计划 |
| `.sciforge/RUNSTATE.json` | `current_phase / next_action / budget_snapshot` | 恢复 |
| `.sciforge/verdicts/PIPELINE_VERDICT_SUMMARY.md` | `verdicts` | 汇总 |
| `.sciforge/verdicts/RUN_BUDGET.json` | `usage / limits` | 账本 |
| `output/RUN_PREPRINT.md` | gap / idea / kill / verdict / budget / failures | 归档 |
| `output/LESSONS.json` | `failed_experiments / what_worked` | 跨 run 回放 |
| `paper/main.pdf` | — | 论文 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `{verdict, artifacts, notes, cost_usd}` | orchestrator 自身与各边界 | 机器判定回执 |
| 逐字复述硬约束 | 每个 phase boundary | 防漂移 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| INV / method | `PROBLEM_HASH` hash match + `REGISTRY_HASH` + 人审 | Phase 0 / 5 | — | BLOCKED |
| gap_gate | `scripts/gap_gate.py` | gap-id + 引用 + 判别词 | lite≥1 / balanced≥2 / max≥3 / beast≥4 | 阻断 |
| toy | `RESULT.json status=PASS ∧ core_claim_validated=true` | ≥2 seeds 负 | — | PIVOT / KILL |
| full | `budget_floor=true` / S2 GOOD | engineer ≤2 | — | IN_PROGRESS / 补阶梯 |
| audit | 无 CRITICAL / ESCAPE / FATAL、零警告编译 | — | — | Phase5/6 或 BLOCKED |
| review | `last_score≥6`，`<8` → rebuttal | — | `SCIFORGE_REVIEW_THRESHOLD=8.0` | Phase6 |
| wrap | `validate_verdicts --strict --require-complete`，parity≥80% | — | `80%` | BLOCKED / 修复 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| 用户 Q-id / revision 输入 | `/auto-pipeline` | Phase 16 归档与 `paper/main.pdf` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| 26-DAG / `REP` / verdict / 机械门 | `paperapp/tbox.py::STAGE_IDS`（26 阶段）、`gates.py`（6 态 verdict） | 否，已实现 |
| `LoopBack` 四分类与预算 | `paperapp/replay.py` + `RUN_BUDGET` | 否 |
| 逐字约束再注入 | `hitl.reinject()` | 否 |
