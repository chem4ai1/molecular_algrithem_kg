# SciForge 论文生成方案落地蓝图：语义层抽取 + 动态应用层本体 + LLM 新节点缓存

> 版本 1.0 · 2026-11-15
> 适用仓库：`/home/zengshuxin/molecular_algrithem_design`
> 输入材料：本目录 4 份既有设计 md、`docs/skills/` 24 份解析与框架文档、`src/capfactory/` 全部 schema/抽取/应用/复现代码、`storage/sciforge/` 全量图产物，以及 4 组外部调研。
> 配套文档：[DYNAMIC_ONTOLOGY_NODE_CACHE.md](DYNAMIC_ONTOLOGY_NODE_CACHE.md)（缓存与增量节点的完整设计）

---

## 0. 执行摘要：先给结论

### 0.1 三条最重要的建议

1. **不要把 SciForge 的 26 个 skill 搬成 26 个 Python 模块。** 它们是给 LLM 的散文契约，而你已有的 `semantic/extraction/contracts.py::E_CONTRACTS` + `applayer/miner.py` 的确定性挖掘器 + `reprospec/compiler.py` 的零 LLM 编译，是**更强**的实现。正确做法是把 26 个阶段**映射成应用层节点类与门**，用图编译代替 prompt 编排。
2. **LLM 创建的节点绝不直接写 `batch10_semantic_v4.json`。** 语义层 6 类/9 关系是客观事实层，基础契约由既有回归锁定（`reprospec/application.py` 头部注明）；`RUBRIC_TREE_LAYER.md` 已经验证过「语义层 6 类一个都不动」是可行的。新增节点一律先进**提案缓存层**，经过对齐、验证、复用计数、晋升规则后才允许成为正式应用层节点；晋升到语义层需要 NON_LLM 证据与人工批准。
3. **缓存不是「把 LLM 输出存起来」这么简单，要拆成三层**：L1 请求级幂等缓存（同输入不重跑）、L2 节点提案缓存（LLM 生成的新节点候选 + 证据 + 指纹）、L3 动态类注册中心（已晋升的类/实例 + 版本 + 使用计数 + 失效时间）。项目里已有可复用的三态契约 `ontology/metrics.py::align_metric_name()` 的 `reuse | registered | proposal`，应把它扩展成四态生命周期而不是另起炉灶。

### 0.2 目标架构（一句话）

```
语义层（冻结，客观事实）
  → build_task_layer("generation") 复制 + 确定性挖掘
  → 任务派生层 app_generation.json（可扩展动态类）
  ⇄ 动态提案缓存层【新增】LLM 新节点在这里四态流转
  → 规格层 ReproSpec / PaperSpec（零 LLM 编译）
  → 运行时层（按 run_id 隔离）
  → 证据层（run 工作区 + events.ndjson）
  ↺ 跨 run 回写：Lesson / PromotionLog / 复用计数
```

### 0.3 一句话回答「按照这个步骤进行完增加的新节点的方式」

每次 run 结束后，`paperapp/materialize.py` 汇总本轮 LLM 产出的候选节点 → 走 `align → validate → register` → 写入 `storage/sciforge/node_cache/` 与 `dynamic_tbox/registry.json` → **只把 `status=registered` 的节点增量合并进 `app_generation.json`**，同时把 `Lesson`、`use_count`、`supersedes` 写回缓存。下次 run 启动时先按 `cache_key` 命中，命中即 `reuse`，不再调 LLM；语义层图永远不变。

---

## 1. 现状诊断（全部来自实测代码，不是推测）

### 1.1 三层 TBox 与图产物

| 层 | 定义处 | 契约 | 实测产物 |
|---|---|---|---|
| 语义层 v4.1 | `semantic/tbox_v4.py` | **6 类 / 9 关系**（`Paper / Algorithm / AlgorithmModule / CodeRepository / CodeFunction / Benchmark`），`REMOVED_CLASS_MAP` 明确「被删类 → 语义层落点 / 应用层承接」 | `storage_cf/sciforge/batch10_semantic_v4.json`：6001 节点 / 7460 断言 |
| 任务派生层 | `applayer/tbox.py`、`applayer/tasks.py` | **8 类 / 9 关系**；`TASK_SPECS` 有 `reproduction` 与 **`generation`** 两个任务 | `app_reproduction.json` 8300 节点 / 10260 断言；`app_generation.json` 8853 节点 |
| 运行时层 | `reprospec/application.py` | 9 类（含 `RubricNode`）/ 4 关系，`run_id` 命名空间隔离 | `<run>/app_repro_runtime.json` |
| legacy 判定入口 | `ontology/tbox.py` | `TBOX_VERSION="v3.2-105"`，102 权威关系 + 30 reserved 类 + 87 reserved 关系 | 仅规则，不存数据 |

