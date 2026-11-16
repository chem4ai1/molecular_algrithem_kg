# S3 · 26 阶段编排后半（阶段 6–16）、回退链与运行时隔离

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 把剩余 15 个阶段接通，形成完整 26 节点 run；补齐 L1–L13 回退、6 态门全覆盖、run 隔离与证据链 |
| 依赖 | S2（`phasegraph.json` 前 11 节点、`runner.py` 骨架、`gates.py`、`PaperSpec`） |
| 上游文档 | `../SCIFORGE_INTEGRATION_BLUEPRINT.md` §5/§9 P3；`docs/skills/05-orchestrator/auto-pipeline-guide.md` §4–§6 |
| 覆盖阶段 | `6 → 6a → 6b → 6c → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 15.5 → 16`（15 个） |
| 周期建议 | 7–9 个工作日 |
| 一句话验收 | 单次 run 走完 26 阶段；每个 gate 都有 6 态 verdict；`app_generation.json` 与语义层图**全程未被 runner 写入** |
| 硬门 | H7（+ H1/H2/H5/H6 不退化） |

---

## 1. 后端设计

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 修改 | `src/capfactory/paperapp/phasegraph.json` | 后 15 节点 `enabled=true` + `reads/produces/gate/next` + 并行组 |
| 修改 | `src/capfactory/paperapp/runner.py` | 完整分发、`LoopBack` L1–L13、预算护栏、崩溃恢复 |
| 新建 | `src/capfactory/paperapp/stages/__init__.py` | 15 个适配器注册 |
| 新建 | `.../stages/s06_routing.py` | `VerificationRoute` + `na_verdicts` |
| 新建 | `.../stages/s06a_theory.py` | 复用 `reprospec` 的静态检查 / `arb_verify` 思路 |
| 新建 | `.../stages/s06b_toy.py` | 复用 `reprospec.executor.execute_repro` + `smoke` |
| 新建 | `.../stages/s06c_full.py` | 复用 `reprospec.ladder.run_ladder` + `budget_floor` |
| 新建 | `.../stages/s07_s09_audits.py` | 泄漏 / 逻辑 / 不变量三类审计 verdict |
| 新建 | `.../stages/s10_claims.py` | `Claim` / `ClaimAnchor` / TDAL 四维 / 消融 |
| 新建 | `.../stages/s11_figures.py` | `FigureSpec` / `Figure` / `FigureBudget` + 复用 `reprospec.probe` |
| 新建 | `.../stages/s12_s13_write.py` | `PaperSection` / `Caption` / 编译报告 |
| 新建 | `.../stages/s14_review.py` | `ReviewRound` / `KillArgument` / 双阈值 6.0 与 8.0 |
| 新建 | `.../stages/s15_delivery.py` | `CitationAudit` / `PublishabilityScore` / `Lesson` |
| 新建 | `src/capfactory/paperapp/loopback.py` | L1–L13 表 + 预算 + 「必须改状态」校验 |
| 新建 | `src/capfactory/paperapp/budget.py` | `RUN_BUDGET.json` 记账 + budget-underuse 护栏 |
| 新建 | `src/capfactory/web/static/paperapp_run.html` | 完整 run 详情 + 门视图 |
| 新建 | `tests/test_paperapp_s3.py` | §6 的 20 项 |
| 修改 | `src/capfactory/web/paperapp_api.py` | `/runs/{id}`、`/stages/{id}/verdict`、`/loopbacks`、`/budget` |
| 修改 | `src/capfactory/paperapp/cli.py` | `run --effort`、`resume`、`verify-run`、`debug-stage` 全阶段 |
| 修改 | `src/capfactory/config.yaml` | `paperapp.budget:` / `paperapp.loopback:` 段 |

### 1.2 复用清单（**S3 不重写这些能力**）

