# 设计反思与 v2 优化：最本质要保证什么

> 版本 2.0 · 2026-11-15
> 回顾对象：[`SCIFORGE_INTEGRATION_BLUEPRINT.md`](SCIFORGE_INTEGRATION_BLUEPRINT.md)、[`DYNAMIC_ONTOLOGY_NODE_CACHE.md`](DYNAMIC_ONTOLOGY_NODE_CACHE.md)、[`plan/` 九份计划](plan/README.md)、[`skills/` 24 份解析与框架](skills/README.md)、`src/capfactory/` 现有代码
> 配套修订：[`plan/V2_DELTA.md`](plan/V2_DELTA.md)（对 S0–S6 的逐阶段增量、H12–H16 新硬门、24 项新测试）

---

## 0. 先说结论：v1 缺了什么

v1 方案把三件事做对了：**语义层冻结**、**缓存不能成为第二真相源**、**LLM 节点不污染事实层**。但它有一个结构性的偏科：

> v1 把系统当成「一条自动流水线，人在两端签字」；而真实的科研探索是「人不断改变方向，机器不断捕捉意料之外的东西」。

具体暴露为 4 个缺口：

| # | 缺口 | v1 现状 | 后果 |
|---:|---|---|---|
| G1 | 人类只出现在「approver / 人工签字 / KILL 检查点」 | `plan/` 里 grep「人工」几乎全是 §7.3 签字项与 `approver` 输入框 | 人不能在选题、方法、范式、图、claim 等环节**提出方向或方法尝试**；只能否决，不能引导 |
| G2 | 人一旦选择，没有机制把决定传播到后续阶段 | 无 `CONSTRAINT_REINJECTION`、无 `HumanDecision` 节点、`spec_hash` 不含人的决定 | 第 3 阶段选的方向，到第 10 阶段被模型「忘掉」，长链路漂移 |
| G3 | 探索中的新知识必须「成功注册成节点」才算被捕捉 | 只有 `LLMNodeProposal` 四态；`rejected` 只是留档，无聚合、无频率、无晋升通道 | 词表外概念、对齐未命中、门 FAIL、未尝试方向这些**最有价值的信号**被当成噪声丢掉 |
| G4 | 语义层挖掘只有「字段提升」，没有「结构派生」与覆盖率雷达 | `applayer/miner.py` 的 8 个挖掘器全是 `questions/categories/metrics/leaderboard/contracts/evidence/limitations/source_papers` | 数据流闭包、方法×基准空白、谱系年份切片、代码共现等结构知识从未被显式挖掘；也无法回答「语义层还有多少东西没被用上」 |

**v2 的一句话转向**：

> 从「LLM 生成节点 → 缓存 → 晋升」的单通道，改成
> **「确定性派生 + 探索信号 + LLM 提案 + 人类思路」四路输入，汇入同一个可追溯、可重算、可干预的动态本体**。

---

## 1. 深度思考：最本质要保证什么

### 1.1 先找出根本矛盾，而不是先列功能

这个系统要同时满足四件事，且它们两两冲突：

| 目标 | 需要的性质 | 与谁冲突 |
|---|---|---|
| 基于 783 篇论文的事实可信 | **封闭性**：只有可核验证据能进事实层 | 与「发现新知识」冲突 |
| 能在探索中发现并积累新概念 | **开放性**：词表外、被拒、失败都要留下 | 与「事实层不被污染」冲突 |
| 26 阶段能自动跑、可重算 | **确定性**：规则/AST/哈希优先，少用 LLM | 与「人随时改变方向」冲突 |
| 研究者能随时注入思路、换方法 | **可干预性**：机器不得做终局判断 | 与「全自动、幂等」冲突 |

所以「最本质」不是某个功能，而是**同时守住这四条边界的一组不变量**。任何设计优化，只要破坏其中一条，就属于用短期便利换长期不可信。

### 1.2 七条不变量（v2 的宪法）