**关键发现**：`generation` TaskSpec **已经存在**（7 类 / 7 关系：`ResearchQuestion / ProblemCategory / MetricDefinition / DataContract / Evidence / Limitation / SourcePaper`），`app_generation.json` 已有 783 个 `ResearchQuestion` + 17 个 `ProblemCategory`。所以「论文生成」不是从零开始，而是**扩展这个已有任务**。

### 1.2 写入权限矩阵（`APPLICATION_LAYER_DESIGN.md` §2，必须继续遵守）

> 「只有 `semantic/` 和 `applayer/` 能写图；其余模块只写 run 目录。」

| 生产者 | 允许写 | 禁止写 |
|---|---|---|
| `semantic/` 抽取与回填 | `batch10_semantic_v4.json` | 任何 app/run 文件 |
| `applayer/build_task_layer` | `app_<task>.json` | 语义层、run 工作区 |
| `compile_reprospec` | 只返回对象 / `REPRO_SPEC.json` | 图 |
| `reprospec/application` | `app_repro_runtime.json` | `app_reproduction.json` |
| `executor` / `runner` | run 目录产物 | 图 |

**本方案新增的写入口只有两个**：`paperapp/materialize.py` 可增量写 `app_generation.json`（须经 `build_task_layer` 的同一把锁），`paperapp/nodecache.py` 只写 `storage/sciforge/node_cache/` 与 `dynamic_tbox/`。

### 1.3 数据结构已有的「溯源基因」

`po/store.py`：

```python
Assertion(id, source, target, relation,
          attribution="analyst_synthesis", evidence_ids=[], properties={})
Concept  (id, type, label, attrs, attribution, evidence_ids,
          source_version, missing_states)
```

`Assertion` 是 RDF reification 在属性图里的落地，**「分析者关联」不会被误读成「作者声明」** —— 这正是 LLM 生成节点最需要的隔离机制：`attribution="llm_proposal"` 天然可区分。

其它可复用资产：

| 资产 | 位置 | 用途 |
|---|---|---|
| 三态动作 `reuse / registered / proposal` | `ontology/metrics.py::align_metric_name()` L130-163 | **LLM 新节点注册范式的现成模板** |
| 受控词表 `default_registry` / `register_metric()` | `po/vocab.py`、`ontology/metrics.py` | 新类/新关系的封闭词表判定 |
| `E_CONTRACTS` + `NON_LLM` | `semantic/extraction/contracts.py` | 「LLM 只能抽什么」的契约约束 |
| `Capability(version, maturity, lessons, provenance, verification, artifact_ids)` / `Evidence(source_id, quote, locator)` / `Lesson` | `schema/capability.py` | 动态节点的成熟度、经验回放、溯源记录 |
| 5 级证据优先级 | `semantic/provenance.py` L3-8 | 提案验证的证据排序 |
| `relations.resolve_relation()` / 历史别名 | `reprospec/relations.py` | 关系名归一，历史别名只解析不回写 |
| `ClaimAnchor` 三哈希 / `events.ndjson` | `reprospec/scoring.py`、`sciforge/repro/state.py` | LLM 输出的六哈希锚定与 durable truth |
| `RubricTree` | `reprospec/rubric_tree.py` | 失败分支只重判子树 → 缓存失效的最小粒度 |
| 缓存先例 | `ingest/arxiv.py`（查询缓存）、`web/home_api.py`（cached/live/auto）、`web/data_api.py`（stamp 缓存） | 幂等键与模式开关的既有写法 |
| **6 态 verdict（已存在）** | `sciforge/contracts.py::VERDICT_STATES = (PASS, WARN, FAIL, NOT_APPLICABLE, BLOCKED, ERROR)` + `validate_verdict()`，`sciforge/__init__.py` 已导出 | 26 阶段门控**直接复用**，无需引入外部校验脚本 |
| 软链与解释器 | `storage_cf -> storage`；`python3`（`/home/zengshuxin/anaconda3/bin/python3`）；`tests/` 现有 8 个测试文件 | 方案中所有 `python3` / `storage_cf` 写法以此为准 |

### 1.4 现状缺口（本方案要补的）

| 缺口 | 证据 |
|---|---|
| `generation` 任务只有 7 类节点，SciForge 26 阶段的选题/前沿/图/评审等产物**无处落地** | `applayer/tasks.py::TASK_SPECS["generation"]` |
| 没有「LLM 生成节点」的统一记录结构、没有跨 run 复用计数、没有失效机制 | grep `cache\|llm_node\|reuse` 只命中 web/arxiv 的请求级缓存 |
| 应用层类集合是**静态 tuple**，新增类必须改源码并重跑全量 `build_task_layer` | `applayer/tbox.py`、`tasks.py` |
| 每次 `build_task_layer` 全量重建 8853 节点，无增量合并入口 | `applayer/builder.py` |
| LLM 输出与图节点之间缺 `prompt_hash / model_id / input_sha / output_sha` 的绑定 | `E_CONTRACTS` 只约束字段，不约束输出溯源 |

