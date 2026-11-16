# P1a · `domain-signature` — 领域签名快速提示

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/domain-signature/SKILL.md`（v1.7.2，162 行）
> **功能批次**：① 领域与选题层
> **机械对应代码**：`scripts/tdal_compute.py`（消费 `learning_confidence`）、`scripts/sciforge_audit.py`（verdict 完整性）
> **性质判断**：**契约型 skill（prose contract）**，本身没有可执行脚本；它的机器化落点是下游的确定性 gate。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `domain-signature` / `1.7.2` |
| `type` / `role` | `meta-skill` / `domain-characteristic-extractor` |
| 管线阶段 | **Phase 1a**（问题理解之后、领域学习之前） |
| 阶段模式 | **`[OPTIONAL]`** 快速通道；v2.8 起被降级为 hint |
| 单一写入者 | 只写 `refine-logs/domain-signature-hint.json` |
| 唯一消费者 | `/domain-learner`（Phase 1b），**仅作为 prior** |
| 是否被下游直接读取 | **否**。所有下游 skill 只读 learner 写的 `domain-signature.json` |

---

## 2. 解决什么问题

### 2.1 核心痛点

一个通用论文生成系统在面对任意学科时，必须回答「这个领域认什么样的证据、用什么方法、怎么写、怎么引用、哪里最容易出错」。若把这些规则**硬编码成领域分类表**，会出现两类失败：

1. **规则失配**：交叉学科（计算生物 = CS + 生物）无法归入单一标签；
2. **冷启动**：新领域、稀疏文献时没有可用规则。

### 2.2 本 skill 的定位（v2.8 的重要修正）

早期版本把领域签名写成最终裁决，导致「rule-hardcoded signature」失败模式。v2.8 把它**降级为 OPTIONAL 的冷启动提示**：

```
Phase 1a  /domain-signature  （规则匹配 → hint.json，confidence 可 < 0.7）
      ↓ 仅作为 prior
Phase 1b  /domain-learner    （从文献重新学习 → domain-signature.json，唯一真相源）
      ↓
所有下游阶段
```

即使 1a 的规则「匹配得很干净」，learner 仍必须从文献重新推导一遍，用来抓出规则失配。这是**双通道 + 单一真相源**的抗错设计：允许快速猜测，但不允许猜测直接生效。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| 26 节点 DAG 位置 | `Phase 0（冻结 Q-id） → Phase 1（问题理解 + REP.json） → **Phase 1a** → Phase 1b → Phase 4broad → Phase 2 ...` |
| 前置 | Phase 1 的问题形式化分解、Q-id 冻结（INV-G1） |
| 后继 | Phase 1b `/domain-learner`；再之后是 Phase 4broad 文献广搜 |
| 门 | 无硬门（`OPTIONAL`）。失败 → `WARN` + 继续管线 |
| 人工检查点 | 无 |
| 回退 | 不适用；hint 缺失时 learner 从零开始 |

> 注意它在 **文献广搜之前**：因此它只能从「问题陈述的语言」里抽信号，不能假装掌握了领域文献。这也是它只能是 hint 的根本原因。

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | 写作规范 / 投稿定位 | `writing_profile`：style、citation_format、section_structure、typical_length、abstract_style | 决定 Intro/Method/Result 的骨架与引用格式 |
| **论文层** | 领域范式 | `domain_profile.reasoning_paradigm`（formal / empirical / interpretive / design） | 决定后续走 theory-only 还是 experiment-first |
| **算法层** | 方法选型 | `methodology_profile.standard_methods` + `verification_approach` | 决定候选方法池与验证方式（推导 / 仿真 / 实验） |
| **算法层** | 假设稳健性 | `failure_mode_profile.critical_assumptions` / `robustness_checks` | 为 Phase 2.5 证伪攻击提供攻击向量 |
| **代码层** | 实验是否需要 | `methodology_profile.requires_experiment`、`can_be_theory_only` | 决定 `VERIFICATION_ROUTING.json` 的路由（6a/6b/6c 是否启动） |
| **数据层** | 数据契约 | `data_profile`：data_type、typical_sources、data_availability、min_sample_size | 决定实验矩阵规模、数据来源与最小样本量 |
| **证据层** | 证据充分性 | `evidence_type` 六分类（causal_inference / correlational / derivational / experimental / simulational / interpretive） | 决定 Phase 10 `result-to-claim` 的置信校准口径 |

**它不碰**：具体公式推导、具体代码、具体数值结果、引用条目本身。

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入：Problem 描述 + 用户 prompt + 可选 seed 文献
  ↓
Step 1  问题陈述信号分析（4 类 direct signal + 4 类 inferred + 3 类 literature signal）
  ↓
Step 2  生成结构化签名 JSON（6 个 profile + confidence）
  ↓
Step 3  维度判定（证据类型 6 分类表 / 方法模式 6 分类表）
  ↓
Step 4  写 hint.json，交给 learner 当 prior
输出：refine-logs/domain-signature-hint.json
      refine-logs/domain-signature-report.md（人读解释）
```