| # | 不变量 | 精确表述 | 守住哪条边界 | v1 状态 |
|---|---|---|---|---|
| **I1 事实主权** | 客观事实只由 NON_LLM 证据（原文 / 表格 / AST / 规则 / 哈希）写入语义层；语义层 6 类/9 关系冻结；`attribution="llm_proposal"` 永不入内 | 封闭性 | ✅ 已有（H1/H3/H5） |
| **I2 单真相源** | 任何派生/缓存/增量都必须能由「语义层 + 确定性规则 + append-only 决策日志」重算；`增量 ≡ 全量重建` | 抗分叉 | ✅ 已有（H2） |
| **I3 全谱留痕** | **探索中的「未命中、词表外、被拒、失败、未尝试方向」都必须成为可查询节点**，而不是日志噪声；捕捉率 100%，晋升率可控 | 开放性 | ⚠️ 部分（只留 rejected 文件） |
| **I4 人类主权** | 方向、方法、终局判断、类/关系晋升、KILL 都必须有人工可选入口；机器不得替人做终局判断；`gate` 超时只能 BLOCKED | 可干预性 | ❌ 缺（只有签字） |
| **I5 决定可传播** | 人的每个选择生成 append-only `HumanDecision`，并在后续**每个边界逐字复述**（Constraint Re-injection）；改主意用 `SUPERSEDES`，旧决定标 `valid_to` 不删 | 一致性 | ❌ 缺 |
| **I6 确定性优先** | 能由规则/AST/表格/哈希判定的不用 LLM；LLM 只产生候选；`TypeA ⇒ TypeB` | 可信 | ✅ 已有（P3） |
| **I7 可演进不失稳** | TBox 动态但版本化、单一写入者、可回滚；新增不破坏既有 8 个测试与页面 | 可持续 | ✅ 已有（H11） |

**凝练成一句**：保证 **「事实不被编造、探索不被丢失、方向不被机器独占、每个决定可追溯且能重算」**。

### 1.3 与已总结 skills 的对照（八条元原则的继承与扩展）

`skills/APPLICATION_ONTOLOGY_FRAMEWORK.md` §1 的 P1–P8 是 v1 的来源。v2 的映射：

| SciForge 原则 | v2 对应 | 本轮补强 |
|---|---|---|
| P1 单一写入者 | I2 / I7 | 新增 `HumanDecision` 也是单一写入者（`hitl.py`），且 `CONSTRAINT_REINJECTION.json` 由它唯一生成 |
| P2 文献先于 idea | I6 | 新增「**人的方向也要有 gap_anchor 或显式 exploratory 理由**」，否则同样是空想 |
| P3 机械判定先于 LLM | I6 | 新增「**确定性派生视图先于任何 LLM 提案**」：先穷尽图里能挖的，再让模型补 |
| P4 一切锚定留痕 | I5 | 从「claim/idea 锚定」扩展到「**人的决定也锚定**」：`evidence_ids + run_id + approver + supersedes` |
| P5 判定靠 exit code | I6 | `ChoicePoint` 的 gate 也必须有 verdict 文件，不能靠前端按钮状态 |
| P6 降级不等于跳过 | I3 | **探索信号是这一条的正面版本**：网络失败降 WARN，词表外降 `other`——都不是丢弃 |
| P7 源码+输入+哈希 | I2 | 人的决定加入重算输入：`rebuild ≡ f(semantic, rules, decisions)` |
| P8 回退带预算且改状态 | I4 | 人换方向也是一种「有预算的回退」，走 `SUPERSEDES` 而非静默重写 |

> 特别注意 **P6 的正面用法**：SciForge 用 `other + proposed_new` 处理词表外类（见 `skills/04-shared-references/01-governance-and-output.md` 与 `domain-learner.md`），项目里 `semantic/extraction/vocab.py` 已经实现了同样的机制（`observe()` / `PROMOTE_AFTER` / `promote()` / `stats()`）。v1 完全没有把它接进 `paperapp`——这是最可惜的一处遗漏。

