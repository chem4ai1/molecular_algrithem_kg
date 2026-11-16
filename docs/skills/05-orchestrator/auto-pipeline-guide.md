# 指导 · `auto-pipeline` 编排器操作手册（26 节点 DAG v1.7.2）

> **依据**：`skills/orchestrator/auto-pipeline/SKILL.md`（575 行，v1.7.2）
> **用途**：指导你**如何启动一次完整 run、每个边界做什么、失败怎么回退、什么必须交给人**，而不是复述文档。
> **定位**：这是 OSS 的**唯一入口编排器**。它不执行研究，只做分发、读 verdict、套质量门、触发回退、重建状态。

---

## 1. 启动前：必须想清楚 6 件事

### 1.1 一次调用只处理一个 Q-id

```
/auto-pipeline "Q001: <problem description>" — effort: max
```

- Q-id **必须由人给出**。编排器**不会**去问题库里找下一个问题，也不会自动遍历所有问题。
- Q-id 在 Phase 0 冻结（**INV-G1**），之后每个下游产物都要引用它；Phase 9 `/invariant-check` 会做内容哈希校验，缺引用直接 BLOCK。

### 1.2 选 mode（三者共用同一条链，不产生第二条管线）

| mode | 输入 | 冻结什么 | 跳过什么 | 产物 |
|---|---|---|---|---|
| `full`（默认） | 一个研究问题 | Q-id | 无 | 从零生成完整论文 |
| `revision` | 已完稿 + 可选审稿意见 + 数据 | **原稿的 core idea / contributions**（INV-G1 锚定 thesis，不重新造 Q-id）、作者数据 | Phase 1–3 | `.sciforge/refine-logs/REVISION_PLAN.md`，**scoped revision**（只改被点名的章节/图，禁止全文重写） |
| `deepen` | 可用稿件 + 数据/代码 | **core claim + 贡献列表 + method identity**（提出不同方法即 `deepen_frozen_violation` → BLOCKED） | 不变创新 | `DEEPEN_PLAN` + `FAIRNESS.json`，只提升证据深度与实验公平性 |

> `deepen` 的关键约束：`/result-to-claim` 重新门控后，**claim 强度只能持平或下降，不能超过新证据**；只在单一配置下成立的边缘阳性必须移到 "regime-limited" 并写明 regime，**不得删除也不得夸大**。

### 1.3 参数与两条独立的轴

| 参数 | 取值 | 说明 |
|---|---|---|
| `effort` | `lite / balanced / max / beast` | 深度与成本（文献量、轮次、ideation） |
| `assurance` | `draft / submission` | 审计严格度；未给时由 effort 推导：`lite/balanced→draft`，`max/beast→submission`。**可独立覆盖**：`effort: balanced, assurance: submission` 合法 |
| `human_skip` | `true/false` | **生产级**显式委托两个人工检查点；`production_ready: true` |
| `test_mode` | `true/false` | 仅机械压力测试；`production_ready: false`，`human_review_deferred: true`，**事后必须人工确认** |
| `kill_checkpoint` | `false` 关闭 | 只关 KILL 检查点；默认 ON |
| `language` | 如 `chinese` | 输出语言 |

> `human_skip` ≠ `test_mode`：前者是人**已决定**授权、无需事后确认；后者是**暂缓**人工批准但仍完成了检查点所保护的工作，且不算生产就绪。两者都不能豁免其余硬门。

### 1.4 默认配置（写进 `AGENT_DOC.md`）

`verification_type` 默认 **experiment-first**；`test_mode` 只影响检查点；`language` 默认按用户；budget 默认值见 §6。

### 1.5 无学科分支

OSS **没有** economics / cs-ml / physics / general 四条并行管线，只有一条 universal 链 + `senior-reviewer-agnostic` 人格。领域方法论由 Phase 1 选 paradigm（`formal / empirical / interpretive / design`）**按问题性质而非领域标签**决定，由 `/theory-derivation` + `/dynamic-sandbox` 承载。**不要重新引入学科分叉或 AIM/SOTA/PNV 框架。**

### 1.6 启动第一步其实是「恢复」

若存在未完成的 `.sciforge/RUNSTATE.json`，**先跑恢复协议**：校验 verdict trail（`validate_verdicts.py`）→ 迁移旧路径产物 → 从 `next_action` 继续。长跑靠这个跨 session 存活。

---

## 2. 26 节点主链（照此顺序分发）

