# P1b · `domain-learner` — 领域特征文献学习器（唯一真相源）

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/domain-learner/SKILL.md`（v1.7.2，182 行）
> **功能批次**：① 领域与选题层
> **机械对应代码**：`scripts/tdal_compute.py`（A 维 / 联合置信 / floors）、`scripts/domain_*` 无独立实现（契约型）
> **性质判断**：**契约型 skill**；它是 8 个 meta-skill 中**唯一持有全局配置写入权**的一个。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `domain-learner` / `1.7.2` |
| `type` / `role` | `meta-skill` / `domain-characteristic-learner` |
| 管线阶段 | **Phase 1b**（Phase 1a 之后、Phase 4broad 之前） |
| 阶段模式 | **`[MUST]`**，不可跳过 |
| 单一写入者 | `refine-logs/domain-signature.json`（**sole writer**） |
| 消费者 | Phase 2 / 2.5 / 2.5b / 3 / 5 / 6 / 10 / 12 共 8+ 个下游 skill |
| 置信门 | `learning_confidence >= 0.7` 才允许应用学习结果 |

---

## 2. 解决什么问题

### 2.1 核心痛点：规则硬编码 vs 领域漂移

`/domain-signature` 用规则从问题文本猜领域，但规则会失配、会过时、覆盖不到交叉学科。若让这个猜测直接驱动后续所有阶段，整篇论文的方法论、写作风格、证据标准都会**系统性地偏**。

### 2.2 核心哲学

> **Do NOT pre-define domain characteristics. Search the literature, analyze the problem, and LEARN what makes this domain unique.**

每次运行**从零学习**，不预置领域表。用 `/universal-retrieval` 搜文献 + 读 3–5 篇 seed paper，从证据本身归纳出这个领域的「方法分布 / 失败模式分布 / 写作范式 / 证据规范」。

### 2.3 v6.0 新增：治「不知道好论文长什么样」

CRUX（arXiv:2607.27191）失败模式 #1 是「LLM 不知道本领域什么算充分证据」。因此 learner 不止抽取**用了什么方法**，还抽取**什么算够格的证据**：

| `evidence_norm_profile` 字段 | 含义 |
|---|---|
| `sample_size_norm` | 典型样本量 / seed 数 / 规模门槛 |
| `control_design_norm` | 必需的对照组设计（baseline + sham/placeholder） |
| `effect_reporting_norm` | 效应量与 CI、p 值是否够用、要不要不确定性量化 |
| `negative_result_norm` | 阴性结果在什么条件下可发表 / 只能进 Limitations |
| `exemplar_venues` | 作为标尺的标杆期刊/会议 |
| `learning_basis` | 规范从哪批文献归纳出来 |

**诚实降级**：若文献太薄支撑不起某条规范，字段写 `"unknown — defaulting to conservative"`，消费者回退到内置保守默认，**绝不发明规范**。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | `Phase 1 → 1a → **1b** → Phase 4broad → Phase 2 → 2.5 → 2.5b → 3 → ...` |
| 前置 | Phase 1 问题分解 + `REP.json`；可选 1a hint 作为 prior |
| 后继 | 几乎全部阶段；它是**全局配置的唯一来源** |
| 门 | `learning_confidence >= 0.7`（orchestrator Phase Mode Table L258） |
| 失败 | 学习失败 → 默认 `general` profile + WARN，管线继续但标记「domain adaptation 降级」 |
| 回退 | 3 轮 fallback → `BLOCKED`（MUST 阶段） |

### 3.1 领域签名传播图（orchestrator §Domain Signature Propagation）

```
Phase 1a  /domain-signature   OPTIONAL  → domain-signature-hint.json（prior）
     ↓
Phase 1b  /domain-learner     MUST      → domain-signature.json（sole writer）
     ↓