---

## 2. 问题一：是否需要在原有语义层挖掘更多东西

### 2.1 结论

> **不在语义层加任何类，但要补「确定性派生视图」与「覆盖率雷达」两件事。**

理由：`semantic/tbox_v4.py` 的设计文档已经把删类/降属性的理由写得很清楚（v3.2 的 46 类/105 关系 → v4.1 的 6 类/9 关系，把派生类全部下沉为属性或应用层节点）。加回第 7 类会同时破坏 H3 与 `reprospec` 的领域口径。语义层该做的是**把已有字段的可挖掘性用尽**，而不是扩张本体。

### 2.2 现状：`applayer/miner.py` 只做了「字段提升」

实测 8 个挖掘器全部是「读一个字段 → 建一个节点 → 连一条边」：

| miner | 输入 | 输出 |
|---|---|---|
| `questions / categories / metrics` | `Paper.research_question` / `problem_category` / `Benchmark.metrics[]` | `ResearchQuestion` / `ProblemCategory` / `MetricDefinition` |
| `leaderboard / contracts / evidence` | `Benchmark.model_results[]` / 契约字段 | `LeaderboardEntry` / `DataContract` / `Evidence` |
| `limitations / source_papers` | `Algorithm.limitations` / `Paper--RELATED_TO-->Paper` | `Limitation` / `SourcePaper` |

**没有一个做跨节点结构推导**。也就是说：语义图里明明有 7460 条断言，但应用层只用了「节点属性」这一维。

### 2.3 补 4 个确定性派生挖掘器（全部写应用层，不改语义层）

| # | miner | 从什么推导 | 产出节点 | 复用现有代码 |
|---:|---|---|---|---|
| D1 | `flow_closure` | `AlgorithmModule.inputs/outputs` 词元交集 → 直接前驱压缩 → 环检测 | `ModuleFlowEdge` / `CyclicFeedback` | `reprospec/compiler.py` 的 `_as_list()` / `_find_cycle_edges()` 思路（**沉淀到 app 层，不再只在 run 时算**） |
| D2 | `method_benchmark_matrix` | `Algorithm × Benchmark` 共现矩阵 → 空格检测 | `ResearchGap` 候选（`kind="structural_blank"`）、`MethodFamily` | `applayer/miner.py` 的 `add/rel` 模式 |
| D3 | `lineage_slice` | `Paper--RELATED_TO-->Paper` + `year` 切片 + 被引/年份 | `FrontierNode`（solved/unsolved） | `reprospec/probe.py` 的 lineage 分级、`SourcePaper` miner |
| D4 | `capability_cooccurrence` | `CodeFunction` 同文件/调用共现 + AST 符号 + `verification.passed` | `Capability` 成熟度、`Evidence` 增强 | `research/gaps.py::CoverageAnalyzer` 的 `maturity` 维度 |

**硬规则**：4 个派生挖掘器都是 `NON_LLM`、幂等、可重算；输入只来自语义图；输出只写 `app_generation.json`；每个产出带 `derived_from` + `miner` + `provenance="deterministic"`。

### 2.4 覆盖率雷达 `MINING_COVERAGE.json`（回答「还有多少没挖」）

项目里**已经有** `research/gaps.py::CoverageAnalyzer`：用 `relevance × (0.35 + 0.65×maturity)` 判 `covered / partial / gap`，阈值 `0.52 / 0.32`，并且明确「缺口不展示最相近能力，避免误导」。v2 直接复用它，但把「需求」换成「语义层可挖掘面」：

