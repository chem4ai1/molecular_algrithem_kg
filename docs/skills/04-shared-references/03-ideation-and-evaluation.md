# 指导 · 选题、搜索与评估协议（9 份）

> **覆盖源文件**：`idea-dag-schema.md`(241) · `mcts-search-protocol.md`(308) · `fantasy-prevention.md`(150) · `s2-protocol.md`(196) · `experience-replay-contract.md`(83) · `competitive-analysis.md`(178) · `competitive-drift-monitor.md`(254) · `engineering-grounding-contract.md`(233) · `background-dispatch-protocol.md`(192)
> **一句话**：这组文件把「想 idea → 打分 → 做实验 → 评审」从启发式变成**有状态机、有硬门、有跨 run 记忆**的可审计流程。

---

## 1. IDEA_DAG 的结构（`idea-dag-schema.md`）

**为什么是 DAG 不是树/图/超图**：idea 之间可以有多个前驱（组合），但不能有环；树丢组合，一般图丢顺序语义，超图过重。

| 契约 | 内容 |
|---|---|
| §2 JSON Schema | 节点与边的字段定义（与 `/idea-discovery` 的 `IDEA_DAG.json` 一致） |
| §3 Node States | 状态与合法转移（生成 → 打分 → promote / reject / borderline→child） |
| §4 Edge Types | depends_on 等边类型 |
| §5 **UCB Score Semantics** | 节点分数语义，与 MCTS 的选择公式对接 |
| §6 Data Fit Flags | 可选、领域感知的数据适配标记（6-axis 的 data-readiness） |
| §8 Artifact Registration | 产物登记位置（见 `artifact-registry.md`） |
| §9 Fallback | 图损坏/无节点时的降级 |
| §10 Version Compatibility | 版本兼容 |

**实操**：写 `IDEA_DAG.json` 时先校验无环，再让每个 promoted 节点带 `gap_anchor`；`failed_ideas.json` 与 DAG 的 eliminated 列表必须一致。

---

## 2. MCTS 协议（`mcts-search-protocol.md`）

| 节 | 要点 |
|---|---|
| §2 UCB Formula | 选择阶段的 UCB 公式（与 `idea-dag-schema.md` §5 对齐） |
| §3 Four-Phase MCTS Cycle | Expansion → Selection/Simulation → Backpropagation → Final（对应 `/idea-discovery` 的 R1–R4） |
| §4 Termination Conditions | 何时收敛（配合 orchestrator 的增量 MCTS：R2 只重评 borderline 0.4–0.6，省约 40%） |
| §5 Pseudo-Code | 实现参考 |
| §6 Crossover Partner Selection | 组合父节点怎么选 |
| §7 **Noise Handling (Anti-False-Trick)** | 防止 noisy reward 把「假技巧」推上去（与 `multi-fidelity-evaluation.md` §5 呼应） |
| §8 Parameters Summary | 参数表 |
| §9 Integration | 与现有 Pipeline 的接口 |

**指导**：改 MCTS 参数前先看 §8；任何「因为分数好看就 promote」的捷径都要过 §7 的 false-trick 检测。orchestrator 允许收敛清晰时减轮数（FLEXIBLE），但 **Phase 2 至少 1 个 idea、promoted 必须有 gap-id** 是硬的。

---

## 3. 五门防幻想（`fantasy-prevention.md`，由 `fantasy_gate.py` 机械执行）

| 门 | 检查 | FAIL 后果 |
|---|---|---|
| Gate 1–3 | 证据存在性 / 数据真实性 / **假设合理性**（`FINAL_PROPOSAL.json` 每个 assumption 需数值合理性分） | 计入 0–5 分 |
| **Gate 4** | **可证伪性**：`FALSIFICATION_RECORD.json` 必须存在且 ≥1 次反例尝试 | 缺则不满足 |
| Gate 5 | 反自欺 / 结论与证据一致 | 计入 |

```
5/4 门通过 → GROUNDED
3 门       → WEAKLY_GROUNDED（强制写 Limitations）
0–2 门     → FAIL，阻断 /paper-writing
```

> 该文件的 docstring 说得很直白：契约里称「最重要的质量门」，但此前**完全活在散文里**，没有东西阻止无根据的 claim 进入写作。因此**以 `scripts/fantasy_gate.py` 的机器判定为准**，散文只是解释。

配套 `Fantasy Log` 记录每次判定（文件里带一条 2026-07-21 的实例条目），便于复盘「哪次放行后来被证伪」。

---

## 4. S2 Protocol（`s2-protocol.md`，ScientistTwo parity layer v1.7.0）

> **Authority**：`kernel/sciforge/s2/` 的**代码赢过散文**；每条规则都有 kernel 模块 / 边界门 / bench 保证，没有一条是 advisory。
> 复现来源：*ScientistTwo* (arXiv:2609.19644)；86/107 真实会议问题、+25.2% over human SOTA。v1.7 把 4 个「只写在散文里」的机制变成代码。