| 已有实现 | 用在哪 |
|---|---|
| `reprospec.executor.execute_repro` / `check_script_safety` | 6b 隔离子进程执行、AST 白名单 |
| `reprospec.ladder.run_ladder` / `relative_gain` / `decide` | 6c subset→full 阶梯、ties fail |
| `reprospec.probe.shape_probe` / `lineage_enrich` | 11 的 `FigureSpec` 形状契约、15 的书目证据 |
| `reprospec.scoring.claim_anchors` / `perf_gap` / `align_rubric` / `finalize` | 10 的 claim 锚定与最终裁决 |
| `reprospec.verdict.evaluate_sau` / `sau_drift_acceptable` | 7/9 的逐 SAU 语义门 |
| `reprospec.application.materialize_runtime_nodes` | 运行时层节点（按 `run_id` 隔离） |
| `sciforge/contracts.py::VERDICT_STATES / verdict / validate_verdict` | 所有 gate |
| `sciforge/repro/state.py::EventLog / replay / save_state` | `events.ndjson` + `RUNSTATE` 派生 |
| `schema/capability.py::Lesson` | 16 的跨 run 回放 |
| `po/store.py::Concept/Assertion` 的 `attribution / evidence_ids` | 全部运行时节点 |

> **关键边界**：`runner` 与所有 stage 适配器**只写 run 目录与 `node_cache/`**；图写入统一留给 S4 `materialize()`。这是 S0 写入权限矩阵的延续。

### 1.3 后 15 阶段门定义

| 阶段 | 门 | 判据 | FAIL 去向 |
|---|---|---|---|
| 6 | `routing_decided` | `VERIFICATION_ROUTING.json` 含 `route/evidence_type/reason/na_verdicts` | 回 6 |
| 6a | `sympy_steps` | 逐步机器验证 PASS；theory-only 标 `[not machine-verified]` | 回 1（≤3 轮） |
| 6b | `toy_gate` | `RESULT.json status=PASS ∧ core_claim_validated=true`；`.SMOKE.json` 存在且 PASS | L5 KILL/PIVOT（≤2） |
| 6c | `full_gate` | `DISPATCH.json` + 后台确认 + `budget_floor.satisfied` + `S2_LADDER.json` PASS | `IN_PROGRESS`，不得进 10 |
| 7 | `type_i_iv` | Type I 无 CRITICAL、Type IV 无 ESCAPE | L8 → 5（≤3 轮） |
| 8 | `logic_zero_fatal` | 零 FATAL/CRITICAL | L9 → 6（≤3 轮）；FATAL → BA |
| 9 | `inv_g1_recheck` | Q-id 内容哈希 + 全部产物引用 Q-id | 回 0 |
| 10 | `claim_fidelity` | ≥1 主结果 numerical fidelity + `ABLATION_LEDGER.json` PASS + TDAL 已算 | 回 6 |
| 11 | `figure_budget` | Methods 架构图存在、body ≥7、类型 ≥3、A1–A11 无 FAIL | 回 11 |
| 12 | `leakage_scrub` | A–J 类零命中、caption 纪律 | 回 12 |
| 13 | `compile_clean` | 零 error 零 warning + `check_figure_embedding` PASS | L12 → 12 |
| 14 | `review_score` | boundary floor ≥6.0；校准 <8.0 触发 `REBUTTAL_PLAN` + 真实补充实验 | L10 → 6（≤4 轮） |
| 15 | `citation_audit` | 3 层验证 + DOI 标题 token-overlap ≥0.8 + 无 orphan | 删伪造引用 + 回 4broad |
| 15.5 | `publishability` | 主实验逻辑轴 + `FAIRNESS.json` PASS | 回 10 |
| 16 | `verdicts_complete` | `validate_verdicts` 风格：任一 PENDING 且非 `na_verdicts` → BLOCKED | 回缺 verdict 的阶段 |

**双阈值必须在代码里分开命名**：`BOUNDARY_FLOOR=6.0`、`S2_REBUTTAL_BAR=8.0`，禁止用一个 `threshold` 变量。