```json
{"semantic_version":"v4.1-semantic",
 "fields":[{"name":"Paper.flow_family","consumed_by":["categories"],"status":"covered"},
           {"name":"AlgorithmModule.formula","consumed_by":[],"status":"gap"},
           {"name":"Paper.why_hard","consumed_by":[],"status":"partial"}],
 "assertions":[{"relation":"MODULE_IMPLEMENTED_BY","consumed_by":["D4"],"status":"covered"}],
 "miners":[{"name":"D2","status":"covered","n_outputs":37}],
 "coverage_ratio":0.61,
 "gap_candidates":[{"id":"sig:...","reason":"字段从未被任何挖掘器消费"}]}
```

`status=gap` 的每一项**自动生成一个 `KnowledgeSignal`**（见 §3），成为下一轮探索的候选输入，而不是只写一份报告。

> 这直接回答用户的疑问：**需要挖更多，但挖的是「结构」与「覆盖盲区」，不是加语义层类**。

---

## 3. 问题二：如何保证探索过程中增加和捕捉新知识点

### 3.1 核心原则：**捕捉 ≠ 晋升**

v1 的隐含假设是「一个东西只有变成 registered 节点才算被系统学到」。这会导致两个坏结果：① 为了不丢东西而放宽晋升门；② 门一严，探索信号全丢。

v2 把它拆开：

| | 捕捉 | 晋升 |
|---|---|---|
| 覆盖率 | **100%（硬门）** | 可控（0.2–0.6） |
| 存放 | `KnowledgeSignal`（append-only） | `DynamicClassRegistration` / `NodeCacheEntry` |
| 需要证据 | 不需要，只要「发生了」 | 需要 NON_LLM / 规则 / 人批准 |
| 失败后果 | **H12 硬门失败** | 只是保持 `proposed` |

### 3.2 四层捕捉漏斗

```
[L0] 零成本信号  KnowledgeSignal  ← 复用 vocab.observe() / PROMOTE_AFTER
      来源：词表外 proposed_new / "other"、recognize_entities 候选、
            align 未命中、门 FAIL、unknown 表单、MINING_COVERAGE.status=gap、
            未探索 gap、CoverageAnalyzer 判定 gap、人提出的方向未被采纳
      ↓ frequency >= PROMOTE_AFTER(项目现值) → 词表扩表（复用 vocab.promote()）
[L1] 提案  LLMNodeProposal（S1 已有四态）
      ↓ 对齐 + 验证
[L2] 注册  DynamicClassRegistration / NodeCacheEntry（S0/S1 已有）
      新类/新关系必须人批准；跨 run use_count >= 3
[L3] 经验  Lesson / ExplorationFrontier / RUN_PREPRINT（S3/S4 已有）
      失败、回滚、未尝试方向也算知识点
```

**L0 是 v2 新增的关键层**。它把「没被采纳的东西」变成一等节点：

```json
{"signal_id":"sig:000421","kind":"vocab_out_of_list",
 "stage":"1b","paper_id":"paper:2411.06608","run_id":"run:...",
 "value":"scaffold-split 条件生成","source":"vocab.proposed_new",
 "evidence_ids":[],"count":2,"first_seen":"...","last_seen":"...",
 "status":"observed|clustered|promoted_to_proposal|dismissed",
 "promoted_to":"prop:000123","dismiss_reason":""}
```

`status=dismissed` 也必须写 `dismiss_reason` —— **不删除、不静默**。

### 3.3 复用 `vocab.py` 的现成装置（不要另造）

实测 `src/capfactory/semantic/extraction/vocab.py`：

- `render()` 注入 prompt 时明写「若确实出现词表外的新类，输出 `other` 并在 `proposed_new` 里写出建议的新类名，**系统会自动收集并扩充词表，不要静默丢弃**」；
- `observe()` 累计候选，`count >= PROMOTE_AFTER` 自动 `promoted`；
- `promote(name, value)` 手动晋升；`stats()` 给出 `sizes / promoted / candidates`。

v2 的做法：**`paperapp/signals.py` 作为 `vocab.py` 的消费者与统一出口**，把 `candidates` 里每一项镜像成 `KnowledgeSignal`，并把 `stage / paper_id / run_id` 补上（vocab 本身没有这些维度）。这样不改 `vocab.py` 的既有行为，也不破坏 E0–E6 抽取链。