---

## 2. 调研结论

### 2.1 内部调研（已解析的 24 份文档）

| 来源 | 可迁移的机制 |
|---|---|
| `docs/skills/APPLICATION_ONTOLOGY_FRAMEWORK.md` | 5 命名空间约 70 个本体类、25 条 canonical 关系、26 节点 DAG、L1–L13 回退 |
| `05-orchestrator/auto-pipeline-guide.md` | 每边界 5 件事、6 态 verdict、`RUNSTATE` 恢复、budget-underuse 护栏 |
| `04-shared-references/01-governance-and-output.md` | 权威顺序、单一写入者、双写 + MANIFEST append-only、pointer-load |
| `04-shared-references/03-ideation-and-evaluation.md` | S2 ladder / ablation / `LESSONS.json` 经验回放 |
| `04-shared-references/schemas-guide.md` | 22 个 verdict schema、跨字段后检、`na_verdicts` 合法缺失声明 |
| `01-domain-ideation/domain-learner.md` | `DomainProfile / EvidenceNormProfile` 是动态本体的典型「运行中习得的配置节点」 |
| `06-support-skills/` 5 份 | 19 个阶段执行者的输入/输出/门，用于设计阶段产物节点 |

### 2.2 外部调研（4 组，2025–2026）

| 方向 | 结论 | 对本方案的取舍 |
|---|---|---|
| **MGraph-DB / 演化语义图** | file-backed、schema-aware 的 JSON 快照可进 Git diff，本体演化有完整历史 | 采用「`registry.json` + append-only `PROMOTION_LOG.jsonl` + 快照版本」，但**不引入外部图数据库**，继续用 `POGraph` + JSON |
| **Graphiti / Zep（arXiv:2501.13956）** | 三层子图（episode → semantic → community）；**双时间模型** `valid_from / invalid_at`；episode 是溯源码头；边失效而非堆积 | 采用 `episode`→本项目的 `run_id + events.ndjson`，采用 bi-temporal 字段，采用「标 deprecated 而非删除」 |
| **LLM-KGC 综述（arXiv:2510.20345）/ Wikontic / ODKE+ / KARMA** | 三阶段演进：本体驱动一致性 → 数据驱动统一 → schema 与实例联合对齐；实体对齐/冲突消解/模式协调是核心 | 采用「受控词表优先 + LLM 只做 proposal + 确定性对齐」，不让 LLM 自由扩展 TBox |
| **Semantic Caching with VecDBs / GraphRAG 增量** | ANN 相似阈值复用 LLM 输出可显著降本；企业 GraphRAG 组合图检索 + 语义缓存 + 溯源 | L1 用向量近邻做**幂等重放**，但**禁止跨论文用相似度复用事实节点**（会串味）；阈值与任务类别绑定 |
| **Self-Organizing Knowledge Networks（arXiv:2502.13025）/ Semantica** | agentic graph expansion、graph-native provenance | 只借鉴「新节点必须带 provenance 才能入图」，不采用自组织扩张（会破坏确定性溯源） |

> **一条贯穿判断**：这些工作的共同点是「让本体能动起来」，但你的项目优势恰好是**确定性 + 可溯源 + 783 篇全量**。因此动态性只能放在**应用层与缓存层**，语义层保持冻结 —— 这与 `RUBRIC_TREE_LAYER.md` §2「树属于 reproduction 任务层，语义层只提供骨架」是同一决策。

---

## 3. 核心判断：SciForge 该怎么「做到项目里」

| 维度 | SciForge-OSS | 本项目 | 落地方式 |
|---|---|---|---|
| 编排 | `auto-pipeline/SKILL.md` 26 节点，散文调度 | `sciforge/repro/phasegraph.json` R0–R6 + `runner.py` 门控 | 扩展成 `paperapp/phasegraph.json` 26 节点，但每个节点的「执行」是**图编译 + 确定性门**，不是 prompt |
| 阶段产物 | `.md` / `.json` 文件 | `POGraph` 节点 + `Assertion` | 每个阶段产物映射成**应用层节点类**，`derived_from` 指向语义层锚点 |
| 领域配置 | `domain-signature.json` 单一写入者 | 无对应物 | 新增 `DomainProfile` 应用节点，同样单一写入者、`spec_hash` 锁定 |
| 判定 | `scripts/*.py` exit code | `sciforge/contracts.py::VERDICT_STATES` / `validate_verdict()` | 直接复用**项目已有**的 6 态 verdict |
| 新节点 | 无（skill 只写文件） | **本方案新增** | 四态提案缓存 + 动态类注册中心 |
| 跨 run 记忆 | `RUN_PREPRINT.md` + `LESSONS.json` | `schema/capability.py::Lesson` 已有结构 | 复用 `Lesson`，写 `use_count` 与 `supersedes` |