Phase 2     /idea-discovery          → 调整 4 视角权重
Phase 2.5   /adversarial-falsification → 装载领域失败模式 + 校准 EG 的 N/A 判定
Phase 2.5b  Engineering Grounding    → 领域相关的 EG 子维度权重（Compute/N/A）
Phase 3     /novelty-check           → 调整新颖性评价权重
Phase 5     /method-registry         → 调整假设打分准则
Phase 6     /verification-routing    → experiment-first / theory-only / hybrid 路由
Phase 10    /result-to-claim         → 校准 claim 置信 + evidence_sufficiency
Phase 12    /paper-writing           → 选写作风格 / 引用格式 / 章节结构
```

**设计要点**：每个下游 skill **在启动时独立读取** `domain-signature.json`，而不是由 orchestrator 把内容注入 prompt。这是「pointer-load, do NOT inline」上下文经济原则的体现：契约是路径，不是正文。

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | 全篇写作范式 | `writing_profile.style` / `citation_format` / `section_structure` | 决定 elsarticle 模板内各 section 的组织与引用样式 |
| **论文层** | 稿件定位 | `exemplar_venues` + `evidence_norm_profile` | 决定「什么质量算可发表」，供 Phase 15.5 publishability-score 使用 |
| **算法层** | 方法先验分布 | `methodology_profile.standard_methods` + **`method_frequencies`**（带频次） | 决定 idea-discovery 的视角权重、method-registry 的假设打分 |
| **算法层** | 验证路线 | `verification_approach` / `reasoning_paradigm` | 决定 Phase 6 是 SymPy 推导、数值仿真还是真实实验 |
| **代码层** | 实验矩阵规模 | `evidence_norm_profile.sample_size_norm` / `control_design_norm` | 决定 seed 数、对照组数量、实验矩阵行数 |
| **代码层** | 依赖选择 | （间接）`standard_methods` 决定要用哪些库 | 与 `dep_gate.py` 的 `dependencies.json` 声明式依赖相接 |
| **数据层** | 数据契约 | `data_profile` / `min_sample_size` / `typical_sources` | 决定数据获取路径与最小可用样本量 |
| **证据层** | claim 强度 | `effect_reporting_norm` / `negative_result_norm` | 决定 result-to-claim 是给 numerical 还是 qualitative fidelity、阴性结果去向 |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入：Problem 描述 + seed papers（3–5 篇）+ 可选 hint.json + 文献检索能力
  ↓
Step 1  领域特征文献检索（3 类查询）
  ↓
Step 2  Seed Paper 分析（读 3–5 篇，抽 methodology/style/citation/failure/robustness）
  ↓
Step 3  合成结构化领域画像（含 v6.0 evidence_norm_profile）
  ↓
Step 4  写 domain-signature.json，供所有下游独立读取
输出：refine-logs/domain-signature.json（唯一真相源）
      refine-logs/domain-learning-log.md（检索式、分析、合成过程）
```

### 5.1 Step 1 的三类检索式

| 检索 | 示例查询 | 产出 |
|---|---|---|
| 标准方法 | `"common signal-processing methods in time-series anomaly detection"` | 方法频次分布（如 spectral 40% / thresholding 35% / model-based 25%），基于 50 篇综述 |
| 常见失败模式 | `"common pitfalls in time-series periodicity and anomaly analysis"` | 失败模式频次（sensor noise 45% / non-stationarity 35% / edge effects 20%） |
| 标准论文结构 | `"typical structure of a physics/datalab measurement study"` | 章节骨架（Problem → Model → Measurement → Analysis → Robustness → Conclusion） |

### 5.2 Step 2 的 seed paper 抽取字段

`title` / `venue` / `methodology` / `structure` / `citations`（引用格式）/ `key robustness checks`。

### 5.3 Step 3 输出 JSON 结构

```json
{
  "learner_version": "2.0",
  "learning_method": "literature_search + seed_analysis",
  "sources_consulted": ["(50 篇综述)", "(seed paper 1)", "(seed paper 2)"],
  "learning_confidence": 0.85,
  "domain_profile": {"primary_domain": "...", "evidence_type": "...", "reasoning_paradigm": "empirical"},
  "methodology_profile": {"standard_methods": [], "method_frequencies": {}, "verification_approach": "...", "learning_basis": "..."},
  "failure_mode_profile": {"common_failures": [], "failure_frequencies": {}, "learning_basis": "..."},
  "writing_profile": {"style": "...", "citation_format": "...", "section_structure": "...", "learning_basis": "..."},
  "evidence_norm_profile": {"sample_size_norm": "...", "control_design_norm": "...",
                            "effect_reporting_norm": "...", "negative_result_norm": "...",
                            "exemplar_venues": [], "learning_basis": "..."}
}
```

