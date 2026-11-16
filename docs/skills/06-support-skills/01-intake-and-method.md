# 指导 · 入口分类、方法预注册与推导（5 个 support skill）

> **覆盖**：`intake-triage`(74) · `adversarial-falsification`(257) · `method-registry`(417) · `theory-derivation`(308) · `invariant-check`(166)
> **DAG 位置**：Phase 0 前置 → 2.5 → 5 → 6a → 9（以及每个边界）

---

## 1. `intake-triage` — 用户投料的分类器（无门）

| 项 | 内容 |
|---|---|
| 输入 | 用户丢在工作区根或 `intake/` 的**任意组合**（稿件 / 审稿意见 / 数据 / 代码 / 文献） |
| 输出 | `.sciforge/verdicts/INTAKE_MANIFEST.json` + `INTAKE_REPORT.md` |
| 作用 | 给 `mode` 选择提供路由提示：哪些阶段 **inherited**、哪些必须 **re-run**；给 `claim_mode` / `discipline` 建议；记录 user-request ledger |
| 门 | **无**（planning artifact），下游门不变 |

**指导**：这是 `mode=full / revision / deepen` 的事实来源。有稿件 → 建议 revision/deepen；只有问题 → full。它**不替代** orchestrator 的 mode 决策，也不得擅自跳过阶段；`INTAKE_MANIFEST.json` 未登记在 22 个 verdict 里，属于未注册类，不要指望 `validate_verdicts.py` 强制它。

---

## 2. `adversarial-falsification` — 先杀后证（Phase 2.5，MUST）

| 项 | 内容 |
|---|---|
| Purpose | **6 维证伪攻击**：assumption scoring → counterexample → literature adversarial search → analogy → sandbox feasibility → 汇总 |
| 输入 | `IDEA_CANDIDATES.md`（来自 `/idea-discovery`） |
| 输出 | 每个 idea 一个 `SURVIVE / WEAKENED / FALSIFIED` verdict + `FALSIFICATION_RECORD.json` |
| 核心 | **Forced falsification：先尽力杀死 idea，再试图证明它对**；「看出为什么错，比证明它对容易」 |
| 门 | 假设健康 ≥6 **或**无反例；WEAKENED → L1 回 Phase 2；FALSIFIED → 记 `failed_ideas.json` 并评估下一个（L2） |

**为什么这一阶段不能跳**（orchestrator Early Exit 表明确写「Phase 2.5 MANDATORY — never skipped」）：它是 `fantasy_gate.py` **Gate 4 可证伪性**的证据来源 —— 没有 `FALSIFICATION_RECORD.json` 且 ≥1 次反例尝试，整篇稿子会在 Phase 12 前被判 `WEAKLY_GROUNDED` 或 FAIL。

**它还负责**：读 `domain-signature.json` 的 `failure_mode_profile.common_failures` 装载领域失败模式；校准 Engineering Grounding 的 N/A 子维判定（见 [04-shared-references/03-ideation-and-evaluation.md](../04-shared-references/03-ideation-and-evaluation.md) §5）。

**检查清单**：6 维攻击是否都留下痕迹？反例是否在 `dynamic-sandbox` 里数值验证过？WEAKENED 是否真的回 Phase 2 并改变了输入（L1 的「状态改变」硬纪律）？

---

## 3. `method-registry` — 预注册 + hash lock（Phase 5，MUST + 人工）

| 项 | 内容 |
|---|---|
| Purpose | **防止事后挑方法**（post-hoc method shopping） |
| 输入 | `refine-logs/FINAL_PROPOSAL.md` |
| 输出 | `methods/METHOD_REGISTRY.md`（**8 节**）+ `REGISTRY_HASH.txt` + `.sciforge/APPROVAL_LOG.txt`；另产 `METHOD_BINDING.md` / `OUTCOME_CLASSIFICATION.md` / `EXPERIMENT_MATRIX.json` / `EVALUATION_PROTOCOL.{md,json}` |
| 关键 | **Section 3 (Method Selection) 在 lock 后不可变**；assumption quality scoring；**强制人工审批** |
| 门 | Phase 5→6 人工检查点；hash 漂移 → L4 回 Phase 5 重建（3 轮） |

**8 节结构的下游消费者**（`artifact-registry.md`）：`/leakage-audit`、`/experiment-execution` (Phase 1.7 校验 `METHOD_BINDING` 的 LOCKED 状态)、`/result-to-claim` (Step 3.2 estimator 交叉核对)、`/paper-writing`、`/invariant-check`、`/citation-audit`、`/auto-review-loop` (econ persona 的 AIM 链)、`replication/run_all.sh`。

