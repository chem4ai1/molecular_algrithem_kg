# 指导 · 领域适配与置信契约（14 份）

> **覆盖源文件**：`domain-adaptation-contract.md`(305) · `domain-adaptation-guide.md`(734) · `domain-adaptive-pipeline.md`(172) · `domain-contribution-protocol.md`(197) · `domain-failure-modes.md`(104) · `domain-signature-consumer.md`(236) · `discipline-context.md`(90) · `discipline-paradigm.md`(90) · `discipline-writing.md`(213) · `confidence-uplift.md`(314) · `ouroboros-integration.md`(609) · `methodology-and-context-contract.md`(74) · `multi-fidelity-evaluation.md`(205) · `verification-routing.md`(59)
> **一句话**：这组文件回答「系统怎么知道本领域什么算充分证据」，以及「证据不足时怎么诚实降级/提升置信」。

---

## 1. 首要原则：学科无关的「无操作」契约

`discipline-context.md` 明说 OSS **没有 `DISCIPLINE_CONTEXT`**，只有一个 `general` 单行 no-op stub。主仓库按 economics / cs-ml / physics / general 分叉的功能已被移除：

- ❌ 不要重新引入 `source_priorities` 的学科分支（文献源固定 arXiv → S2 → CrossRef → PubMed → Web → OpenAlex）；
- ❌ 不要按领域标签选方法框架（AIM / SOTA / PNV）；
- ✅ 按**问题性质**在 Phase 1 选 paradigm，由 `/universal-retrieval` 与运行时推理承载领域差异。

### 4 范式（`discipline-paradigm.md`）

| 范式 | 典型证据 | 验证形态 |
|---|---|---|
| `formal` | 证明、推导 | theory-only，SymPy / 逐步机器验证 |
| `empirical` | 数据、估计 | experiment-first |
| `interpretive` | 文本、诠释 | qualitative fidelity 为正常 |
| `design` | 构造、系统 | 实验 + 工程落地性（EG） |

`discipline-writing.md` 把范式映射到章节集（mode-selected，见 `paper-modes.md` §3）与通用写作原则；**领域惯例由 agent 运行时判断，不是 skill overlay**。

---

## 2. 领域签名的消费规则（`domain-signature-consumer.md`）

唯一写入者是 Phase 1b `/domain-learner`，文件 `refine-logs/domain-signature.json`。每个 skill **在启动时独立读取**（配合 `startup-protocol.md` 5 步）：

| 消费方 | 读什么 | 用来做什么 |
|---|---|---|
| `/idea-discovery` | `domain_profile.evidence_type` | 4 视角权重 |
| `/adversarial-falsification` | `failure_mode_profile.common_failures` | 装载领域失败模式；校准 EG 的 N/A 判定 |
| Engineering Grounding | `methodology_profile` | 领域相关子维权重（Compute / N/A） |
| `/novelty-check` | `domain_profile` | 评价权重 |
| `/method-registry` | `methodology_profile` | 假设打分准则 |
| `/verification-routing` | `domain_profile` + `verification_approach` | 路由 |
| `/result-to-claim` | `evidence_norm_profile` | claim 置信校准 + evidence sufficiency |
| `/paper-writing` | `writing_profile` | style / citation format / 章节结构 |

**Fallback**：签名不存在 → 记警告、用默认行为、管线继续但标记「domain adaptation 降级」。**绝不让 Phase 1a 的 hint 直接充数**。

### 失败模式目录（`domain-failure-modes.md`）

提供 catalog +「How to Extend」。新增领域失败模式时：写清触发条件、检测信号、反例构造方式，并在 learner 的 `failure_mode_profile.common_failures` 中被引用，才能进入 2.5 的攻击向量。

---

## 3. TDAL 四维联合置信（`domain-adaptation-contract.md`，locked）

这是「本领域什么算够格证据」的量化核心。公式**锁死**，由 `scripts/tdal_compute.py` 唯一实现（与上次 GGR 解析一致）：