**明确不做**：不引入多智能体协作生成代码（会断溯源，`RUBRIC_TREE_LAYER.md` §8 已论证）；不把 26 个 SKILL.md 复制进仓库；不改语义层 6 类；不改 `applayer/tbox.py` 的 8/9 基础契约（既有全量回归锁定）。

---

## 4. 目标架构：五层 + 一个缓存闭环

```
┌──────────────────────────────────────────────────────────────────┐
│ L0 语义层  semantic/  6 类 / 9 关系  【冻结】                     │
│    batch10_semantic_v4.json  6001 / 7460                          │
│    NON_LLM 优先（AST / 表格 / 规则）；只读，不接受 llm_proposal   │
└───────────────────────────┬──────────────────────────────────────┘
                            │ build_task_layer("generation") 复制 + 挖掘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ L1 任务派生层  applayer/  app_generation.json                    │
│    静态 7 类（已有） + 动态注册类（新）                          │
│    可重算、幂等、随语义层重建；layer="application"                │
└───────────────────────────┬──────────────────────────────────────┘
                            │ ◀── 增量回写（只写 status=registered）
                            │
┌───────────────────────────┴──────────────────────────────────────┐
│ L2 动态提案缓存层【新增】paperapp/nodecache.py + registry.py      │
│   L1 请求级幂等缓存  L2 节点提案缓存  L3 动态类注册中心          │
│   四态：proposed → validated → registered → deprecated           │
│   bi-temporal：valid_from / valid_to / recorded_at                │
│   文件：storage/sciforge/{node_cache,dynamic_tbox}/               │
└───────────────────────────┬──────────────────────────────────────┘
                            │ compile_paperspec()  零 LLM 编译
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ L3 规格层  PaperSpec / ReproSpec（spec_hash 幂等）               │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 26 阶段门控执行
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ L4 运行时层 按 run_id 隔离  app_paper_runtime.json               │
│    + 证据层：events.ndjson / RUNSTATE / verdicts / LESSONS.json   │
└──────────────────────────────────────────────────────────────────┘
        │ 每次 run 结束：materialize() 回写 L2 → 增量合并 L1
        └───────────────────────────────────────────────────────────►
```

### 4.1 扩展后的写入权限矩阵

| 生产者 | 新增允许写 | 仍然禁止写 |
|---|---|---|
| `paperapp/nodecache.py` | `storage/sciforge/node_cache/**`、`dynamic_tbox/PROMOTION_LOG.jsonl` | 任何图文件 |
| `paperapp/registry.py` | `dynamic_tbox/registry.json` | 图 |
| `paperapp/materialize.py` | `app_generation.json`（**只能增量 append 已 registered 的节点**，须与 `build_task_layer` 共用文件锁与 `semantic_fingerprint`） | 语义层、其它 run 目录 |
| `paperapp/phasegraph.py` / `gates.py` | run 目录 | 图 |

> **硬约束**：`app_generation.json` 永远可由 `build_task_layer("generation")` 全量重建。增量回写只能是「重建结果的等价优化」，即 `rebuild(graph) ⊕ registered_nodes == incremental(graph)`，用 P0 阶段的等价性测试强制（见 §9 P0）。

---

## 5. SciForge 26 阶段 → 项目节点 / 产物映射表

> `TaskSpec["generation"]` 已有 7 类；下表 **N = 新建应用类**、**R = 复用既有类**、**F = 仅文件产物不进全量图**。