### 5.1 Step 1 抽取的信号

| 类别 | 字段 |
|---|---|
| Direct | domain keywords / methodology keywords / evidence keywords / output keywords |
| Inferred | reasoning style、formality level、quantitative intensity、proof standard |
| Literature | seed paper venues、seed paper methods、citation style |

### 5.2 Step 2 的签名结构（6 个 profile）

| Profile | 关键字段 |
|---|---|
| `domain_profile` | primary_domain、secondary_domains、evidence_type、reasoning_paradigm |
| `methodology_profile` | standard_methods、verification_approach、requires_experiment、can_be_theory_only |
| `writing_profile` | style、citation_format、section_structure、typical_length、abstract_style |
| `failure_mode_profile` | common_failures、critical_assumptions、robustness_checks |
| `data_profile` | data_type、typical_sources、data_availability、min_sample_size |
| `confidence` | domain / methodology / writing 三个 0–1 置信 |

### 5.3 两张判定表

**证据类型 6 分类**：`causal_inference`（需识别策略）、`correlational`、`derivational`（证明，不需数据）、`experimental`（受控/RCT）、`simulational`（数值仿真）、`interpretive`（文本诠释）。

**方法模式 6 分类**（按触发词判定）：`difference_in_differences`、`instrumental_variables`、`structural_equation`、`machine_learning`、`theorem_proof`、`controlled_trial`。

---

## 6. 怎么做（机制与配置）

| 机制 | 实现 |
|---|---|
| 规则来源 | **从问题文本抽取，不是查领域分类表**（`Never hard-code domain-to-signature mapping`） |
| 签名性质 | 一组**概率信号**，不是标签；允许混合签名 |
| 置信下限 | `confidence < 0.5` → 退回 `general` 默认签名，不做领域适配 |
| 可修正性 | 签名始终 provisional，下游检测到更强信号可 refine |
| 与 learner 的关系 | hint 可携带粗粒度 `evidence_norm_profile`，但 learner 从文献重推且**永远 winning** |

配置参数（来自 `skill-config` 同类约定）：`learning_mode ∈ {literature, seed_only, hybrid}`、`min_papers_for_learning=3`、`confidence_threshold=0.7`、`fallback_to_default=true` —— 这些实际由 `/domain-learner` 使用（本 skill 只做 hint）。

---

## 7. 运用了哪些关键知识节点

把 SKILL.md 的字段提升为本体节点，可得到如下「领域签名」子图：

| 节点（类） | 关键属性 | 关系（边） |
|---|---|---|
| `ProblemAnchor`（Q-id，INV-G1 冻结） | `problem_id`, `description` | `HAS_SIGNATURE_HINT →` `DomainSignatureHint` |
| `DomainSignatureHint` | `signature_id`, `confidence{domain,methodology,writing}` | `IS_PRIOR_FOR →` `DomainProfile`（learner 输出） |
| `DomainProfile` | `primary_domain`, `secondary_domains`, `evidence_type`, `reasoning_paradigm` | `DETERMINES →` `VerificationRoute` |
| `MethodologyProfile` | `standard_methods[]`, `verification_approach`, `requires_experiment`, `can_be_theory_only` | `CONSTRAINS →` `MethodRegistry`（Phase 5） |
| `WritingProfile` | `style`, `citation_format`, `section_structure`, `abstract_style` | `SHAPES →` `PaperSection` / `CitationFormat` |
| `FailureModeProfile` | `common_failures[]`, `critical_assumptions[]`, `robustness_checks[]` | `FEEDS →` `FalsificationAttack`（Phase 2.5） |
| `DataProfile` | `data_type`, `typical_sources`, `data_availability`, `min_sample_size` | `SIZES →` `ExperimentMatrix` / `SeedPolicy` |
| `EvidenceType`（6 值枚举） | — | `CALIBRATES →` `ClaimConfidence`（Phase 10） |
| `ReasoningParadigm`（4 值枚举） | — | `ROUTES →` `VerificationRoute`（Phase 6） |