| 维 | 公式 | 输入 |
|---|---|---|
| **T** 理论 | `0.30×sympy + 0.25×logic + 0.25×falsification + 0.20×theory_data` | `PROOF_AUDIT` / `LOGIC_VERIFICATION` / `FALSIFICATION_RECORD` |
| **D** 数据 | `0.50×ouroboros + 0.30×oss_data_check + 0.20×theory_only_flag` | 数据可得性 |
| **A** 领域适配 | `0.80×learner_confidence + 0.20×seed_match` | `domain-signature.json` 的 `learning_confidence`（缺失 `=0.3` 并记 `missing_inputs`） |
| **L** 文献 | `0.50×supporting + 0.30×non_contradicting + 0.20×non_gap` | `references.bib` / `GAP_REPORT` |

```
joint = T × D × A × L
≥0.70 STRONG | 0.50–0.70 MODERATE | 0.30–0.50 WEAK | <0.30 UNSUPPORTED
```

**floors（硬约束）**：任一维为 0 → 至多 `WEAK`；`missing_inputs` 非空 → `STRONG` 降 `MODERATE`；`FALSIFIED_SIGN` → `UNSUPPORTED`；`total_papers=0` → `L=0`。

**生产者** `/result-to-claim`（Phase 10）写 `TDAL.json`；**消费者** `/paper-writing` 据此定 claim 强度；orchestrator 在 Phase 10 边界校验。`domain-adaptation-guide.md`（734 行）是 7 步执行指南 + 5 个领域示例 + 6 个验收用例，落地时按它做 acceptance test。

---

## 4. 置信不够时：`confidence-uplift.md` 三机制

当 TDAL verdict ≤ `WEAK` 时，**不是直接宣告完成，也不是偷偷加置信**，而是走有界 uplift loop：

1. 读 `Quick Reference` 与 `Three Mechanisms`（补理论验证 / 补数据可得性 / 补文献支持，具体以文件为准）；
2. 按 `Uplift Loop Bounding` 控制轮数与成本；
3. 按 `Output Schema` 写机器可读结果；
4. 遵守 `Boundaries` 与 **When NOT to invoke uplift**（例如前提缺失、检测到 falsified sign 时应直接 BLOCKED，而不是靠补证据洗白）。

> **红线**：uplift 只能补真实证据，**不能改写 T/D/A/L 的权重或 floors**。

---

## 5. Ouroboros 集成（`ouroboros-integration.md`，609 行）

| 层 | 喂给谁 | 作用 |
|---|---|---|
| **Section A — Basic** | TDAL 的 **D 维** | Phase 2.5 的数据可得性/自洽循环 |
| **Section B — Deep** | TDAL 的 **T 维 uplift** | Phase 6 / 10 的理论验证增强 |

配合 `methodology-and-context-contract.md` 的 5 条横切纪律（这是 auto-pipeline §Context Economy 的真相源）：

1. **Sufficiency Stopping**：(必填字段齐) ∧ (verdict 稳定 2 轮) ∧ (边际收益 ≤0) 才停；每个分析输出写 `stopping_rule.satisfied`。
2. **Evidence-Forcing**：每个 finding 带 `raw_stat + confidence + method`；**数据特征 ≠ 错误**（不许为美观清洗真实特征）；分析层只报告不判定。
3. **Context Economy (Bundle + Compact)**：≥10 行指令写 bundle 文件，下阶段拿路径；Phase 8 / 12 前写 20–40 行紧凑摘要。
4. **Deterministic-First + Hash Lock**：文件/字段/阈值/SHA-256 检查先于 LLM 判断；冻结产物加 hash lock。
5. **Reviewer-Only-Raw-Artifacts**：给 reviewer 传路径与原始产物，不传执行者的解释/引导结论。

---

## 6. 多保真过滤（`multi-fidelity-evaluation.md`）

治「noisy rewards and false tricks」：**三层过滤**（symbolic → numerical → qualitative），每层有 promotion gate；§5 明确「False-Trick Detection」跨领域通用；§6 给每领域资源预算；§8 给 fallback。