### 3.4 新增本体类与关系

| 类 | 关键字段 | 关系 |
|---|---|---|
| `KnowledgeSignal` | `signal_id, kind, stage, paper_id, run_id, value, source, count, status, promoted_to, dismiss_reason` | `AGGREGATES_TO → SignalCluster`；`PROMOTED_TO → LLMNodeProposal`；`FROM → MiningCoverage` |
| `SignalCluster` | `cluster_id, members[], frequency, representative` | `TRIGGERS → VocabPromotion / ClassRegistrationProposal` |
| `MiningCoverage` | `coverage_ratio, fields[], assertions[], gap_candidates[]` | `EMITS → KnowledgeSignal` |
| `ExplorationFrontier` | `direction, rationale, status(untried|tried|failed|absorbed), source(human|signal|gap)` | `SUGGESTED_BY → HumanIntent / ResearchGap`；`TRIED_IN → run_id` |

### 3.5 新增护栏与指标

| 项 | 定义 |
|---|---|
| `signal_capture_rate` | 产生的信号数 / 应产生信号的事件数（词表外、未对齐、门 FAIL、gap）= **100%（H12）** |
| `signal_to_proposal_rate` | 晋升为提案的信号 / 总信号（观察值，不设目标，异常高说明门松） |
| `exploration_regret` | 连续 N 个 run 无新增 `ExplorationFrontier` 且预算只花 <50% → WARN（budget-underuse 的探索版） |
| `dismiss_with_reason` | 100%（任何 dismissed 都有理由） |

---

## 4. 问题三：怎么在各环节增加「可选择的人类思路」并真正并入

### 4.1 核心转向

> v1：人是**门卫**（approve / reject / 签字）
> v2：人是**一等参与者**，其思路作为图节点进入 DAG，与机器候选一起被评估、被约束再注入、被回放、被反思

这需要三层东西：**建模**（节点/关系）、**传播**（Constraint Re-injection）、**界面**（ChoicePoint UI）。

### 4.2 六个新本体类 + 关系词表

| 类 | 关键字段 |
|---|---|
| `HumanIntent` | `intent_id, statement, scope(global|run|stage), constraints[], created_by, ts` |
| `HumanHypothesis` | `hypothesis_id, statement, falsifiable_claim, mechanism, boundary, gap_anchor, origin="human"` |
| `MethodAlternative` | `alternative_id, name, rationale, cost, risk, evidence_ids, origin="human|machine"` |
| `ChoicePoint` | `choice_id, stage, mode(advisory|option|gate), options[], default_option, deadline, status, verdict_file` |
| `HumanDecision` | `decision_id, choice_id, chosen_option_id, approver, ts, evidence_ids, reason, supersedes, valid_from/to` |
| `HumanOverride` | `override_id, target_node, field, old_value, new_value, approver, ts, reason` |

| 关系 | 语义 |
|---|---|
| `SUGGESTS` | `HumanIntent → HumanHypothesis / MethodAlternative / ExplorationFrontier` |
| `CHOOSES / REJECTS` | `HumanDecision → options` |
| `CONSTRAINS` | `HumanDecision → Stage / PaperSpec / miner` |
| `OVERRIDES` | `HumanOverride → 节点字段` |
| `APPROVES` | `HumanDecision → PromotionRecord / KillArgument` |
| `SUPERSEDES` | 新 `HumanDecision → 旧 HumanDecision` |
| `REINJECTS` | `HumanDecision → CONSTRAINT_REINJECTION.json → 后续每阶段` |

### 4.3 三种介入模式（明确区分，不能混）