### 1.4 `loopback.py` L1–L13（摘要，完整表见上游指南）

| 字段 | 说明 |
|---|---|
| `id / trigger / target_stage / action / budget / exhaustion_exit` | 13 条固定登记 |
| **BA 全局预算** | L7/L9/L11 共享 `ba_rounds_used ≤ 2`，记在 `RUN_BUDGET.json` |
| **必须改状态** | 重入阶段必须消费 `failed_ideas.json` / `KILL_ARGUMENT.json` / `REVIEW_STATE.response_class`；原样重跑直接 `rep_fallback: FAIL` |
| **KILL 人工检查点** | 默认 ON；`KILL_ARGUMENT.json` + `APPROVAL_LOG.txt` 记录 |
| **Off-plan loopback** | Phase 1 的 `REP.json` 声明 fallback 条件；未声明的回退记 FAIL |

### 1.5 `budget.py`

```
每边界：① 记账（墙钟按时钟算，不是阶段自报）
      ② 超限 → BLOCKED + reason_code=budget_exhausted_<resource>
      ③ 写 pipeline.log 一行
budget-underuse 护栏：api_cost < 0.5×上限 或 wall_clock < 0.5×上限
                     且仍有 pending/IN_PROGRESS verdict
                     → WARN + completion_justification[] 必须解释未尝试路线
```

**hard invariant**：只有人能抬上限；`api_cost_usd` 只增不减。

### 1.6 运行时层与证据层

```
storage/sciforge/paperapp/<run_id>/
├── PAPER_SPEC.json / RUNSTATE.json / RUN_BUDGET.json
├── events.ndjson                 # durable truth，append-only
├── stages/<stage_id>/*.json      # 每阶段产物
├── app_paper_runtime.json        # 运行时节点（不进全量图）
├── verdicts/*.json               # 26 个 6 态 verdict
├── KILL_ARGUMENT.json / APPROVAL_LOG.txt
├── LESSONS.json / RUN_PREPRINT.md
└── FINAL_EVALUATION.json
```

`RUNSTATE` 由 `replay(events)` 派生，**禁止手改**。

---

## 2. 构建步骤（Step 1–14）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | `phasegraph.json` 后 15 节点启用 + 并行组（7∥8、11∥12） | `validate_phasegraph()` 返回 `[]`，26 节点全 enabled |
| 2 | `loopback.py` 13 条表 + 预算 + 状态改变校验 | 单测 T-S3-01..03 |
| 3 | `budget.py` 记账 + 两端护栏 | T-S3-04/05 |
| 4 | `runner.py` 分发器：按 `stage_order`、每边界写 events/RUNSTATE/verdict | 单跑 `--stage 6` 能重放 |
| 5 | 接 6 / 6a / 6b / 6c 四个适配器（复用 `reprospec`） | `toy_gate` / `full_gate` verdict 合法 |
| 6 | 接 7/8/9 审计适配器 | `validate_verdict()` 对每个 verdict 返回 `[]` |
| 7 | 接 10 claim 适配器（TDAL 四维由 `tdal_compute` 思路确定性计算） | `CLAIM_ANCHORS.json` 全 `resolved=true` |
| 8 | 接 11 图适配器（Figure Budget + shape 契约） | `figure_budget` 门判据明确 |
| 9 | 接 12/13 写作编译适配器 | `leakage_scrub` / `compile_clean` verdict |
| 10 | 接 14 评审适配器（双阈值 + kill-argument 检查点） | 6.0 与 8.0 分别触发不同动作 |
| 11 | 接 15/15.5/16 交付适配器 + `LESSONS.json` | `verdicts_complete` 无 PENDING |
| 12 | `runner` 全流程 `--effort balanced` 跑 1 篇（2411.06608） | 26 阶段各 1 verdict；`events.ndjson` 可 replay |
| 13 | `paperapp_api` 追加 4 个 API + `paperapp_run.html` | run 详情页展示 26 卡片与 verdict |
| 14 | `smoke.sh` 追加 4 项；全量回归 + H7 | 见 §7 |