| # | 阶段 | 主产物 | 对应应用节点 | 语义层锚点（`derived_from`） | 门 / 复用代码 |
|---:|---|---|---|---|---|
| 0 | 冻结 Q-id / 预算 | `RUN_BUDGET.json` | **N** `ProblemAnchor` | `Paper` | `INV-G1` 内容哈希（复用 `invariant-check` 思路） |
| 1 | 问题分解 | `REP.json` | **N** `PhasePlan` | `Paper` | `rep_plan_present` |
| 1a | `domain-signature` hint | `domain-signature-hint.json` | **F**（只作 prior，不入图） | — | 单一写入者约束 |
| 1b | `domain-learner` | `domain-signature.json` | **N** `DomainProfile` + `EvidenceNormProfile` | `Paper` 集合 | `learning_confidence ≥ 0.7`；**单一写入者** |
| 4broad | 广搜 | `GAP_REPORT.md`、`references.bib` | **N** `ResearchGap` | `SourcePaper` / `RELATED_TO` | `gap_gate` 风格：gap-id + 引用 + 判别动词 |
| 2 | `idea-discovery` | `IDEA_DAG.json`、`FINAL_PROPOSAL.md` | **N** `IdeaNode` / `IdeaDAG` / `MCTSRound` | `Algorithm` / `AlgorithmModule` | 6 轴 BLOCKED、Type-A 零 LLM、TF-IDF > 0.78 硬拒 |
| 2.5 | 证伪 | `FALSIFICATION_RECORD.json` | **N** `FalsificationRecord` | `Algorithm` 假设 | 可证伪性机器门 |
| 2.5b | EG | `ENGINEERING_GROUNDING.md` | **N** `EGAssessment` | `CodeFunction` | ≥3 子维=0 淘汰 |
| 3 | `novelty-check` | `FRONTIER_MAP.json`、`differentiation.md` | **N** `FrontierNode` / `DeltaClaim` / `CollisionMatrix` | `SourcePaper` + `HAS_LIMITATION` / `REPLACES` | 复合分 ≥0.6、人工选定 |
| 4targeted | 定向检索 | `TARGETED_WAVE_LOG.md` | **R** `ResearchGap` 追加 | `SourcePaper` | 碰撞预检 |
| 5 | 方法注册表 | `METHOD_REGISTRY.md` + hash | **R** `MethodLock`（`reprospec/application.py`） | `AlgorithmModule` | §3 hash lock、人工审批 |
| 6 | 验证路由 | `VERIFICATION_ROUTING.json` | **N** `VerificationRoute` | `DomainProfile` | `na_verdicts` 合法缺失声明 |
| 6a | 理论推导 | `PROOF_AUDIT.json` | **R** `StaticCheck` | `AlgorithmModule` | SymPy 逐步验证 |
| 6b/6c | 实验 | `RESULT.json` / `S2_LADDER.json` | **R** `ExperimentNode` / `EvaluationResult` | `Benchmark` | `smoke_gate` / `s2_ladder` / `budget_floor` |
| 7–9 | 三类审计 | verdict JSON | **N** `GateVerdict`（6 态） | 各阶段节点 | `validate_verdict()` |
| 10 | `result-to-claim` | `CLAIMS_FROM_RESULTS.md`、`TDAL.json` | **R** `ClaimAnchor` + **N** `Claim` | `LeaderboardEntry` / `Evidence` | claim 强度 ≤ 证据；TDAL 四维 |
| 11 | `unified-plotting` | `output.pdf/svg`、`figure_audit.json` | **N** `FigureSpec` / `Figure` / `FigureBudget` | `DataContract` / `RESULT` | A1–A11、Figure Budget |
| 12 | `paper-writing` | `main.tex` + `sections/` | **N** `PaperSection` / `Caption` | `Claim` / `Figure` | leakage scrub、caption 纪律 |
| 13 | `paper-compile` | `main.pdf`、`COMPILE_REPORT.json` | **R** `CompileReport` | — | 零 warning 零 error |
| 14 | 评审 | `REVIEW_STATE.json`、`KILL_ARGUMENT.json` | **N** `ReviewRound` / `KillArgument` | `Claim` | 6.0 / 8.0 双阈值 |
| 15 | 引用终审 | `CITATION_AUDIT.json` | **N** `CitationAudit` | `SourcePaper` | DOI + 标题 token-overlap ≥0.8 |
| 15.5 | 可发表性 | `PUBLISHABILITY_SCORE.json` | **N** `PublishabilityScore` | `Claim` / `GateVerdict` | 主逻辑轴 + fairness |
| 16 | 归档 | `RUN_PREPRINT.md`、`LESSONS.json` | **R** `Lesson`（`schema/capability.py`） | 全 run | **跨 run 缓存的来源** |

**新增类数量控制**：P0 只注册 `DomainProfile / ResearchGap / IdeaNode / GateVerdict` 4 个；其余按 P1–P4 分批注册。**绝不一次性改 `applayer/tbox.py`**，全部通过动态注册中心声明（见 §6）。

---

## 6. 动态本体设计

### 6.1 静态 vs 动态的分界

| | 静态（冻结） | 动态（可演化） |
|---|---|---|
| 对象 | `SEMANTIC_CLASSES` 6 类 / 9 关系、`APP_CLASSES` 8 类 / 9 关系 | `generation` 任务的扩展类、扩展关系、LLM 提案节点 |
| 修改方式 | 只能改源码 + 全量回归 | `dynamic_tbox/registry.json` 注册，append-only |
| 版本 | `TBOX_VERSION`、`po_v1` | `DYNAMIC_TBOX_VERSION`（语义化，随注册递增） |
| 谁能写 | 人 / 代码评审 | `paperapp/registry.py`（规则）→ 人批准 |

> 不改 `applayer/tbox.py` 的原因与 `reprospec/application.py` 顶部注释完全一致：`reprospec/application.py` 头部注明 8/9 与 legacy 46/105 由回归锁定，直接改会让既有全量回归退化。采用**扩展声明 + 独立注册表**。

### 6.2 动态类注册项 `DynamicClassRegistration`