| 模式 | 是否阻断 | 超时行为 | 适用 |
|---|---|---|---|
| `advisory` | 否，只注入 prompt / prior | 继续 | 自由文本方向、风格偏好、约束备注 |
| `option` | 否，机器有默认值，人可改 | 采用默认并记 `auto_default` | 权重、route、figure archetype、paper mode、claim 强度 |
| `gate` | **是** | **BLOCKED，绝不自动通过** | 最终 idea、方法注册表、KILL、kill argument、类/关系到语义层晋升 |

> 对齐 SciForge 的 forced human checkpoints（Phase 3→4、5→6、KILL 默认 ON），并保留 `human_skip`（生产级委托，写 `APPROVAL_LOG.txt`）与 `test_mode`（压力测试，事后必须人确认）的区分。**人不能批准 LLM 节点进语义层**——这是 I1，不因身份而豁免。

### 4.4 ChoicePoint 清单（26 阶段中的 14 个）

| 阶段 | ChoicePoint | 模式 | 可选项示例 |
|---|---|---|---|
| 1b | 领域范式 / evidence_norm | `option` | formal / empirical / interpretive / design；≥N seeds、是否强制 CI |
| 4broad | 检索方向 + gap 优先级 | `option` | 方法族 / 数据集 / 年份切片；5 类 gap_type 权重 |
| **2** | **idea 候选池与 4 视角权重** | `option` + 可注入 `HumanHypothesis` | 人给一句可证伪假设 → 作为额外 root 进 MCTS |
| 2.5 | 攻击向量选择 | `option` | 领域失败模式 / 数值反例 / 文献反例 |
| **3** | **最终 idea 选定** | **`gate`** | 1–3 survivor，agent 不能自选 |
| 4targeted | 定向检索种子 | `advisory` | 补充关键词 / 指定必查工作 |
| **5** | **方法注册表 / 方法尝试** | **`gate`** + `MethodAlternative` | 人指定换用某个方法族、改损失、改采样 |
| 6 | 验证路线 | `option` | experiment-first / theory-only / hybrid |
| **6b** | **KILL / PIVOT** | **`gate`** | 换方法（PIVOT ≤2）或换 idea（KILL） |
| 10 | claim 强度 / 阴性结果去向 | `option` | symbolic/numerical/qualitative；Limitations vs regime-limited |
| 11 | figure archetype / Figure Budget | `option` | schematic-led / quantitative-grid；删哪个 panel |
| 12 | paper mode / 章节集 | `option` | 5 模式选择器 |
| **14** | **kill argument 是否成立** | **`gate`** | 成立 → BA 回 Phase 2 |
| 15.5 | publishability 判定 | `option` | 主逻辑轴权重、是否补实验 |

### 4.5 「并入」的五步机制（本轮最关键的设计）

```
1. 注入   HumanHypothesis / MethodAlternative 写入 node_cache（origin=human）
         → 进入 idea DAG 作为额外 root/branch，参与 MCTS 六轴与 4 轮打分
         → 与机器候选同权重；若设 human_boost 必须有上限且留痕、可关闭
         → 同样必须满足 gap_anchor 或显式 exploratory 理由（P2 不因人或机器而豁免）

2. 选择   ChoicePoint 产生 HumanDecision（append-only）
         字段：approver / ts / evidence_ids / reason / supersedes / valid_from-to
         同时写 6 态 verdict 文件（P5：不能只靠前端按钮状态）

3. 传播   生成 CONSTRAINT_REINJECTION.json：
         {"decisions":[{decision_id, verbatim_text, applies_to_stages:[...],
                        constraints:{...}}], "spec_hash_input": true}
         → 后续每个边界逐字复述（复用 SciForge Constraint Re-injection）
         → 作为 compile_paperspec() 的输入，人的决定改变 spec_hash（I2：可重算）
         → 前端 T3/T7 显示「本阶段受哪些人类决定约束」

4. 失败   人选择的方向若失败，不静默丢弃：
         → LESSONS.json 新增 human_hypothesis_rollbacks（带 evidence + lesson）
         → 成为下次 REPLAY_CONTEXT 的 avoid 或 exploration_seed
         → ExplorationFrontier.status = failed → 可重新 untried（人可重启）

5. 改主意 新 HumanDecision.SUPERSEDES 旧决定；旧决定标 valid_to，不删除
         → 所有受影响阶段标 stale，走 S4 的最小重算（dependency_index 增加
           decision_id → 受影响节点 的反向键）
```

