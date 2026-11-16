# 指导 · Claim 门控、自审循环、反驳与可发表性（4 个 support skill）

> **覆盖**：`result-to-claim`(429) · `auto-review-loop`(625，第二长) · `rebuttal`(164) · `publishability-score`(180)
> **DAG 位置**：Phase 10 → 14 → 15.5；这条链决定「结果能说成什么」以及「稿子够不够投」。

---

## 1. `result-to-claim` — 3-fidelity claim 门（Phase 10）

| 项 | 内容 |
|---|---|
| 输入 | `derivations/{problem_id}/`、`.sciforge/verdicts/LOGIC_VERIFICATION.json`、`RESULT.json`、`ENGINEERING_GROUNDING.md`、`IDEA_CANDIDATES.md`、`AGENT_DOC.md` |
| 输出 | **`CLAIMS_FROM_RESULTS.md`**（含 confidence assessment）、`CLAIM_ANCHORS.json`、`TDAL.json`、`ABLATION_LEDGER.json` 联动 |
| 关键 | **3 档 fidelity**：`symbolic / numerical / qualitative`；**theoretical confidence 与 grounding confidence 分别给出**；primary outcome 需 ≥ numerical fidelity |
| 门 | ≥1 个主结果达 numerical fidelity + `s2_ablation` PASS；qualitative-only → 改写为 conjecture；numerical 缺失 → 回 Phase 6 |

**三条不可协商**：
1. **claim 强度 ≤ 证据强度**（`paper-voice-contract.md` §1 CRITICAL EVALUATION RULE 的上游实现）；
2. **阴性结果按 negative-result discipline 处理**：进 Limitations / regime-limited 报告，**不删除也不夸大**；
3. **TDAL 由 `scripts/tdal_compute.py` 从机器产物计算**（T×D×A×L + floors），不是模型手写分数。详见 [04-shared-references/02-domain-and-confidence.md](../04-shared-references/02-domain-and-confidence.md) §3。

`CLAIMS_FROM_RESULTS.md` 还带逐 claim 的显著性门 `yes/partial/no` 与 **Claims-Evidence Matrix** —— `senior-econ-editor` persona 的 File-Read Order 第 3 项就是它，与正文不一致即拒稿（见 [reviewer-prompts-guide.md](../04-shared-references/reviewer-prompts-guide.md) §3.3）。

`claim_anchor_gate.py` 复核：每个进入正文的 claim 必须在 `CLAIM_ANCHORS.json` 里 `resolved=true`，锚定的 `NODES.json` 节点存在，且 **node outputs 哈希未漂移**（结果被改过就使 claim 失效）。

---

## 2. `auto-review-loop` — 单 agent 角色轮换自审（Phase 14，MUST）

| 项 | 内容 |
|---|---|
| 输入 | `derivation_output.md` + `CLAIMS_FROM_RESULTS.md` + 全稿 |
| 输出 | `AUTO_REVIEW.md` + `REVIEW_STATE.json` + `REVIEW_LEDGER.json` + `BLINDSPOT_CHECK.json` + `REVIEWER_MEMORY.md` + `REBUTTAL_PLAN.json` + 更新后的产物 |
| 关键 | **role switching：researcher → reviewer → defender → adjudicator**（`reviewer-routing.md` 的三轮版）；**round cap 3**；fidelity gate；v3.2 **domain-expert blind-spot pass** |

### 2.1 两条阈值（务必分开）

| 阈值 | 值 | 含义 |
|---|---:|---|
| boundary floor | **6.0** | `REVIEW_STATE.last_score ≥ 6` 才能跨 Phase 14；<6 → L10 回 Phase 6 补证据（≤4 轮） |
| S2 rebuttal bar | **8.0**（`SCIFORGE_REVIEW_THRESHOLD`） | 校准分 <8 → 必写 `REBUTTAL_PLAN.json`，每个 panel fatal / kill-argument 配一个**真实补充实验**；≤2 轮；纯措辞 = `round_invalid` |

### 2.2 三个容易写错的产物契约

| 产物 | 契约 |
|---|---|
| `REVIEW_LEDGER.json` | **单一 JSON 对象**，round 历史在 `details.rounds[]`，**不是 JSONL 流**；round 级 verdict 用 `ready/almost/not_ready`，envelope 用 6 态；`phase:"finalized"` 终止条目不带 `action_items`。由 `scripts/verifiers/verify_review_ledger.sh` 强制 |
| `BLINDSPOT_CHECK.json` | 固定名文件**每轮覆写**（每轮一个，历史在 `AUTO_REVIEW.md`）；5 个 required：`round, evidence_type, failure_modes_checked, unresolved_count, fatal_unresolved` |
| `REVIEW_STATE.json` | 9 个 required；`status ∈ {in_progress, completed}`；`not_ready` 与 `not ready` 两种拼写都接受但**写 `not_ready`** |

### 2.3 reviewer independence

`reviewer-independence.md`：**reviewer-only-raw-artifacts** —— 只给路径与原始产物，不给执行者的解释/引导性结论。配合 `review-tracing.md` 留痕。persona 用 canonical 路径 pointer-load（`reviewer-prompts/`），**不得 inline 第二份**。

### 2.4 与 kill-argument 的联动

Phase 14 还挂 `/kill-argument`：若最强拒稿论点**成立** → L11 BA 回 Phase 2（全局 ≤2 轮）。`anti-self-deception` FAIL → 回 Phase 10 重新门控 claim。两条都不要当成普通的「再评一轮」。

---

## 3. `rebuttal` — 逐点回复信（Phase 14 之后 / 收到拒稿时）