### 5.4 Step 4 学习失败处理

三次检索全 0 结果 → 写 `Learning Failure Report`（含检索式清单）→ 使用 `general` 默认 profile → 记 WARN 并建议用户补 2–3 篇 seed paper。**不静默失败、不编造领域特征**。

---

## 6. 怎么做（机制与配置）

| 参数 | 默认 | 作用 |
|---|---|---|
| `learning_mode` | `literature` | `literature` / `seed_only` / `hybrid` |
| `min_papers_for_learning` | `3` | 少于 3 篇视为不可靠 |
| `confidence_threshold` | `0.7` | 低于此值不应用学习特征 |
| `fallback_to_default` | `true` | 学习失败退回 general |

| 机制 | 说明 |
|---|---|
| 从零学习 | 每次运行不预置领域表，避免规则硬编码 |
| 频次化 | 方法与失败模式都带 `*_frequencies`，把「定性印象」变成可加权数值 |
| 溯源 | 每个 profile 都带 `learning_basis` / `sources_consulted` |
| 种子优先 | `Seed papers > literature search`（两者都有时种子论文信号最可靠） |
| 单一写入者 | 只有 learner 写 `domain-signature.json`；learner 完全不可用才用默认行为，hint 永不作 fallback |

---

## 7. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `DomainProfile` | `primary_domain`, `evidence_type`, `reasoning_paradigm` | `PRODUCED_BY →` `domain-learner`；`CONSUMED_BY →` 8 个下游 skill |
| `MethodologyProfile` | `standard_methods[]`, `method_frequencies{}`, `verification_approach` | `WEIGHTS →` `IdeaPerspective`；`SELECTS →` `VerificationRoute` |
| `FailureModeProfile` | `common_failures[]`, `failure_frequencies{}` | `FEEDS →` `FalsificationAttack` |
| `WritingProfile` | `style`, `citation_format`, `section_structure` | `SHAPES →` `PaperSection` |
| **`EvidenceNormProfile`** | `sample_size_norm`, `control_design_norm`, `effect_reporting_norm`, `negative_result_norm`, `exemplar_venues` | `CALIBRATES →` `ClaimConfidence`；`SIZES →` `ExperimentMatrix`；`WEIGHTS →` `PublishabilityScore` |
| `LearningConfidence` | `0–1`，阈值 0.7 | `GATES →` 是否应用学习结果；`FEEDS →` TDAL 的 A 维 |
| `LearningBasis` / `SourceConsulted` | 文献出处 | `PROVENANCE_OF →` 每个 profile（防幻觉） |
| `GeneralProfile` | 默认领域画像 | `FALLBACK_FOR →` `DomainProfile` |

**最重要的本体约束**：`SingleWriter` + `IndependentReadAtStartup` + `PointerLoad`。三者共同构成「全局配置不随上下文压缩漂移」的结构保障 —— 对应 orchestrator 的 Constraint Re-injection 机制。

---

## 8. 对应 `scripts/` 代码

本 skill 同样**没有专属脚本**，但它的输出是多个确定性脚本的输入。最核心的是 `scripts/tdal_compute.py`：

### 8.1 `tdal_compute.py` — TDAL 四维联合置信（v1.6, A1）

该脚本解决了「`domain-adaptation-contract.md` 从 v2.8 就锁定了公式，却一直没人真正计算、result-to-claim 的 TDAL 只是散文」的问题。它**只从已有机器产物推导**，不给宿主增加新负担：