### 4.6 前端：第 7 个 tab「人工决策」

| 区域 | 展示 |
|---|---|
| 待办 | 所有 `status=pending` 的 ChoicePoint，按 `gate > option > advisory` 排序，gate 红色 |
| 选项卡 | 每个 option 显示 `rationale / cost / risk / evidence / suggested_by`，可对比 |
| 方向输入 | 自由文本 → 生成 `HumanHypothesis`，要求填 `falsifiable_claim` 与 `gap_anchor`（否则禁提交） |
| 方法尝试 | `MethodAlternative` 表单，展示它注入了 idea DAG 的哪个分支、MCTS 得分 |
| 决策历史 | append-only 列表，灰行显示被 `SUPERSEDES` 的旧决定与 `valid_to` |
| 约束再注入 | 展示 `CONSTRAINT_REINJECTION.json` 与「哪些阶段正在受它约束」 |
| 失败反思 | `human_hypothesis_rollbacks` 与对应 `ExplorationFrontier` 状态 |

交互红线：`gate` 超时**不能**显示「已自动通过」；`human_skip` 必须填 `approver` 且写 `APPROVAL_LOG`；任何人不可以通过 UI 把 LLM 提案晋升进语义层（该入口不存在）。

---

## 5. v2 目标架构（五层 → 七层）

```
L0  语义层（冻结，6 类/9 关系，NON_LLM）                     [I1]
      │
L1  任务派生层 app_generation.json
      ├─ 原有 8 挖掘器（字段提升）
      └─ 【新】D1–D4 确定性派生视图 + MINING_COVERAGE.json     [I6/G4]
      │
L1.5 【新】探索信号层 KnowledgeSignal / SignalCluster         [I3]
      │   ← vocab.observe() / 对齐未命中 / 门 FAIL / 覆盖 gap / 人未采纳方向
      ↓ frequency → 词表扩表 / 提案
L2  提案缓存层（S1 四态，proposed→validated→registered→deprecated）
      │
L2.5 【新】人类决策层 ChoicePoint / HumanDecision / REINJECTION [I4/I5]
      │   ← 与 L2 双向：人的思路进提案池，提案可请求人裁决
      ↓
L3  规格层 PaperSpec（spec_hash 包含 semantic + rules + decisions） [I2]
      ↓
L4  运行时 + 证据层（run_id 隔离 / events.ndjson / LESSONS）
      ↺ 回写 L1 / L1.5 / L2.5（append-only，可重算）
```

**写入权限矩阵新增 2 行**：

| 生产者 | 允许写 | 禁止写 |
|---|---|---|
| `paperapp/signals.py` | `node_cache/signals/**`、`SIGNAL_LOG.jsonl`、只读 `vocab.json` | 语义层、应用图 |
| `paperapp/hitl.py` | `dynamic_tbox/decisions/**`、`DECISION_LOG.jsonl`、`CONSTRAINT_REINJECTION.json` | 语义层、应用图（节点仍由 S4 materialize 统一写） |

---

## 6. v1 → v2 的关键取舍（明确不做什么）