```
0 冻结 Q-id / RUN_BUDGET → 1 问题分解 + REP.json
→ 1a domain-signature(OPTIONAL hint) → 1b domain-learner(MUST, 唯一写入者)
→ 4broad universal-retrieval 广搜 + GAP_REPORT.md
→ 2 idea-discovery(4 视角 + MCTS)
→ 2.5 adversarial-falsification(MUST) → 2.5b Engineering Grounding
→ 3 novelty-check(DAG 收敛) ──[人工选定最终 idea]──
→ 4targeted 逐 survivor 定向检索
→ 5 method-registry(8 节 + §3 hash lock) ──[人工审批]──
→ 6 verification-routing → 6a / 6b / 6c
→ 7 leakage-audit ∥ 8 logic-verification → 9 invariant-check
→ 10 result-to-claim(3-fidelity + TDAL + ablation)
→ 11 unified-plotting ∥ 12 paper-writing(可并行)
→ 13 paper-compile → 14 auto-review-loop → 15 citation-audit
→ 15.5 publishability-score → 16 归档 + RUN_PREPRINT + LESSONS
```

**并行组**：A = 4broad 与 Phase 2 Round 1 的 raw pool 可并行，但 **gap 锚定 / novelty 预筛 / Round 2–4 打分必须等 `GAP_REPORT.md` 可读**；B = 11 ∥ 12；C = 7 ∥ 8。

**增量 MCTS**：R1 全评 8–12 root → R2 只重评 borderline(0.4–0.6) → R3 只评其 child → R4 终选。约省 40%。

**Early exit（仅这 4 个）**：Phase 2 六轴全 BLOCKED → 直接返回；Phase 10 所有 claim 达 symbolic fidelity → 跳过 Phase 14；Phase 12 明确无需图 → 跳过 Phase 11。**注意 Phase 2.5 证伪永远不能跳**；Phase 4 也 non-skippable（理论型也要查重，避免重证已知结论）。

---

## 3. 每个边界固定要做的 5 件事（照抄成 checklist）

1. **逐字复述硬约束**（不是摘要，是 verbatim）：verification route、budget_floor 五项检查、page-tier cap、`EXPERIMENT_MATRIX.json` 的 group 列表、剩余 PIVOT 预算、negative-result discipline、`RUN_BUDGET.json` 当前用量 vs 上限。写进 `.sciforge/logs/pipeline.log`。
2. **跑 verdict 校验**：`python3 scripts/validate_verdicts.py {problem_id}/.sciforge/verdicts/`（`--strict` 下违规 = BLOCKED）。
3. **漂移检测**：本阶段产物是否带它消费/产生的硬约束字段（如 `evidence_sufficiency`、`response_class`、page-count verdict）。缺字段 → 该阶段降 WARN(`constraint_field_missing`)；**同类字段连续 2 个阶段缺失 → BLOCKED**。
4. **拦截「我完成了」声明**：任何阶段报 PASS 时，检查其硬约束字段是否齐全且满足；不完整 → **不接受 PASS**，降为 `IN_PROGRESS` 并要求补齐。
5. **重写三个状态文件**：`.sciforge/RUNSTATE.json`（当前阶段 / 上一完成边界 / next_action / status / pending approvals / budget 快照）、`.sciforge/verdicts/PIPELINE_VERDICT_SUMMARY.md`（所有 verdict 聚合）、`RUN_BUDGET.json`（记账）。

> 另外：机械判定一律走 `scripts/sciforge_audit.py`（一次调用、硬退出码），**模型读机器 verdict，不重新推导规则**。

---

## 4. 阶段模式与质量门（最关键的行）