```json
{
  "registration_id": "dcls:0007",
  "name": "ResearchGap",
  "parent_class": "ResearchQuestion",
  "layer": "application",
  "task": "generation",
  "producer_stage": "4broad",
  "producers": ["paperapp.miners.gap_miner"],
  "consumers": ["idea_discovery", "novelty_check", "paper_writing"],
  "fields": ["gap_id", "gap_type", "statement", "evidence_ids", "priority"],
  "relation_bindings": ["SUPPORTED_BY", "ANCHORS"],
  "id_template": "appgap:<arxiv>:<slug>",
  "promotion_rule": "rule:gap_gate_pass AND evidence_count>=1",
  "status": "active",
  "tbox_version": "dyn-1.3.0",
  "first_seen": "2026-11-15T...",
  "use_count": 0,
  "evidence_ids": [],
  "supersedes": ""
}
```

**类注册与实例写入严格分离**：一个类必须先 `status=active` 才能写它的实例；否则实例只能停在 `proposed`。这样避免「LLM 顺手发明一个类并塞进全量图」。

### 6.3 关系注册

复用 `reprospec/relations.py` 的 `resolve_relation()` 思想：新增关系进 `dynamic_tbox/relations.json`，历史别名**只解析不回写**；`validate_phasegraph()` 风格的 `validate_dynamic_tbox()` 在每次启动时检查 domain/range 与 `relation_bindings` 一致性。

---

## 7. LLM 新节点缓存（摘要，完整设计见配套文档）

> 详见 [DYNAMIC_ONTOLOGY_NODE_CACHE.md](DYNAMIC_ONTOLOGY_NODE_CACHE.md)。这里给接入要点。

| 层 | 键 | 内容 | 命中后 |
|---|---|---|---|
| L1 请求级 | `request_key = sha256(stage, input_fp, tbox_version, prompt_version, model_id, effort)` | LLM 原始输出 + 六哈希 | `reuse`，不调 LLM |
| L2 提案缓存 | `proposal_id` | `LLMNodeProposal`（候选类/实例/关系、证据、嵌入、confidence） | 走 align/validate，不重新生成 |
| L3 注册中心 | `canonical_id` | 已 `registered` 的节点 + `use_count` / `valid_from` / `valid_to` / `supersedes` | 直接 `GENERATED_BY` 引用 |

**四态生命周期**：`proposed → validated → registered → deprecated`；bi-temporal `valid_from / valid_to / recorded_at`；**标 deprecated 而非删除**（Graphiti 式）。

**cache_key 公式**（四维版本绑定，任一项变化自然失效）：

```
cache_key = sha256(sorted_json({
  task, stage,
  input_fp        = sha256(输入节点 id 列表 + 相关 attrs 摘要),
  semantic_fp     = sha256(batch10_semantic_v4.json),
  tbox_version    = SEMANTIC_TBOX_VERSION + "@" + DYNAMIC_TBOX_VERSION,
  prompt_version, model_id, effort
}))
```

**晋升硬规则**（防污染语义层）：
1. `attribution="llm_proposal"` 的节点**永不**写 `batch10_semantic_v4.json`；
2. 只有 NON_LLM 证据（AST / 表格 / 规则 / 哈希）才能晋升为语义层属性，且需人工批准；
3. 晋升为应用节点需：受控词表命中或 `registered` 类 + ≥1 条 `evidence_ids` + 规则门 PASS + 跨 run 复用计数 ≥3（可配）；
4. 每次晋升写 append-only `PROMOTION_LOG.jsonl`，保留原提案；
5. `use_count`、`last_used`、`Lesson`、`supersedes` 在每次 run 结束时回写。

**对齐算法**：确定性 id 规范化 → `default_registry` 受控词表 → `align_metric_name()` 式三态 → 向量近邻（复用 `storage/semantic/vector` 1024 维，阈值 0.92，**仅用于幂等重放，不跨论文复用事实**）→ 冲突则保持 `proposal` 并记 `CONFLICT_LOG.jsonl`，**不自动合并**。

---

## 8. 代码结构：新增 `capfactory/paperapp/`

```
src/capfactory/paperapp/
├── __init__.py            统一导出
├── tbox.py                SciForge 26 阶段 → 应用类/关系映射表（静态声明，§5）
├── registry.py            DynamicClassRegistry：注册/停用/版本/校验
├── nodecache.py           三层缓存 + 四态生命周期 + cache_key
├── align.py               规范化 / 词表 / 向量近邻 / 冲突判定（三态→四态）
├── validate.py            提案验证：证据优先级、门、字段契约
├── promote.py             晋升规则 + PROMOTION_LOG.jsonl + use_count 回写
├── paperspec.py           compile_paperspec()：从图零 LLM 编译 PaperSpec（spec_hash）
├── phasegraph.json        26 节点 DAG（reads / produces / gate）
├── gates.py               6 态 verdict 与确定性门（复用 `sciforge/contracts.py::VERDICT_STATES`）
├── materialize.py         每次 run 结束回写：提案→注册→增量合并 app_generation.json
├── replay.py              LESSONS.json / RUN_PREPRINT 跨 run 回放
└── cli.py                 一键 run / query-cache / promote / invalidate / status
```