| 项 | 内容 |
|---|---|
| 输入 | `AUTO_REVIEW.md` + `REVIEW_STATE.json` + `REVIEW_LEDGER.json` + `main.tex`（+ 可选外部审稿意见） |
| 输出 | `paper/REBUTTAL_LETTER.md`（**双写**：时间戳副本 + 固定名副本）+ MANIFEST 条目 |
| 结构 | **quote → concession（该认就认）→ evidence-backed response → exact manuscript change**；每点带 `response_class` |
| 红线 | **绝不能声称做了 `EXPERIMENT_MATRIX.json` / `EXPERIMENT_LOG.md` 里不存在的实验** |

> 它是 advisory、人审的交付物，**没有机器门**；但「引用不存在的实验」是硬红线（与 `rebuttal` SKILL.md 及 artifact-registry 一致）。`deepen` 模式下的正文仍要遵守 SCI body voice（stance-first、zero-apology），不要把 reviewer-response 语气写进论文正文。

---

## 4. `publishability-score` — 6 维可发表性（Phase 15.5）

| 项 | 内容 |
|---|---|
| 输入 | `main.pdf` + `main.tex` + `experiments/` + `.sciforge/audits/` + `CLAIMS_FROM_RESULTS.md` + `PIPELINE_STATUS.md` + `COMPILE_REPORT.json` + `RESULT/STATUS/EXPERIMENT_RESULTS.json` |
| 输出 | `.sciforge/verdicts/PUBLISHABILITY_SCORE.json` + `.sciforge/audits/PUBLISHABILITY_SCORE.md` |
| 关键 | **6 维打分**；**`main-experiment-logic-in-place` 是主逻辑轴**；区分「缺补充实验」与「主逻辑不成立」 |
| schema | `PUBLISHABILITY_SCORE.schema.json` 6 required：`q_id, scored_at, verdict, total_score, dimensions, main_logic_gating`；verdict 枚举是 `SUBMISSION_READY / SUPPLEMENTARY_GATE…`（**不是 6 态**） |

**硬门**：`FAIRNESS.json` PASS 是主实验逻辑轴的必要条件；`deepen` 模式下若论文表格数字早于 fairness 重跑，会标 `numbers_stale: true` 并被判无效直到重出表。`scripts/fairness_gate.py` 负责。

> 与 persona 的 `READY/ALMOST/NO/REJECT` 是**两套不同阈值**，不要混用：`publishability-score` 是可发表性 machine verdict，persona 是评审分数结论。

---

## 5. 这条链的 SOP

```
Phase 10  result-to-claim
          ├─ 3-fidelity 判 claim 强度
          ├─ TDAL from tdal_compute.py
          ├─ ABLATION_LEDGER.json (s2_ablation 门)
          └─ CLAIM_ANCHORS.json + claim_anchor_gate.py
              ↓
Phase 14  auto-review-loop（角色轮换 ≤3 轮，只喂 raw artifacts）
          ├─ score <6  → L10 回 Phase 6
          ├─ 校准分 <8 → REBUTTAL_PLAN.json + 真实补充实验（≤2 轮）
          ├─ kill-argument 成立 → L11 BA 回 Phase 2
          └─ rebuttal（需要对外回复信时）
              ↓
Phase 15.5 publishability-score（主逻辑轴 + FAIRNESS PASS）
```

**每个 completion 声明都受拦截**：编排器的 completion-declaration interceptor 会检查硬约束字段是否齐全，不齐全则 PASS 降 `IN_PROGRESS`；同时 budget-underuse guard 若发现「预算只花了一半却还有 open verdict」→ WARN `budget_underuse` 并要求 `completion_justification` 解释每条未尝试路线。

---

## 6. 对应脚本

| 脚本 | 对应 |
|---|---|
| `scripts/tdal_compute.py` | T/D/A/L、joint、floors，写 `TDAL.json` |
| `scripts/claim_anchor_gate.py` | claim 锚点解析 + node outputs 哈希漂移 |
| `scripts/s2_ablation_gate.py` | Phase 10 消融门 |
| `scripts/validate_verdicts.py` | `REVIEW_*` / `BLINDSPOT_CHECK` / `PUBLISHABILITY_SCORE` schema |
| `scripts/verifiers/verify_review_ledger.sh` | ledger 单对象 + per-round 词汇 |
| `scripts/fairness_gate.py` | 主实验逻辑轴的 fairness PASS |
| `scripts/s2_audit.py` | Phase 16 gain 算术 / split / method↔code parity |

---

## 7. 检查清单

- [ ] `CLAIMS_FROM_RESULTS.md` 每条 claim 有 fidelity / confidence / evidence，且强度未超证据
- [ ] `TDAL.json` 由脚本计算，floors 与 `missing_inputs` 已体现
- [ ] `CLAIM_ANCHORS.json` 全 `resolved=true`，outputs 哈希未漂移
- [ ] `REVIEW_LEDGER.json` 是单对象 `details.rounds[]`；`BLINDSPOT_CHECK.json` 每轮覆写
- [ ] reviewer 只拿到路径 + raw artifacts；persona 未 inline；trace 已留
- [ ] 6.0 / 8.0 两条阈值分别处理；rebuttal 的补充任务真的执行过
- [ ] `REBUTTAL_LETTER.md` 没有引用不存在的实验
- [ ] `PUBLISHABILITY_SCORE.json` 用 `SUBMISSION_READY` 系列 verdict（非 6 态），主逻辑轴 + FAIRNESS PASS

---

## 8. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中 `Claim / ClaimAnchor / TDAL / Verdict / VisualReview` 与 `LoopBack` L10/L11 由本组落地；§4.1 治理层的完成声明拦截也在这里起作用。
GGR 复现层的 `finalize()`（`Align_mixed` / `Perf Gap` / `ClaimAnchor` 三哈希 / `overall=PASS`）与 `publishability-score` 是同一类「最终裁决」节点，可互为模板。
