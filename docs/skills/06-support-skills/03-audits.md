# 指导 · 结构审计、逻辑验证与反自欺（4 个 support skill）

> **覆盖**：`leakage-audit`(343) · `logic-verification`(303) · `quality-gate`(344) · `kill-argument`(349)
> **DAG 位置**：Phase 7 / 8 / 12 前置 / 14；四个都是「宁可 BLOCK 也不放水」的承重门。

---

## 1. `leakage-audit` — Type I 逻辑缺口 + Type IV 经验逃逸（Phase 7）

| 项 | 内容 |
|---|---|
| 输入 | `METHOD_REGISTRY.md` + `METHOD_BINDING.md`（+ `DERIVATION_PLAN.md`、`AGENT_DOC.md`） |
| 输出 | `LEAKAGE_AUDIT.json` + `LEAKAGE_AUDIT.md`、必要时 `METHOD_BINDING_DIFF.md` |
| 关键 | **无学科 overlay**，Type I + Type IV 通用；CRITICAL → 回 `/method-registry`（L8，3 轮） |
| 门 | Type I 无 CRITICAL + Type IV 无 ESCAPE；3 轮仍失败 → `BLOCKED + LOGIC_GAP_FUNDAMENTAL_ISSUE` |

**两类要分清**：
- **Type I**：声明的方法与推导/实现之间的逻辑断层（假设没被用上、估计量与声明绑定不一致）；
- **Type IV**：验证结果与前提相矛盾却仍被当作支持（empirical escape）。

`LEAKAGE_AUDIT.schema.json` 要求 9 个字段：`verdict, discipline_context, type_i, type_ii, type_iii, type_iv, blockers…` 且**必须带 `audited_input_hashes`**（这是 `artifact-registry.md` invariant 2，SKILL.md 的 Step-6 示例曾漏掉，registry 优先）。

> 另一个同名但不同职责的脚本：`scripts/leakage_scan.py` 查的是**正文里的管线痕迹泄漏**（8+1 类正则，Class J = AIGC 痕迹词），写 `LEAKAGE_SCRUB.json`；它不是 `leakage-audit` 的实现。两者不要混。

---

## 2. `logic-verification` — 6 维 / 20 类问题分类（Phase 8）

| 项 | 内容 |
|---|---|
| 输入 | `derivations/{problem_id}/derivation_output.md` |
| 输出 | `LOGIC_VERIFICATION.md` + `LOGIC_VERIFICATION.json`、必要时 `ARGUMENT_SKELETON.md` / `LOGIC_CHECK_STATE.json` / `UNRECOVERABLE_ARGUMENT.md` |
| 关键 | **结构化证明检查（不是 cross-model）**；20 类 issue taxonomy；3 轮 cap；6 维一致性 |
| 门 | 零 FATAL / 零 CRITICAL；FATAL/CRITICAL → L9 回 Phase 6（3 轮）；**FATAL = 实验数据与推导结论矛盾 → BA 回 Phase 2（全局 ≤2 轮）** |

`LOGIC_VERIFICATION.schema.json` 必需 10 个字段：`verdict, q_id, n_fatal, n_critical, n_major, n_minor, issues…`，verdict 用完整 6 态（`NOT_APPLICABLE` 保留但 OSS 对推导恒跑），另有 `counterexample_passed` 枚举。

**与 `PROOF_AUDIT.json` 的分工**：`theory-derivation` / `logic-verification` 写证明审计（`PROOF_AUDIT.json` 是 audit family，必带 `audited_input_hashes`）；`LOGIC_VERIFICATION.json` 是 6 维 / 20 类的结构化问题清单。两者都被 `verify_paper_audits.sh` 检查。

---

## 3. `quality-gate` — 写作前最后一道硬门（Phase 12 边界）

| 项 | 内容 |
|---|---|
| Purpose | stagnation check + quality floor + anti-self-deception |
| 输入 | 全部研究产物（`derivations/` + `.sciforge/audits/` + `CLAIMS_FROM_RESULTS.md`） |
| 输出 | `QUALITY_FLOOR_REPORT.md` + `SELF_DECEPTION_REPORT.md` (+ `STAGNATION_REPORT.md`) + `QUALITY_GATE.json` |
| 关键 | **FAIL 阻断 `/paper-writing`**；确定性检查（Type D）+ 语义检查（Type S） |
| schema | `QUALITY_GATE.schema.json` required 3：`verdict, overall, generated_at`；另有 `stagnation` / `quality_floor` / `self_deception` 枚举 |

**三个检查各自的失败含义**：
- `stagnation`：连续多轮无实质进展（对应 L13 anti-shrinkage，3 轮无实质回应 → forced KILL）；
- `quality_floor`：核心证据未达最低置信（TDAL / fidelity）；
- `self_deception`：结论超出证据、把定性结果写成数值结论、把失败包装成发现。

**指导**：这是「论文写没写出来」之前最后的结构性拦截。若 `assurance: submission`，本门必须产出 6 态 verdict，静默 skip 禁止。

---

## 4. `kill-argument` — 单 agent 攻防自审（Phase 14）