**修改既有文件（最小化）**：

| 文件 | 改动 |
|---|---|
| `applayer/tasks.py` | `TASK_SPECS["generation"]` 增加 `dynamic_extends="capfactory.paperapp.registry"`、`runtime_extends="capfactory.paperapp.materialize"`；**不改原有 classes/relations tuple** |
| `applayer/builder.py` | `build_task_layer()` 增加可选 `registered_nodes` 增量合并入口 + 文件锁 + `semantic_fingerprint` 校验 |
| `schema/capability.py` | `Capability` 增 `cache_key / prompt_hash / model_id / input_sha / output_sha / valid_from / valid_to / use_count`（字段追加，不破坏既有回归） |
| `po/vocab.py` | 注册 `PAPERAPP_CLASS_VOCAB` / `PAPERAPP_RELATION_VOCAB`（复用 `default_registry`） |
| `config.yaml` | 新增 `paperapp:` 段（cache_dir / thresholds / model / prompt_version） |

**产物目录**（全部在工作区 `storage/` 内，代码路径按项目惯例写 `storage_cf/`，二者是软链）：

```
storage/sciforge/
├── node_cache/
│   ├── requests/<request_key>.json          L1
│   ├── proposals/<proposal_id>.json         L2
│   ├── conflicts/CONFLICT_LOG.jsonl
│   └── index.faiss / index.json            近邻索引（复用 1024 维）
├── dynamic_tbox/
│   ├── registry.json                        L3 类注册
│   ├── relations.json
│   ├── PROMOTION_LOG.jsonl                  append-only
│   └── snapshots/dyn-1.x.x.json
├── app_generation.json                     增量回写目标
└── paperapp/<run_id>/                      运行时层 + 证据层
```

---

## 9. 分阶段实现（P0–P5）

| 阶段 | 目标 | 交付 | 验收命令 / 判据 |
|---|---|---|---|
| **P0** | 骨架 + 等价性证明 | `paperapp/{__init__,tbox,registry,nodecache}.py`；`builder.py` 增量入口；`tests/test_paperapp_p0.py` | `build_task_layer("generation")` 全量重建 与 `重建 ⊕ registered_nodes` 结果**逐节点/逐断言一致**；语义层图哈希不变；`python3 -m unittest discover -s tests` 全过 |
| **P1** | 缓存三层 + 四态 | `nodecache.py` 完整、`align.py`、`validate.py`；`DYNAMIC_ONTOLOGY_NODE_CACHE.md` 全部数据结构落地 | 同一 `cache_key` 第二次调用 `llm_calls=0`；`tbox_version` 改变后 `cache_miss`；提案 `attribution="llm_proposal"` |
| **P2** | 阶段 0–5 落地 | `DomainProfile / ResearchGap / IdeaNode / GateVerdict` 4 类注册；`paperspec.py`；`phasegraph.json` 前 10 节点 | `compile_paperspec(graph, paper_id)` 幂等（`spec_hash` 两次相同）；零 LLM；`source_node_ids` 可回溯 |
| **P3** | 阶段 6–16 落地 | 其余应用类分批注册；`gates.py` 6 态 verdict；`materialize.py` | 单次 run 结束 `PROMOTION_LOG.jsonl` 增行、`use_count` 递增、`app_generation.json` 只增 registered 节点；`events.ndjson` 可重放 |
| **P4** | 跨 run 回放与失效 | `replay.py`；`LESSONS.json` 消费；`invalidate` / `deprecated` / `supersedes` | 语义层图变更 → 依赖应用节点标 `stale` 且只重算受影响分支（复用 `RUBRIC_TREE` 的 `failed_branches` 思路）；`reuse | registered | proposal | deprecated` 四态全覆盖 |
| **P5** | 全量回归 + 报告 | `cli.py status`；`docs/SCIFORGE_INTEGRATION_REPORT.md` | 10 篇论文回归；缓存命中率、LLM 调用下降比例、新增节点数三类指标；全仓回归 + 冒烟通过 |

**每阶段的通用纪律**：
- 新增类一律先注册再写实例；
- 每个新节点带 `layer="application"`, `task="generation"`, `derived_from`, `miner`, `run_id`, `attribution`, `evidence_ids`；
- 运行时节点只写 `app_paper_runtime.json`，不进全量图；
- 所有门用 exit code / 6 态 verdict，不用散文判定；
- 先写测试再改 `builder.py`（它影响两张全量图）。

---

## 10. 复用清单与禁止事项

### 10.1 必须复用（不要重写）