| Phase | 模式 | 门（不满足的去向） |
|---|---|---|
| 0 / 1 | MUST | Q-id 不明确 → **问人**；Phase 2+ 无 `REP.json` → `rep_plan_present` FAIL |
| 1a | OPTIONAL | 失败记 WARN 继续；只写 `domain-signature-hint.json` |
| 1b | MUST | `learning_confidence ≥ 0.7`；唯一写入 `domain-signature.json` |
| 4broad | MUST | `gap_gate`；3 层引用验证 + screening-chain（真实性+完整性）PASS；**理论型也不可跳** |
| 2 | MUST | ≥1 idea 且 MCTS 收敛；promoted idea 必须有 gap-id |
| 2.5 | MUST | 假设健康 ≥6 或无反例；WEAKENED→L1 回 Phase 2，FALSIFIED→淘汰记录 |
| 2.5b | MUST | EG 8 维报告；≥3 子维=0 → 淘汰 |
| 3 | MUST + **人工** | 复合分 ≥0.6、收敛到 1 survivor；**agent 不能自己选** |
| 4targeted | MUST | 每 survivor 一次；`TARGETED_WAVE_LOG.md` |
| 5 | MUST + **人工** | 8 节 registry + §3 hash lock + 实验矩阵；**agent 不能自己批** |
| 6 | MUST | `VERIFICATION_ROUTING.json`；experiment-first 默认 |
| 6b toy | ROUTED | `RESULT.json status=PASS ∧ core_claim_validated=true`；FAIL → **KILL-or-PIVOT**（需「显著负且 ≥2 seeds 可复现」） |
| 6c full | ROUTED | `DISPATCH.json` + 后台启动确认 + `budget_floor.satisfied` + `S2_LADDER.json` PASS；不满足 → `IN_PROGRESS`，**不得进 Phase 10** |
| 7 / 8 / 9 | MUST | Type I 无 CRITICAL / 无 ESCAPE；逻辑零 FATAL/CRITICAL；INV-G1 通过 |
| 10 | MUST | ≥1 主结果达 numerical fidelity + `ABLATION_LEDGER.json` PASS（5–6 plans、AblCritic、monotone current_best） |
| 11 / 12 / 13 | MUST | 每篇至少 1 图；elsarticle + leakage scrub；**零 error 零 warning** 编译 |
| 14 | MUST | 跨模型评分 ≥6；校准分 <8 → `REBUTTAL_PLAN.json` + 真实补充实验（≤2 轮，纯措辞 = `round_invalid`）；kill-argument 成立 → **BA 回 Phase 2** |
| 15 / 15.5 | MUST | 全部引用过 3 层；主实验逻辑轴 + fairness PASS |
| 16 | MUST | `validate_verdicts.py --strict --require-complete`；任一注册 verdict 仍 PENDING（且非 `na_verdicts`）→ `BLOCKED: verdicts_incomplete` |

**总 verdict** = 26 节点最差值：`ERROR > BLOCKED > FAIL > WARN > NOT_APPLICABLE > PASS`。

**MUST 失败** → 3 轮 fallback → BLOCKED 交人；**OPTIONAL 失败** → WARN 继续；**ROUTED** 由 `VERIFICATION_ROUTING.json` 决定，合法缺失写进 `na_verdicts`（**不要为了清 pending 伪造 verdict**）。

---

## 5. 回退：Loop-Back Registry L1–L13（唯一权威表）

| ID | 触发 | 目标 | 动作 | 预算 | 耗尽 |
|---|---|---|---|---|---|
| L1 | 2.5 WEAKENED | Phase 2 | 重生 idea | 3 轮 | BLOCKED |
| L2 | 2.5 FALSIFIED | — | 记 `failed_ideas.json` 继续下一个 | 每 idea 1 次 | 全灭→BLOCKED |
| L3 | 3 无 survivor | Phase 3 | 放宽 strictness 重评 | 1 轮 | BLOCKED |
| L4 | 5 hash 失配 | Phase 5 | 重建 registry | 3 轮 | BLOCKED |
| L5 | 6b toy FAIL | PIVOT→Phase 5 / KILL→Phase 2 | 重注册方法 / 写 kill argument 换 idea | PIVOT ≤2 | forced KILL |
| L6 | 6b TIMEOUT/ERROR | 6b | 缩放/修复重跑 | 各 1 | BLOCKED |
| L7 | 6c full FAIL 且 toy 曾 PASS | Phase 2 | BA idea 重生 | **BA 全局 ≤2** | `BA_EXHAUSTED` |
| L8 | 7 CRITICAL | Phase 5 | 方法打补丁 | 3 轮 | `LOGIC_GAP` |
| L9 | 8 FATAL/CRITICAL | Phase 6 | 修推导 | 3 轮 | FATAL（数据与结论矛盾）→ BA 回 Phase 2 |
| L10 | 14 score<6 | Phase 6 | 补证据 | 4 轮 | BLOCKED |
| L11 | 14 kill-argument 成立 | Phase 2 | BA idea 重生 | **BA 全局 ≤2** | `BA_EXHAUSTED` |
| L12 | 13 页数溢出 | Phase 12 | 删减重编译 | 直到达标 | 降长度档重排 |
| L13 | 连续 3 轮无实质回应 | Phase 2 | forced KILL | — | BLOCKED |