### 4.1 四个机制与对应门

| 机制 | kernel 实现 | 产物 | 边界门 |
|---|---|---|---|
| subset→full **ladder** + 3 态 Critic `{BAD, ENGINEER≤2, GOOD}` | `s2/ladder.py` | `.sciforge/audits/S2_LADDER.json` | **6c 边界** `scripts/s2_ladder_gate.py` |
| **exploration-guaranteed** idea evolution | `s2/ideas.py` | loopback 事件带 `exploration_seed`、`KILL_DECISIONS.jsonl` | L1/L3/L11/L13 |
| 单调 **component ablation** + AblCritic | `s2/ablation.py` | `ABLATION_LEDGER.json` | **Phase 10 边界** `scripts/s2_ablation_gate.py` |
| score 驱动 **rebuttal + meta-review** | `s2/reviewloop.py` | `REBUTTAL_PLAN.json` / `REVIEW_STATE.meta_review` | Phase 14 |

### 4.2 Ladder 硬规则（照抄）

```
baseline reproduction (subset) → implement candidate → Critic:
  BAD      → discard（按 L5/L7 回退，永不 promote）
  ENGINEER → 再调，总轮数 ≤2
  GOOD     → 跑 FULL set
full-set 复验：candidate 必须 STRICTLY beat baseline（ties fail）
```

- 有实验证据但 `S2_LADDER.json` 缺失 → **FAIL**（跳过了阶梯）；
- `GOOD` 要求 `fullset.verified=true` 且方向感知的严格提升；
- `engineer_rounds ≤ 2`，耗尽是 BLOCKED，**不得静默 promote**；
- 声明的 `relative_gain_pct` 与重算值误差须 ≤ **0.15 pp**（算术不一致 = reward-hacking）；
- 完全无实验 → **SKIP**（theory-only 不受影响）。

### 4.3 Ablation 硬规则

- planner 出 **5–6 plans**（`SCIFORGE_ABLATION_MIN/MAX` 可覆盖做 micro-run），每个 `{id, component, hypothesis, metric}`；
- 每个已执行结果由 `ablcritic(prev,new)` 给 `GOOD`（严格更好）/ `REFINE`（保留旧态）；
- `current_best` 必须等于历史最佳 GOOD，回归或手改 ledger 直接 FAIL（单调性）；
- 有实验证据但无 `ABLATION_LEDGER.json` → **FAIL**（无消融不许 claim）。

### 4.4 两条阈值别混（Phase 14）

| 阈值 | 值 | 含义 |
|---|---:|---|
| boundary floor | **6.0** | `REVIEW_STATE.last_score ≥ 6` 才能跨过 Phase 14（L10 旧契约不变） |
| S2 rebuttal bar | **8.0**（`SCIFORGE_REVIEW_THRESHOLD`） | 低于它**必须**写 `REBUTTAL_PLAN.json`，每个 panel fatal / kill-argument 配一个补充任务 |

- rebuttal ≤2 轮（`MAX_REBUTTAL_ROUNDS`）；补充任务必须**真的执行并回填**，纯措辞 = `round_invalid`；
- `meta_review`：**ACCEPT** iff 校准分 ≥阈值 且零 fatal；否则 `PENDING_REBUTTAL` / `REFINE`（改方法 + 重跑消融 + 重进）。

### 4.5 校准与完整性审计

```
CALIBRATION.json: anchors[{id, panel_score, reference_score}] + OLS(a,b) + usable
calibrated = clamp(a + b·raw, 0, 10)
```
已知质量锚点（accepted-paper mean 6.2）；退化拟合 `b ≤ 0` → identity + `usable:false`，**绝不静默重标定**。

Phase 16 `s2_audit.py` 查三件事：① **gain arithmetic**（每个声明的 gain 从分量重算）② **split discipline**（有实验就必须声明 held-out/split/seed，偷偷换 split 是最廉价的 reward hack）③ **method↔code parity ≥80%**（方法节里 backticked / snake_case / camelCase 的机器 token 必须能在 `src/` + `experiments/` 找到；反向「代码里有但从没提」只报信息）。**SKIP 只在没有任何实验 claim 时合法**。

---

## 5. Engineering Grounding（`engineering-grounding-contract.md`）

立场是「**AI 视角，不是人类工程视角**」：8 个子维度衡量「这个 idea 对当前 AI 系统是否可落地」。

- §3 **EG Axis Tier Classification** → 与 `/idea-discovery` 六轴的 EG 分对接；
- §4 产出 `ENGINEERING_GROUNDING.md`（HEAVY / CONSTRAINED 全量，READY 简化）；
- §5 进入 `/novelty-check` 复合分（占 15%，`eg_average/10`，纯人文全 N/A 时 =1.0 不惩罚）；
- §6 喂给 2.5 证伪。