| 维度 | 锁定公式 | 代码位置 |
|---|---|---|
| **T**（理论） | `0.30×sympy + 0.25×logic + 0.25×falsification + 0.20×theory_data(0.5 neutral)` | L52-76 |
| **D**（数据可得性） | `0.50×ouroboros + 0.30×oss_data_check + 0.20×theory_only_flag` | L78-88 |
| **A**（领域适配） | `0.80×learner_confidence + 0.20×seed_match(0.5 neutral)` | **L91-96** |
| **L**（文献支持） | `0.50×supporting + 0.30×non_contradicting + 0.20×non_gap` | L98-113 |
| **joint** | `T × D × A × L` | L115 |

与 `domain-learner` 直接相关的几行：

```python
sig = _load(rl / "domain-signature.json")                 # L91
lc = _num((sig or {}).get("learning_confidence"), None)   # L92
if lc is None:
    lc = 0.3                                              # L94 契约回退：general baseline
    missing.append("domain_learner")                      # L95
A = 0.8 * lc + 0.2 * 0.5                                 # L96
```

**语义**：learner 的置信直接决定 A 维；learner 没跑 → `A` 掉到 `0.8×0.3+0.1=0.34`，并且 `missing_inputs` 非空会把最终 verdict 从 `STRONG` 压到 `MODERATE`（L130-131）。这就是「MUST 阶段」的机器化强制：不装依赖也能跑，但拿不到高置信。

### 8.2 floors（L128-131）

```
任一维 = 0                    → verdict 至多 WEAK
missing_inputs 非空            → STRONG 降为 MODERATE
FALSIFIED_SIGN                → UNSUPPORTED
total_papers = 0              → L = 0 且标记 literature_search 缺失
```

### 8.3 其他相关脚本

| 脚本 | 关系 |
|---|---|
| `scripts/gap_gate.py` | Phase 4broad 的文献 gap 门；learner 的文献检索能力与它共用 `/universal-retrieval` |
| `scripts/sciforge_audit.py` | 汇总全部 gate 为一个硬退出码（"one call, hard exit code"） |
| `scripts/validate_verdicts.py` | 每个 Phase 边界做 verdict schema 校验 |

> **架构洞察**：meta-skill 是「给模型的散文契约」，scripts 是「给内核的确定性判定器」。二者通过**文件产物**耦合，而不是函数调用。`domain-learner` 写文件 → `tdal_compute.py` 读文件 → orchestrator 读机器 verdict。这正是「Mechanical verdicts via tool, not prose」。

---

## 9. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `domain-signature.json` | `.sciforge/refine-logs/` | 8+ 下游 skill + `tdal_compute.py` |
| `domain-learning-log.md` | `.sciforge/refine-logs/` | 人读 / 审计 |
| `TDAL.json` | `results/` | Phase 10 result-to-claim（由 `tdal_compute.py --write` 生成） |

---

## 10. 边界与反模式

- ❌ 预定义领域特征表；❌ 让 hint 直接成为最终签名
- ❌ `learning_confidence < 0.7` 仍应用学习特征
- ❌ 文献太薄时**发明** evidence norm（必须写 `"unknown — defaulting to conservative"`）
- ❌ 在 orchestrator 里把签名正文内联进每个 prompt（应传路径）
- ✅ 每个 profile 都带 `learning_basis`；seed paper 优先于检索统计

---

## 11. 对「分子算法设计」应用层本体的可迁移点

1. **把 `evidence_norm_profile` 变成一等节点**：分子生成领域可写「≥3 seeds、必须报 mean±std、必须有 scaffold split、必须有 baseline + ablation、阴性结果进 Limitations」，直接约束实验矩阵与 claim 置信。
2. **频次化先验**：`method_frequencies`（如 GNN 0.45 / diffusion 0.30 / autoregressive 0.15 / 其它 0.10）可作为 idea-discovery 视角权重的数值来源，而不是拍脑袋。
3. **单一写入者 + 哈希锁**：`domain-signature.json` 应带 `spec_hash`，下游读取时校验，防止长链路中领域配置被悄悄改写。
4. **与 capfactory 语义层对接**：`DomainProfile` 可映射为 `ResearchField` 节点，`EvidenceNormProfile` 映射为 `EvaluationProtocol` 的约束属性，`LearningBasis` 映射为 `SUPPORTED_BY → SourcePaper/Evidence`。