**六条硬纪律**：
1. 每个回退**必须带预算**，耗尽必须有非回退出口；禁止「再来一轮」。
2. 回退**必须改变状态**：重入的阶段必须消费上次失败证据（`failed_ideas.json` / `KILL_ARGUMENT.json` / `REVIEW_STATE.response_class`）。**原样重跑 = 禁止**。
3. 任何「换 idea」必须先产出 `.sciforge/verdicts/KILL_ARGUMENT.json`，否则 INV-G1 拦截。
4. **BA 预算全局共享**：L7/L9/L11 合计 ≤2 轮，不是各 2 轮（记在 `RUN_BUDGET.json` 的 `ba_rounds_used`）。
5. **Off-plan loopback = 契约违规**：Phase 1 的 `REP.json` 声明了每个阶段的 fallback 条件；kernel 检查 `rep.fallback_consumed`，未声明的回退记 `rep_fallback: FAIL`。
6. **KILL 有人检查点**（默认 ON）：`KILL_ARGUMENT.json` 产出后暂停，向人展示最强拒稿段 + `still_unresolved` + 哪条回退触发，确认后才回 Phase 2；仅 `human_skip=true` 或 `kill_checkpoint=false` 可关。记录写 `.sciforge/APPROVAL_LOG.txt`。

> 3 轮上限是**按失败类型**而非按阶段：一个阶段有 3 种不同失败，最多可 9 次修复，不是 3 次。

---

## 6. 预算：`RUN_BUDGET.json` 与两端护栏

```json
{"schema_version":"1.0","run_id":"Q042","started_at":"...",
 "wall_clock_seconds":0,"api_cost_usd":0.0,
 "pivot_count":0,"ba_rounds_used":0,"ba_rounds_max":2,"per_phase":{},
 "limits":{"wall_clock_seconds_max":172800,"api_cost_usd_max":40.0,"pivot_count_max":2}}
```

| effort | 墙钟上限 | API 费用上限 | PIVOT | BA |
|---|---:|---:|---:|---:|
| lite | 12 h | $10 | 2 | 2 |
| balanced | 48 h | $40 | 2 | 2 |
| max | 96 h | $120 | 2 | 2 |
| beast | 240 h | $400 | 2 | 2 |

**边界协议（按顺序）**：① 记账（墙钟由编排器按时钟算，**不是阶段自报**；`per_phase.<n>` 追加时长/费用/verdict）→ ② 检查任一超限 → `BLOCKED, reason_code: budget_exhausted_<resource>` 并给出 usage-vs-limit 表 → ③ 写一行 `pipeline.log`。**只有人能抬上限，编排器不得自行延长**；`api_cost_usd` 只能增，纠错用追加注释，不得下调重写。

**对称护栏 budget-underuse**（容易漏）：若 `api_cost_usd < 0.5×上限` 或 `wall_clock_seconds < 0.5×上限`，**且**仍有 pending/IN_PROGRESS verdict 或 `BUDGET_FLOOR.satisfied == false` → WARN `budget_underuse`，并且 `completion_justification` 必须逐条解释未尝试的路线，PASS 才被接受。**便宜可以，但「探索没做完就宣布完成」不行。**

---

## 7. 工作区目录（v6.0 两层分离）

```
{problem_id}/
├── README.md / PROBLEM.md / AGENT_DOC.md
├── .sciforge/                 ← 隐藏状态层（durable + resumable）
│   ├── RUNSTATE.json          ← 每边界重写
│   ├── MANIFEST.md / APPROVAL_LOG.txt / PIPELINE_STATUS.md
│   ├── verdicts/              ← 22 个注册 verdict（平铺、固定名）+ PIPELINE_VERDICT_SUMMARY.md
│   ├── logs/ refine-logs/ audits/ tmp/
├── literature/                ← references.bib / GAP_REPORT.md / TARGETED_WAVE_LOG.md
├── methods/                   ← METHOD_REGISTRY.md / METHOD_BINDING.md / OUTCOME_CLASSIFICATION.md
├── derivations/  src/  experiments/  logs/  figures/  paper/  output/
```

目录**按需惰性创建，不预建骨架**；合法缺失靠 `VERIFICATION_ROUTING.json` 的 `na_verdicts` 声明，收尾时保持 N/A，**不要补建空目录**。机器 verdict 进 `.sciforge/verdicts/`，叙述性报告进 `.sciforge/audits/`，科学交付物留在可见层。

Phase 16 必写 `output/RUN_PREPRINT.md`（一页摘要：问题 + gap-ids + 选定 idea + 触发的 kill arguments + verdict trail + 未探索 gap + 预算消耗 + 明确失败记录）与 `LESSONS.json`（failed_experiments / idea_rollbacks / code_errors / what_worked，各带 evidence + lesson）。二者供**后续 run** 的 Phase 2 与 6b 作为 prior（把 `avoid` 当硬排除），把独立 run 变成累积研究计划。缺失 preprint 只 WARN，永不 BLOCK。

---

## 8. HARD vs FLEXIBLE（别把硬的当可调）