**硬门**：≥3 个子维 = 0 → BLOCKED/淘汰；1–2 个只生成 AI Mitigation Plan。

---

## 6. 经验回放（`experience-replay-contract.md`）

Phase 16 写 `LESSONS.json`，四类：`failed_experiments / idea_rollbacks / code_errors / what_worked`，每条带 evidence + lesson，镜像到 `output/LESSONS.json`。

- **消费者**：Phase 2 `/idea-discovery` 读兄弟 run 的 `LESSONS.json` 作为 prior（降权被 kill 的模式、从 `what_worked` 起种子）；Phase 6b 把 `avoid` 当**硬排除**；
- **串行，在既有 DAG 内**，不是并行系统；
- §5 的 retrieval-augmented lessons + policy update（v1.5.0，RL-grade）仍保持串行；
- 与 `RUN_PREPRINT.md`（auto-pipeline §Phase 16）配套，把独立 run 变成累积研究计划。

**红线**：失败是可复用的判断，**永远不是贡献**，也不得静默丢弃。阴性结果按 `result-to-claim` 的 negative-result discipline 处理。

---

## 7. 后台派发（`background-dispatch-protocol.md`）

| 节 | 指导 |
|---|---|
| §When to Background-Dispatch | 预估 >5 min 一律后台（与 orchestrator 一致）；full 实验**强制**后台 |
| §Dispatch Methods | 具体派发方式选一种，写 `DISPATCH.json` |
| §Status Polling Contract | 用 `STATUS.json` 轮询，**禁止 busy-wait**；toy_bg 未完则在 6c 边界跳过 full，Phase 10 复查 |
| §Checkpoint Schema | checkpoint 字段定义 |
| §Dataset / Model-Weight Download (v2.2) | **网络问题永不跳过**：下载也要派发 + 重试，不能因为连不上就当作数据不存在 |
| §Integration with Auto-Pipeline | 与 6b/6c/10 的时序 |

> 与 `universal-retrieval` 的代理自动挂载是同一条原则：**网络失败只能降 WARN + 后台重试，绝不 SKIP**。

---

## 8. 竞争力跟踪（两份，属于「维护」而非「运行时」）

| 文件 | 用途 |
|---|---|
| `competitive-analysis.md`(178) | 竞争格局分析 + Crush-tier 能力矩阵 + 优化方向。是**基线文档**，不在论文 run 中执行 |
| `competitive-drift-monitor.md`(254) | **季度自动**漂移检查：4 个 differentiators → 锁定 Transition Rubric → curated 竞品表 → machine-readable Report Schema → Update PR Contract → Scheduling → Fallback。产出 PR 而非直接改代码 |

指导：这两个文件用于**维护 SciForge 自身**，不要把它们当论文生成阶段的门。若要给「分子算法设计」做同类机制，照抄 `Drift Check Workflow` + `Transition Rubric` + `Report Schema` 三段即可。

---

## 9. 检查清单

**Phase 2 前**
- [ ] `IDEA_DAG.json` 无环、节点状态合法、每个 promoted 有 `gap_anchor`
- [ ] MCTS 参数取自 §8；false-trick 检测已跑

**Phase 6c 边界**
- [ ] `S2_LADDER.json` 存在，Critic 状态合法，`engineer_rounds ≤2`，full-set 严格优于（ties fail）
- [ ] `relative_gain_pct` 与重算值误差 ≤0.15 pp
- [ ] 长任务已后台派发，`DISPATCH.json` + `STATUS.json` 齐全

**Phase 10 边界**
- [ ] `ABLATION_LEDGER.json` 有 5–6 plans，`current_best` 单调
- [ ] `EG` 报告已出，0 值子维 <3

**Phase 14 / 16**
- [ ] 两条阈值 6.0 / 8.0 分开处理；rebuttal 有真实补充实验
- [ ] `CALIBRATION.json` 可用或明确 `usable:false`
- [ ] `s2_audit.py` 的 gain / split / parity 三项通过
- [ ] `LESSONS.json` + `RUN_PREPRINT.md` 已写并镜像到 `output/`

---

## 10. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) §4.2 的 `IdeaNode / IdeaDAG / MCTSRound / FailedIdea / BAEvent` 来自本组前两份；§4.3 的 `FalsificationRecord / ExperimentMatrix` 来自 fantasy / EG / S2；§4.1 的 `LoopBack` 预算来自 L1–L13 与 `ba_rounds_used`。
GGR 复现层的 `S2_LADDER.json`、ties fail、`debug_tries ≤20` 与这里同源 —— 见 [02-retrieval-tooling/dynamic-sandbox.md](../02-retrieval-tooling/dynamic-sandbox.md) 与 `capfactory/reprospec/ladder.py`。