**关键约束关系**：`SingleWriter(domain-signature.json) = domain-learner`；`Hint ⇒ Learner` 是单向 prior，不存在 `Hint ⇒ Downstream` 边。这条「写入权唯一」约束是整个领域适配层不漂移的结构保障。

---

## 8. 对应 `scripts/` 代码

**本 skill 没有自己的脚本**。这是理解 SciForge-OSS 架构的关键：`skills/` 是给 LLM 的**行为契约**，`scripts/` 是给内核的**机械判定器**。二者的接法是「契约产出文件 → 脚本读文件并给出 exit code」。

| 脚本 | 对应点 | 具体代码 |
|---|---|---|
| `scripts/tdal_compute.py` | 消费领域学习置信，计算 TDAL 的 A 维 | `sig = _load(rl / "domain-signature.json")`（L91）；`lc = _num(sig.get("learning_confidence"))`（L92）；缺失时 `lc=0.3` 并 `missing.append("domain_learner")`（L94-95）；`A = 0.8 * lc + 0.2 * 0.5`（L96） |
| `scripts/tdal_compute.py` | 联合置信与地板约束 | `joint = T*D*A*L`（L115）；`>=0.7 STRONG / 0.5 MODERATE / 0.3 WEAK / else UNSUPPORTED`（L120-127）；任一维为 0 → 至多 WEAK（L128-129）；`missing_inputs` 非空 → 至多 MODERATE（L130-131） |
| `scripts/sciforge_audit.py` | 把各 gate 汇总成硬退出码 | 领域签名缺失不会被静默放过，会进 `missing_inputs` 影响 TDAL 等级 |
| `scripts/validate_verdicts.py` | verdict schema 完整性 | Phase 边界 `--strict --require-complete`，任何 PENDING → BLOCKED |

> **注意一个真实的不一致**：`domain-signature/SKILL.md` 的「Output Shape」段（L154-157）仍写 `domain-signature.json` + `domain-signature-report.md`，与它在正文 L11、L134 声明的「只写 `domain-signature-hint.json`」矛盾。这是 v2.8 降级改造的残留。**以正文和 orchestrator 的 Domain Signature Propagation 段为准**：唯一写入者是 learner，1a 只写 hint。文档中已按此纠正。

---

## 9. 产物与契约

| 产物 | 位置 | 说明 |
|---|---|---|
| `domain-signature-hint.json` | `.sciforge/refine-logs/` | hint，唯一消费者是 learner |
| `domain-signature-report.md` | `.sciforge/refine-logs/` | 人读解释，不参与 gate |

6 态 verdict：`PASS / WARN / FAIL / NOT_APPLICABLE / BLOCKED / ERROR`；本阶段为 OPTIONAL，失败只记 WARN。

---

## 10. 边界与反模式

- ❌ 把 hint 直接给下游消费
- ❌ 硬编码「领域 → 签名」映射表
- ❌ 把签名当离散标签（应是概率信号、可混合）
- ❌ confidence 不足仍强行应用领域适配
- ✅ 允许 learner 完全推翻 hint

---

## 11. 对「分子算法设计」应用层本体的可迁移点

1. **双层领域适配**：先用 molecule-domain 关键词给出冷启动 hint（如 `evidence_type=simulational+experimental`、`requires_experiment=true`），再由文献学习器重推；避免把「分子生成」硬编码成单一范式。
2. **写入权唯一**：`domain-signature.json` 只能有一个 writer，否则图里会出现互相矛盾的方法论节点。
3. **证据规范前置**：v6.0 的 `evidence_norm_profile` 思路可直接映射为「本领域要求 ≥N seeds / 必须报 CI / 必须有 baseline+sham 对照」，作为实验矩阵与 claim 置信的**先验约束节点**。