---

## 3. 修正清单

| # | 坑 / 触发信号 | 修法 | 回归 |
|---:|---|---|---|
| C1 | 6.0 与 8.0 用一个变量 → 评审逻辑错 | 两个具名常量 + 分别测试 | T-S3-09 |
| C2 | BA 三个触发点各记 2 轮 → 实际 6 轮 | `ba_rounds_used` 全局共享，写 `RUN_BUDGET.json` | T-S3-02 |
| C3 | 回退「原样重跑」无限循环 | 强制消费失败证据 + `rep.fallback_consumed` 检查 | T-S3-03 |
| C4 | toy FAIL 被误当 BA（消耗全局预算） | toy FAIL = KILL idea（in-phase），不回 Phase 2 | T-S3-06 |
| C5 | `budget_floor.satisfied=false` 却写 `verdict: PASS` | 跨字段后检 + 单测 | T-S3-05 |
| C6 | full 实验在前台阻塞 26 阶段 | >5min 强制后台；`toy_bg` 未完则跳过 6c 继续 7+，Phase 10 复查 | T-S3-07 |
| C7 | runner 直接写 `app_generation.json` | 静态检查：run 前后图 sha 不变 | T-S3-08 |
| C8 | `NOT_APPLICABLE` 被静默 skip（无文件） | 必须写 verdict 文件；`audit-gates` 扫 | T-S3-10 |
| C9 | 26 个 verdict 里有 PENDING 就进 16 | `verdicts_complete` 硬门 + `na_verdicts` 白名单 | T-S3-11 |
| C10 | `RUNSTATE` 被手改后与 events 不一致 | 只允许 `replay()` 生成 | T-S3-12 |
| C11 | 图/写作阶段与 12 并行时抢同一文件 | 按 `stage_id` 分目录写，13 才汇总 | T-S3-13 |
| C12 | 复用 `reprospec` 时误改其默认行为 | 只调用，不修改；如须扩展用可选参数 | H11 |

---

## 4. 前端相应设计（完整 run 详情 + 门视图）

### 4.1 页面 `/paperapp/run?run_id=...`（`paperapp_run.html`）

| 区域 | 数据源 | 展示 |
|---|---|---|
| run 概览 | `/api/v10/paperapp/runs/{id}` | run_id / arxiv / effort / started_at / duration / 26 阶段进度条 / overall verdict |
| 26 卡片时间线 | `/api/v10/paperapp/runs/{id}/stages` | 复用 S2 时间线组件，扩到 26；并行组用虚线框标注 |
| 门 verdict 表 | `/api/v10/paperapp/stages/{id}/verdict` | 26 行：stage / state 徽章 / reason_code / artifacts / evidence_ids / ts |
| 回退链 | `/api/v10/paperapp/runs/{id}/loopbacks` | L-id / trigger / from→to / 预算剩余 / 状态改变证据 / 耗尽标记 |
| 预算 | `/api/v10/paperapp/runs/{id}/budget` | wall_clock / api_cost / pivot / BA 四条进度条 + 上限线 + `budget_underuse` 警告 |
| 事件流 | `/api/v10/paperapp/runs/{id}/events?limit=200` | 时间倒序事件表：`ts / stage / event / payload 摘要`；支持按 stage 过滤 |
| 产物树 | 同上 | run 目录文件列表 + 每文件存在性 + 大小 + 可下载 |

### 4.2 API 契约