| 项 | 内容 |
|---|---|
| Purpose | 找出「审稿人用来拒稿的**最强单一论点**」 |
| 输入 | `derivations/{problem_id}/` + `CLAIMS_FROM_RESULTS.md` |
| 输出 | `KILL_ARGUMENT.md` + `KILL_ARGUMENT.json` |
| 关键 | 两步自审（attacker → adjudicator 角色切换）；**200 词攻击备忘录**；3–7 个分解攻击点；`still_unresolved` 列表 |
| schema | `KILL_ARGUMENT.schema.json` 10 个 required，含 `audit_skill=kill-argument`、6 态 verdict、`audited_input_hashes`、`trace_path` |

**两条最重要的规矩**：

1. **KILL 必须先有 kill argument**：任何「换 idea」决策（L5/L7/L9/L11/L13）都要先产出 `.sciforge/verdicts/KILL_ARGUMENT.json`，否则 INV-G1 内容哈希会拦截 —— 没写 kill argument 的换 idea 是 drift，不是止损。
2. **KILL 有人工检查点（默认 ON）**：kill case 产出后编排器**暂停**，向人展示最强拒稿段 + `still_unresolved` + 触发的回退行，确认后才回 Phase 2。仅 `human_skip=true` 或 `kill_checkpoint=false` 可关；确认记录写 `.sciforge/APPROVAL_LOG.txt`。缺该记录，下一边界必须 BLOCK。

若 kill argument **成立**（claim 被自己的实验驳倒）→ L11 BA 回 Phase 2（**BA 预算全局 ≤2 轮**，与 L7/L9 共享）。

---

## 5. 四者的门与回退对照

| Skill | Phase | 门 | 失败去向 |
|---|---|---|---|
| `leakage-audit` | 7 | Type I 无 CRITICAL、Type IV 无 ESCAPE | L8 → Phase 5（3 轮）→ `LOGIC_GAP_FUNDAMENTAL_ISSUE` |
| `logic-verification` | 8 | 零 FATAL/CRITICAL | L9 → Phase 6（3 轮）；FATAL → BA → Phase 2 |
| `quality-gate` | 12 边界 | stagnation / floor / self-deception 全过 | 阻断 paper-writing，回补证据 |
| `kill-argument` | 14 | anti-self-deception PASS、kill 不成立 | 成立 → L11 BA → Phase 2；anti-self-deception FAIL → 回 Phase 10 |

**常见混淆**：
- `leakage-audit`（方法逻辑）vs `leakage_scan.py`（正文管线痕迹）——不同层；
- `PROOF_AUDIT.json`（证明审计族）vs `LOGIC_VERIFICATION.json`（20 类问题清单）——不同产物；
- `kill-argument` 是**反自欺**，不是 `rebuttal`（对外部审稿意见的回复）；
- BA（idea 本身错了，回 Phase 2，≤2 轮）vs in-phase fallback（执行出错，回相邻阶段，3 轮）。

---

## 6. 对应脚本

| 脚本 | 对应 |
|---|---|
| `scripts/leakage_scan.py` | 正文 A–J 类管线痕迹与 AIGC 词，写 `LEAKAGE_SCRUB.json` |
| `scripts/fantasy_gate.py` | 5 门防幻想，Gate4 要求 `FALSIFICATION_RECORD.json` ≥1 次反例尝试 |
| `scripts/validate_verdicts.py` | 上述 4 个 verdict 的 schema + audit-family 6 态 + `audited_input_hashes` |
| `scripts/sciforge_audit.py` | 汇总所有门为一个硬退出码 |
| `scripts/verifiers/verify_paper_audits.sh` | submission 模式下检查 `PROOF_AUDIT` / `CITATION_AUDIT` / `KILL_ARGUMENT` 等 |
| `scripts/claim_anchor_gate.py` | claim ↔ 节点哈希漂移复核 |

---

## 7. 检查清单

- [ ] 四个 verdict 都用 6 态词汇，且 audit-family 的带 `audited_input_hashes`
- [ ] `LEAKAGE_AUDIT.json` 的 `type_i..type_iv` 与 `blockers` 齐全
- [ ] `LOGIC_VERIFICATION.json` 有 `q_id` 与 `n_fatal/n_critical/n_major/n_minor` 计数，`issues[]` 带类别
- [ ] `QUALITY_GATE.json` 的 `overall` 与 `verdict` 一致，FAIL 时确实没进 paper-writing
- [ ] 任何换 idea 都先有 `KILL_ARGUMENT.json` + `APPROVAL_LOG.txt` 记录
- [ ] BA 计数写在 `RUN_BUDGET.json` 的 `ba_rounds_used`，三处触发共享 ≤2
- [ ] `leakage_scan.py` 的 Class A–J 在 Phase 13 边界通过（`LEAKAGE_SCRUB.json`）

---

## 8. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中 `Assumption / DerivationStep / FalsificationRecord / Claim / Verdict / LoopBack` 类由本组四者提供主要字段；§11 反模式「回退无预算、KILL 无 `KILL_ARGUMENT.json`」正是这里的硬纪律。
GGR 复现层的 `fantasy_gate` 式「可证伪性机器门」、`sau_drift_acceptable` 语义门、以及 dry 下诚实 `BLOCKED`，与本组是同一套防作弊哲学。