`POGraph` / `Concept` / `Assertion`（`po/`）· `TaskSpec`（`applayer/tasks.py`）· `align_metric_name()` 三态（`ontology/metrics.py`）· `default_registry`（`po/vocab.py`）· `E_CONTRACTS` / `NON_LLM`（`semantic/extraction/contracts.py`）· `Capability/Evidence/Lesson`（`schema/capability.py`）· `provenance.py` 五级证据优先级 · `relations.resolve_relation()` · `ClaimAnchor` 三哈希 · `events.ndjson` / `RUNSTATE` · `rubric_tree.failed_branches` · `vector_sync` 的 1024 维索引 · `sciforge/contracts.py::VERDICT_STATES` / `validate_verdict()` 的 6 态。

### 10.2 明确禁止

1. LLM 直接写 `batch10_semantic_v4.json` 或 `app_reproduction.json`；
2. 改 `SEMANTIC_CLASSES` / `APP_CLASSES` 的 6/9 与 8/9 契约；
3. 用向量相似度跨论文复用**事实节点**（只允许复用同一 `cache_key` 的幂等结果）；
4. 删除 deprecated 节点（应标 `valid_to` + `supersedes`）；
5. 为了「缓存命中率好看」降低对齐阈值或跳过门；
6. 把 hint / prior 当最终签名（照 `domain-signature` 的单一写入者约束）；
7. 重写 `build_task_layer` 全量逻辑（只加增量入口与锁）；
8. 引入外部图数据库或新 LLM 框架（项目已是确定性图 + JSON 快照）。

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 增量回写与全量重建结果分叉 | 页面快照与缓存不一致 | P0 等价性测试 + 文件锁 + `semantic_fingerprint` |
| LLM 幻觉节点被晋升 | 污染事实链 | 四态 + NON_LLM 证据 + 人工批准 + `attribution` 隔离 |
| 缓存键漏掉版本维度 | 旧结果被错误复用 | 四维绑定（semantic_fp / tbox / prompt / model）+ 变更即 `cache_miss` |
| 动态类无限膨胀 | 图变成垃圾场 | 受控词表 + `use_count` + `valid_to` + 定期 `registry audit` |
| 全量 783 篇 × 26 阶段成本 | 算力/费用 | 缓存复用 + `failed_branches` 只重判子树 + `effort` 分档 |
| 改 `builder.py` 破坏既有全量回归 | 回归退化 | 只加可选参数与增量入口，默认值行为完全不变 |

---

## 12. 验收指标（P5 应给出实测值）

| 指标 | 口径 |
|---|---|
| `cache_hit_rate` | 命中 `request_key` 的次数 / 总请求数（按阶段分） |
| `llm_call_reduction` | 同一批论文第二次跑的 LLM 调用数下降比例 |
| `n_new_nodes_per_run` | 每次 run 新增 `proposed / validated / registered / deprecated` 各多少 |
| `promotion_rate` | `registered / proposed`，异常高说明门过松 |
| `semantic_graph_hash_stable` | 语义层图 SHA256 在所有 run 前后不变（**硬门**） |
| `rebuild_equivalence` | `build_task_layer` 全量 vs 增量结果逐断言一致（**硬门**） |
| `provenance_coverage` | 每个新节点带 `evidence_ids` + `run_id` + `attribution` 的比例 = 100% |
| `stale_recompute_scope` | 语义层变更后重算的节点数 / 总应用节点数（越小越好） |

---

## 13. 命令速查（实现后）

```bash
cd /home/zengshuxin/molecular_algrithem_design
python3 -m capfactory.paperapp.cli run --arxiv 2411.06608 --effort balanced
python3 -m capfactory.paperapp.cli cache-status
python3 -m capfactory.paperapp.cli cache-invalidate --key <request_key>
python3 -m capfactory.paperapp.cli promote --proposal <proposal_id> --approve
python3 -m capfactory.paperapp.cli registry-audit
python3 -m unittest discover -s tests -p "test_paperapp_*.py"
```

---

## 14. 关联文档

- [DYNAMIC_ONTOLOGY_NODE_CACHE.md](DYNAMIC_ONTOLOGY_NODE_CACHE.md) —— LLM 新节点缓存/四态/失效/晋升的完整设计
- [SEMANTIC_EXTRACTION_DESIGN.md](SEMANTIC_EXTRACTION_DESIGN.md) —— 语义层 v4.1 抽取设计
- [PROVENANCE_AND_VECTOR_AUDIT.md](PROVENANCE_AND_VECTOR_AUDIT.md) —— 溯源与向量审计
- [EXTRACTION_PARADIGM_RESEARCH.md](EXTRACTION_PARADIGM_RESEARCH.md) —— 抽取范式调研
- [FULL_BATCH_RUN.md](FULL_BATCH_RUN.md) —— 全量运行记录
- [skills/APPLICATION_ONTOLOGY_FRAMEWORK.md](skills/APPLICATION_ONTOLOGY_FRAMEWORK.md) —— 已生成的 SciForge 应用层本体框架
- `src/capfactory/md/APPLICATION_LAYER_DESIGN.md` / `SEMANTIC_APP_DAG.md` / `RUBRIC_TREE_LAYER.md` —— 现有三层架构与写入边界的权威说明