| 路径 | 方法 | 200 | 错误/空态 |
|---|---|---|---|
| `/api/v10/paperapp/runs/{id}` | GET | `{run_id, arxiv, effort, status, overall, n_stages, n_completed, semantic_sha, app_sha}` | 404 `run_not_found` |
| `/api/v10/paperapp/runs/{id}/stages` | GET | `{stages:[26 项], parallel_groups:[[7,8],[11,12]]}` | — |
| `/api/v10/paperapp/runs/{id}/loopbacks` | GET | `{items:[...], ba_rounds_used, ba_rounds_max}` | 空 → `items:[]` |
| `/api/v10/paperapp/runs/{id}/budget` | GET | `{wall_clock_seconds, api_cost_usd, pivot_count, ba_rounds_used, limits, warnings[]}` | — |
| `/api/v10/paperapp/runs/{id}/events?limit=&stage=` | GET | `{items:[...], count, replay_ok}` | `limit>500` → 400 |
| `/api/v10/paperapp/stages/{id}/verdict` | GET | `{stage, state, reason_code, artifacts[], evidence_ids[], ts}` | 未跑 → 200 + `state:null` |
| `/api/v10/paperapp/run` | POST | `{run_id, stages_completed, verdicts}` | `effort` 非法 → 400 |

### 4.3 状态与交互

- 进度条按 26 阶段完成数；`BLOCKED/ERROR` 阶段红色脉冲标记并自动展开其抽屉；
- 门 verdict 表支持按 state 过滤（6 个 chip）；`NOT_APPLICABLE` 行必须显示对应文件路径，否则前端标「缺文件」警告；
- 「恢复运行」按钮 → `POST /run {resume: run_id}`，从 `RUNSTATE.next_action` 继续；
- 「重放事件」按钮 → 前端调 `/events?replay=1`，展示 `replay_ok` 与差异条数；
- 「重跑单阶段」→ 局部刷新该卡片 + 受影响的回退/预算面板；
- 事件流默认 200 条，滚动到底部再拉下一页（避免一次灌入全量事件）；
- 三态齐全；`fetch` 全用 `allSettled`。

### 4.4 与 S2 时间线的关系