| HARD（不可协商） | FLEXIBLE（agent 可裁量） |
|---|---|
| INV-G1 冻结；Phase 3→4、5→6 人工检查点；KILL 检查点（默认 ON）；3 轮 fallback 上限；toy FAIL = kill idea；full 实验后台 dispatch；RUN_BUDGET 上限；zero-warning 编译；leakage scrub | MCTS 轮数（默认 4，收敛清晰可减）；`scale_ratio`；toy 设计；strictness 阈值；effort |

**后台 dispatch 细节**：估算 toy 时长 `≤5min` 前台跑，`>5min` 派 `toy_bg`。toy verdict 在 **Phase 6c dispatch 边界**读；若 `toy_bg` 仍在跑，则**跳过 6c**（不发 full）继续 Phase 7+ 非实验工作，Phase 10 再复查。**绝不 busy-wait**。Phase 10 用已完成的 live job 结果并注明 "experiment pending"。

**theory-only 路径**：5 → 6a(`engine=manual`) → 6b/6c SKIP → 7(Type IV = NOT_APPLICABLE) → 8；Phase 10 以 qualitative fidelity 为正常；推导输出标 `[not machine-verified]` 并下调 claim 强度。

---

## 9. 上下文经济（长跑不漂移的 7 条）

1. **默认核心环**：`idea → experiment → audit → write → compile → review`；theory / heavy retrieval / rebuttal 仅在 signature/routing 要求时挂上。
2. **Pointer-load**：每阶段只加载自己的 SKILL.md 与声明的 references，其余**只给路径不内联正文**。
3. **Bundle-out**：≥10 行的指令写入 `refine-logs/<phase>.bundle.md`，下阶段拿路径。
4. **Compact-forward**：Phase 8 与 Phase 12 之前写 20–40 行决定性产物摘要，下游基于摘要工作。
5. **Sufficiency stopping**：(必填字段齐) ∧ (verdict 稳定 2 轮) ∧ (边际收益 ≤0) 才停；每个分析输出持久化 `stopping_rule.satisfied`。
6. **Evidence-forcing**：每个 finding 带 `raw_stat + confidence + method`；**数据特征 ≠ 错误**（不许为了好看清洗真实特征）；分析层只报告不判定。
7. **Deterministic-first + reviewer-only-raw-artifacts**：文件/字段/阈值/SHA-256 检查先于任何 LLM 判断；给 reviewer 传路径与原始产物，不传执行者的解释或引导性结论。

---

## 10. 三份检查清单

**启动前**
- [ ] Q-id 由人给出且唯一；`AGENT_DOC.md` 写明 discipline / venue / methodology_class
- [ ] mode、effort、assurance、三个跳过开关已明确选择
- [ ] 检查是否存在未完成 `RUNSTATE.json` → 先恢复
- [ ] `RUN_BUDGET.json` 已初始化

**每个边界**
- [ ] §3 的 5 件事全做（复述硬约束 / 校验 verdict / 漂移 / 拦截 PASS / 重写三文件）
- [ ] 机械门走 `sciforge_audit.py`，读 exit code 而非重新推理
- [ ] 若触发回退 → 查 L1–L13 是否登记、预算是否够、状态是否改变、KILL 是否有人确认

**收尾**
- [ ] `validate_verdicts.py --strict --require-complete` 通过
- [ ] `s2_completeness_audit`（gain arithmetic + split discipline + method↔code parity ≥80%）PASS
- [ ] budget-underuse 检查已处理（或 `completion_justification` 已解释）
- [ ] `RUN_PREPRINT.md` + `LESSONS.json` 已写
- [ ] 工作区卫生通过（无 stray log / `__pycache__` / 空目录）
- [ ] 所有人工检查点记录在 `APPROVAL_LOG.txt`

---

## 11. 与已有解析 / 框架的对应

| 本手册 | 关联文档 |
|---|---|
| 26 节点与门 | [APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) §3、§6、§7 |
| 6 态 verdict / 22 注册项 | [04-shared-references/schemas-guide.md](../04-shared-references/schemas-guide.md) |
| `domain-signature.json` 唯一写入者 | [01-domain-ideation/domain-learner.md](../01-domain-ideation/domain-learner.md) |
| gap chain / `GAP_REPORT.md` | [02-retrieval-tooling/universal-retrieval.md](../02-retrieval-tooling/universal-retrieval.md) |
| `RUNSTATE` / `RUN_BUDGET` / `LoopBack` 本体类 | 框架 §4.1 Governance |
| GGR 复现层 | `events.ndjson`=durable truth、`ClaimAnchor` 三哈希、dry 下诚实 BLOCKED 与此处 `na_verdicts` / `BLOCKED` 同构 |