| 不做 | 为什么 |
|---|---|
| 给语义层加第 7 类 | 破坏 H3 与 v4.1 降属性设计；结构知识应派生到应用层 |
| 让人的方向绕过 `gap_anchor` / 六轴 / MCTS | 否则「人的偏好」变成无法证伪的空想，破坏 P2/P3 |
| 用 `human_boost` 让人选方向必胜 | 会让人误以为系统验证了它；boost 必须有上限、可关闭、留痕 |
| 把 `gate` 超时自动通过 | 破坏 I4；超时只能 BLOCKED |
| 人批准 LLM 提案进语义层 | I1 不因身份豁免 |
| 删除被拒/被 supersede 的决定或信号 | 破坏 I3/I5；只标 `valid_to` + `dismiss_reason` |
| 另造一套词表扩表机制 | 复用 `vocab.py` 的 `observe/promote/PROMOTE_AFTER/stats` |
| 另造一套覆盖度分析 | 复用 `research/gaps.py::CoverageAnalyzer` 与 `NeedCoverage` 三态 |
| 打乱 S0–S6 阶段编号与 126 项测试编号 | v2 以 `T-V2-xx` 追加，见 `plan/V2_DELTA.md` |

---

## 7. 优化后要实现的点（优先级）

| P | 优化点 | 落在阶段 | 对应不变量 |
|---:|---|---|---|
| 0 | `signals.py` + `hitl.py` 骨架、6 个新本体类注册、`ChoicePoint` schema | S0 | I3/I4 |
| 1 | `vocab.observe()` → `KnowledgeSignal` 桥接；信号聚类与频率晋升 | S1 | I3 |
| 2 | D1–D4 确定性派生挖掘器 + `MINING_COVERAGE.json` | S2 | I6/G4 |
| 3 | `compile_paperspec()` 消费 `HumanDecision`，决定进入 `spec_hash` | S2 | I2/I5 |
| 4 | `HumanHypothesis` / `MethodAlternative` 注入 idea DAG，同权重 MCTS | S2/S3 | I4 |
| 5 | 26 阶段挂 14 个 ChoicePoint；`gate` 超时 BLOCKED | S3 | I4 |
| 6 | `CONSTRAINT_REINJECTION.json` 每边界逐字复述 | S3 | I5 |
| 7 | 人方向失败 → `LESSONS.human_hypothesis_rollbacks` → `REPLAY_CONTEXT` | S3/S4 | I3 |
| 8 | `SUPERSEDES` 触发最小重算（decision 反查索引） | S4 | I5/I2 |
| 9 | 第 7 个前端 tab「人工决策」+ 决策历史/约束再注入视图 | S5 | I4/I5 |
| 10 | 新硬门 H12–H16、演练 F9–F12、4 项新指标 | S6 | 全部 |

> 完整的逐阶段增量、新硬门、24 项新测试、新指标与验收，见 [`plan/V2_DELTA.md`](plan/V2_DELTA.md)。

---

## 8. 与既有文档的关系

| 文档 | 关系 |
|---|---|
| [`SCIFORGE_INTEGRATION_BLUEPRINT.md`](SCIFORGE_INTEGRATION_BLUEPRINT.md) | v2 保留其五层骨架与 26 阶段映射，扩为七层；§4 写入权限矩阵增加 2 行 |
| [`DYNAMIC_ONTOLOGY_NODE_CACHE.md`](DYNAMIC_ONTOLOGY_NODE_CACHE.md) | v2 在其 L2 之前插入 L0 信号层，并把 `HumanDecision` 加入 `cache_identity` 的可重算输入 |
| [`plan/README.md`](plan/README.md) + S0–S6 | 阶段编号与 126 项测试编号**不变**，以 `V2_DELTA.md` 增量修订 |
| [`plan/TEST_PLAN.md`](plan/TEST_PLAN.md) | 追加 `T-V2-01..24`，累计 150 项 |
| [`skills/APPLICATION_ONTOLOGY_FRAMEWORK.md`](skills/APPLICATION_ONTOLOGY_FRAMEWORK.md) | P1–P8 被 I1–I7 继承并补强（§1.3 对照表） |
| `src/capfactory/semantic/extraction/vocab.py` | **只读复用**，不改行为 |
| `src/capfactory/research/gaps.py` | **只读复用** `CoverageAnalyzer` |
| `src/capfactory/applayer/miner.py` | 追加 4 个确定性 miner，不改既有 8 个 |