S2 的 `paperapp_timeline.html` 保留为「阶段定义视图」（静态 26 阶段），S3 的 `paperapp_run.html` 是「某次 run 的实例视图」；S5 用 tab 把两者收进同一页，避免重复实现卡片渲染（抽出 `paperapp.js` 公共 `renderStageCard()`）。

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `VERIFICATION_ROUTING.json` | 6 | run 产物树 | `cli debug-stage --stage 6` | `routing_decided` | 有 `na_verdicts` | 合法缺失未声明 | 补声明并重验 |
| 2 | `RESULT.json` / `.SMOKE.json` | 6b | 6b 抽屉 | `cli debug-stage --stage 6b` | `smoke_passed` / `toy_gate` | `core_claim_validated=true` | smoke 时间晚于 STATUS | 重跑 smoke |
| 3 | `S2_LADDER.json` / `DISPATCH.json` | 6c | 6c 抽屉 + 预算面板 | `cli debug-stage --stage 6c` | `full_dispatched` | full-set 严格优于 | ties 被判赢 | C5/检查 ladder |
| 4 | `ABLATION_LEDGER.json` | 10 | 10 抽屉 | `cli debug-stage --stage 10` | `ablation_checked` | 5–6 plans、单调 | current_best 回退 | 回 10 |
| 5 | `TDAL.json` | 10 | 10 抽屉 | 同上 | `tdal_computed` | T/D/A/L 四维 + floors | 模型手写分数 | 强制脚本计算 |
| 6 | `CLAIM_ANCHORS.json` | 10 | 10 抽屉 | 同上 | `claim_anchored` | 全 resolved | 哈希漂移 | 重锚 |
| 7 | `figure_audit.json` / `FIGURE_BUDGET.json` | 11 | 11 抽屉 | `cli debug-stage --stage 11` | `figure_checked` | Methods 架构图存在 | body<7 | 回 11 |
| 8 | `LEAKAGE_SCRUB.json` | 12 | 12 抽屉 | `cli debug-stage --stage 12` | `scrub_checked` | A–J 零命中 | Class J 命中 | 回 12 删 AIGC 词 |
| 9 | `COMPILE_REPORT.json` | 13 | 13 抽屉 | `cli debug-stage --stage 13` | `compiled` | zero_warnings/errors=true | 有 warning | L12 |
| 10 | `REVIEW_STATE.json` / `KILL_ARGUMENT.json` | 14 | 14 抽屉 | `cli debug-stage --stage 14` | `review_round` / `kill_checked` | 6.0/8.0 分别处理 | 单变量 | C1 |
| 11 | `CITATION_AUDIT.json` | 15 | 15 抽屉 | `cli debug-stage --stage 15` | `citation_audited` | DOI 标题 overlap≥0.8 | 伪造引用 | 回 4broad |
| 12 | `PUBLISHABILITY_SCORE.json` | 15.5 | 15.5 抽屉 | 同上 | `publishability_scored` | 主逻辑轴 PASS | fairness FAIL | 回 10 |
| 13 | 26 个 verdict | 全程 | 门 verdict 表 | `cli audit-gates --run <id>` | `verdict_emitted` ×26 | 无 PENDING | 有 PENDING 非 N/A | C9 |
| 14 | `events.ndjson` | 每步 | 事件流 | `cli verify-run --run <id>` | 全部 | `replay_ok=true` | replay 不一致 | C10 |
| 15 | `RUNSTATE.json` | 每边界 | run 概览 | `cli status --run <id>` | `state_saved` | 由 replay 派生 | 手改痕迹 | 重建 |
| 16 | `RUN_BUDGET.json` | 每边界 | 预算面板 | `cli budget --run <id>` | `budget_accounted` | 只增不减 | 数值下降 | 查记账 |
| 17 | `loopbacks.json` | 回退时 | 回退链面板 | `cli loopbacks --run <id>` | `loopback_triggered` | 有状态改变证据 | 原样重跑 | C3 |
| 18 | `LESSONS.json` / `RUN_PREPRINT.md` | 16 | 产物树 | `cat .../LESSONS.json` | `run_finalized` | 4 类 lesson 齐全 | 缺失 | 回 16 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S3-01 | 单元 | L1–L13 表完整 | 13 条、每条有 `budget` 与 `exhaustion_exit` |
| T-S3-02 | 单元 | **BA 全局预算** | L7+L9+L11 合计 >2 时第 3 次被拒 |
| T-S3-03 | 单元 | 回退必须改状态 | 原样重跑 → `rep_fallback: FAIL` |
| T-S3-04 | 单元 | 预算超限 | `BLOCKED` + `reason_code=budget_exhausted_*` |
| T-S3-05 | 单元 | budget-underuse | 花 <50% 且有 pending → WARN + 需 `completion_justification` |
| T-S3-06 | 集成 | toy FAIL 不是 BA | KILL idea，`ba_rounds_used` 不变 |
| T-S3-07 | 集成 | 后台派发 | >5min 不阻塞；`toy_bg` 未完跳过 6c；**无 busy-wait** |
| T-S3-08 | 集成 | **runner 不写图 H7 支撑** | run 前后 `app_generation.json` 与语义层 sha 不变 |
| T-S3-09 | 单元 | 双阈值 | 5.9→L10；7.5→rebuttal；8.1→通过 |
| T-S3-10 | 单元 | `NOT_APPLICABLE` | 无文件 → `audit-gates` 报 `not_applicable_without_file` |
| T-S3-11 | 单元 | `verdicts_complete` | 有 PENDING 且不在 `na_verdicts` → BLOCKED |
| T-S3-12 | 集成 | events 重放 | `replay()==RUNSTATE`；手改 RUNSTATE 被检出 |
| T-S3-13 | 集成 | 并行组 7∥8、11∥12 | 无文件竞争，产物分目录 |
| T-S3-14 | 集成 | 26 阶段全流程（1 篇） | 26 verdict、状态合法、`overall != BLOCKED` |
| T-S3-15 | 单元 | 崩溃恢复 | events 截断到中间 → `resume` 从 `next_action` 继续 |
| T-S3-16 | 单元 | TDAL floors | 任一维 0 → 至多 WEAK；missing_inputs → STRONG 降 MODERATE |
| T-S3-17 | 单元 | `budget_floor` 跨字段 | `satisfied=false` 时写 PASS → 拒 |
| T-S3-18 | API | 7 个端点 | 200 + 空态；`limit>500` → 400 |
| T-S3-19 | 前端 | 26 卡片 + 门表 | 6 态色、并行组标注、事件分页 |
| T-S3-20 | 回归 | 全量 | 8+S0 12+S1 20+S2 18+S3 20 全过 |