指导：Phase 10 `/result-to-claim` 判定 claim fidelity 时按这三档走 —— **qualitative-only 的结果只能写成 conjecture**，不得冒充数值结论；数值层必须有可重算的 `raw_stat`。

---

## 7. 验证路由（`verification-routing.md`，59 行）

| 规则 | 内容 |
|---|---|
| 入口决策 | Phase 6 **一次决定且终局**：`experiment-first`（默认）/ `theory-only` / `hybrid` |
| 写在哪 | `.sciforge/verdicts/VERIFICATION_ROUTING.json`（**不是** `refine-logs/`，见 schemas-guide §8 第 9 条） |
| `na_verdicts` | 声明该路线**合法不会产生**的 verdict；校验器据此把 missing 报 N/A 而非 pending |
| 误用 | 声明 N/A 的文件却实际存在 → WARN（路由/产物不一致） |

**实操**：先决定 route → 写文件（含 `route / evidence_type / reason / na_verdicts`）→ 再分派 6a/6b/6c → 收尾时若发生额外 skip（如 Phase 11 无图），**追加** `na_verdicts` 并重跑完整性检查，而不是新建空目录。

---

## 8. 自适应降级与贡献新证据类型

| 文件 | 用法 |
|---|---|
| `domain-adaptive-pipeline.md`(172) | **Adaptive Override Table (locked)**：按 `evidence_type` / `paradigm` 覆盖 Phase 5 / 6 / 11 的强度。按 `Override Application Protocol` 应用，产出 `Override Schema` 的机器可读记录；明确「**不是硬编码学科分支**」 |
| `pipeline-adaptive-degradation.md`(192) | **Degradation Matrix (locked)**：v2.8 起取代静态 Phase Mode Table，由领域签名驱动阶段 mode override。记录到 machine-readable override schema，遵守 fallback 与边界 |
| `domain-contribution-protocol.md`(197) | 现存 `evidence_type` 枚举不够用时，走 PR 契约：problem grounding → 证明现枚举不适配 → 给出新定义 → 补 M1 intensity 行 / M3 mode 行 → **falsification test set + 测试结果 + regression check** → learner prompt 补充 → review。这是「开放社区贡献」通道，不要绕过它私加枚举 |

> 三者的共同纪律：**override 必须有机器可读记录、必须能回退、必须说明为什么不是硬编码分支**。

---

## 9. 检查清单

**Phase 1**
- [ ] 按问题性质（非领域标签）选了 4 范式之一
- [ ] learner 产出的 `learning_confidence ≥ 0.7` 才应用学习特征
- [ ] 每个 profile 带 `learning_basis`；`evidence_norm_profile` 文献太薄时写 `"unknown — defaulting to conservative"`

**Phase 6**
- [ ] `VERIFICATION_ROUTING.json` 写在 `.sciforge/verdicts/`，含 `na_verdicts`
- [ ] 6a/6b/6c 的分派与 route 一致

**Phase 10**
- [ ] `tdal_compute.py` 从机器产物算 T/D/A/L，未手工填分
- [ ] floors 已应用；`missing_inputs` 已列
- [ ] ≤ WEAK 时走有界 uplift 或直接 BLOCKED，未改权重洗白
- [ ] claim fidelity 与三层过滤一致（qualitative-only → conjecture）

**改动领域配置时**
- [ ] 新 `evidence_type` 走 `domain-contribution-protocol.md` 的 PR 契约
- [ ] 新失败模式在 `domain-failure-modes.md` 登记并被 learner 引用
- [ ] override 写进 machine-readable schema，且未引入学科分支

---

## 10. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) §4.1 的 `DomainProfile` / `EvidenceNormProfile` / `VerificationRoute` / `TDAL` 类全部来自本组文件；GGR 复现层的 `TRAIN_FEASIBILITY` 与 `evidence_norm_profile`（≥N seeds / CI / baseline+ablation）是同一约束在训练复现场景的实例。
`tdal_compute.py` 的 A 维实现详见 [01-domain-ideation/domain-learner.md](../01-domain-ideation/domain-learner.md) §8.1。