**操作要点**：
1. 在跑推导/实验**之前**写完 8 节并算 Section 3 的 SHA256 → `REGISTRY_HASH.txt`；
2. 让人工确认并写 `APPROVAL_LOG.txt`；`test_mode` 只是**暂缓**批准但活仍要做，`human_skip` 才是生产级委托（见 [05-orchestrator/auto-pipeline-guide.md](../05-orchestrator/auto-pipeline-guide.md) §1.3）；
3. 若 `EXPERIMENT_MATRIX.json` 不完整，hash lock **拒绝**并在 `REGISTRY_HASH.txt` 写 `BLOCKED: experiment_matrix_incomplete`（这是校验器唯一接受的非哈希形式）；
4. 预注册四要素（metrics lock / baseline parity / baseline re-implementation / anti-cherry-picking）由 `EVALUATION_PROTOCOL` 语义承诺，**字段名未固定**，靠 `result-to-claim` 的 `parity_check / all_seeds_reported / full_grid_reported` 落实（见 [schemas-guide.md](../04-shared-references/schemas-guide.md) §8 第 12 条）。

---

## 4. `theory-derivation` — SymPy 逐步验证（Phase 6a，ROUTED）

| 项 | 内容 |
|---|---|
| Purpose | 把口头推理变成机器可验证的符号推导 |
| 输入 | `FINAL_PROPOSAL.md`（idea + assumptions） |
| 输出 | `src/derivations/{problem_id}/derivation.py` + `derivation_output.md` + `verification_report.md` + `PROOF_AUDIT.json` / `DERIVATION_PACKAGE.md` |
| 关键 | **每步 SymPy 验证**；3 模式 `derive / verify / simplify`；theory-only 用 `engine=manual`，输出标 `[not machine-verified]` 并下调 claim 强度 |
| 门 | SymPy 推导成功 + 逐步机器验证 PASS；失败回 Phase 1（≤3 轮） |

**指导**：
- 与 `/dynamic-tooling` 的 `symbolic-reasoner` 模板配合（需要专用验证器时）；
- `PROOF_AUDIT.json` 是 **audit family** verdict：必须 6 态 `verdict` + `audited_input_hashes` + `trace_path`（见 schemas-guide §5）；
- theory-only 路径：5 → 6a → 6b/6c SKIP → 7 (Type IV = NOT_APPLICABLE) → 8；Phase 10 以 qualitative fidelity 为正常；
- OSS **不按学科分叉**，领域方法论由运行时推理 + `dynamic-sandbox` 承担。

---

## 5. `invariant-check` — 结构完整性（Phase 9 + 每边界）

| 项 | 内容 |
|---|---|
| Purpose | 阶段边界的结构检查：文件存在、Q-id 冻结、verdict 有效性 |
| 输入 | `FINAL_PROPOSAL.md` + 当前阶段产物 |
| 输出 | `INVARIANT_CHECK.json` + `INVARIANT_CHECK.md` |
| 关键 | **只有 INV-G1 (PROBLEM_ANCHOR_FREEZE) 生效**；不做质量评估，只查结构 |
| 门 | FAIL → 回 Phase 0 重新锚定 Q-id；缺 Q-id 引用的产物直接 BLOCK |

注意 schema 里它的 verdict 字段叫 **`overall_verdict`** 而不是 `verdict`（`INVARIANT_CHECK.schema.json`），且必带 `timestamp / phase_boundary / discipline_context / checks`。这是注册审计族里唯一字段命名不同的一个，写错就校验失败。

---

## 6. 本组 SOP（照顺序）

```
投料 → intake-triage 分类 + 建议 mode
     → [full] idea-discovery → adversarial-falsification（先杀后证）
     → method-registry 写 8 节 + Section 3 hash lock → 人工批准
     → verification-routing → theory-derivation（6a）
     → invariant-check（每个边界复验 INV-G1）
```

| 常见失败 | 正确动作 |
|---|---|
| 证伪 FALSIFIED | L2：记 `failed_ideas.json`，换下一个候选，**不是**回 Phase 2 |
| 证伪 WEAKENED | L1：回 Phase 2 重生 idea，最多 3 轮；必须消费失败证据 |
| `REGISTRY_HASH` 漂移 | L4：重建 registry（3 轮）；同时检查 `LEAKAGE_AUDIT` 是否需重审 |
| 实验矩阵不完整 | method-registry §3.5：写 `BLOCKED: experiment_matrix_incomplete`，不要锁一个假 hash |
| 推导与实验结论矛盾 | `LOGIC_VERIFICATION` FATAL → **BA 回 Phase 2**（全局 ≤2 轮），不是普通 3 轮 fallback |
| Q-id 缺失 | 回 Phase 0 重锚；**不要**在本地补一个 Q-id 蒙混过关 |

---

## 7. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中：`ProblemAnchor`(INV-G1)、`MethodRegistry`(BINDS + hash lock)、`Assumption / DerivationStep / ProofAudit / FalsificationRecord` 全部来自本组；`LoopBack` 的 L1/L2/L4 也在这里落地。
GGR 复现层的 `MethodLock` / `spec_hash` 与 `REGISTRY_HASH.txt` 是同一机制：`FINAL_PROPOSAL.md` 对应 `ReproSpec`，`METHOD_BINDING.md` 对应 `code_plan`，`EXPERIMENT_MATRIX.json` 对应 `SAU protocol`。