**夹具**：`tests/fixtures/paperapp_s3/` 放 stub 执行结果、ladder、ablation、figure audit、review state 各 1 份；不跑真实 GPU / 编译。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s3 -v
PYTHONPATH=src python3 -m capfactory.paperapp.cli run --arxiv 2411.06608 --effort balanced
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-gates --run <run_id>
PYTHONPATH=src python3 -m capfactory.paperapp.cli verify-run --run <run_id>
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. 验收标准（签字表）

### 7.1 硬门

| 门 | 判据 | 实测值 |
|---|---|---|
| H7 门完整 | 26/26 阶段各有 6 态 verdict；`NOT_APPLICABLE` 全部有文件 | `______` |
| H1/H2/H5/H6 不退化 | 语义层 sha 不变、重建等价、隔离 0、spec 幂等 | `______` |
| runner 只读 | `app_generation.json` 与语义层 sha 全程不变 | `______` |
| H9/H11 | 注册无错；78 项累计全过 | `____/____` |

### 7.2 指标

| 指标 | 目标 |
|---|---|
| 单次 26 阶段 run（stub 执行） | < 180 s |
| `events.ndjson` 事件数 | 60–160 |
| `replay_ok` | true |
| `n_loopbacks` | ≤3（正常 run） |
| `stale/PENDING verdict` | 0（或全部在 `na_verdicts` 白名单） |

### 7.3 退出条件与人工签字

- 交付一次完整 run 的全部产物目录、26 verdict、20 项测试结果、run 详情页截图；
- **人工签字项**：确认 `BOUNDARY_FLOOR` 与 `S2_REBUTTAL_BAR` 是两个常量；确认 `ba_rounds_used` 全局共享；确认 KILL 有 `APPROVAL_LOG.txt`；确认 16 的 `LESSONS.json` 4 类齐全；
- 硬门不过 → 不得进入 S4。

---

## 8. 交付物与回滚

**交付**：15 个新文件 + 4 个修改文件 + `tests/test_paperapp_s3.py` + 夹具 + 一次完整 run 产物 + `docs/plan/S3_PIPELINE_BACK_REPORT.md`。

**回滚**：
1. `phasegraph.json` 后 15 节点回 `enabled=false`；`runner.py` 回到 S2 骨架；
2. run 产物**全部保留**（调试资产），归档索引写 `storage/sciforge/paperapp/INDEX.md`；
3. 新增的 `stages/` 适配器不删，标 `deprecated`；
4. 重跑 `bash scripts/smoke.sh` 回到 S2 的 18/18。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| 完整 `events.ndjson` / `RUNSTATE` | S4 回写依据、S5 事件面板、S6 崩溃恢复 |
| 26 个 verdict | S4 `materialize` 前置检查、S5 门表、S6 指标 |
| 阶段产物 `ResearchGap/IdeaNode/Claim/Figure/...` 提案 | S1 缓存 → S4 注册 → S5 图节点面板 |
| `LESSONS.json` | S4 跨 run 回放、S6 经验指标 |
| `loopback.py` / `budget.py` | S4 失效重算预算、S6 指标报告 |
| `paperapp_run.html` | S5 整合为「运行」tab |
