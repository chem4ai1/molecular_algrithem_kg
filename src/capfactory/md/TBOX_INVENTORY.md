# TBox 清点与精简依据（实测版）

> 生成时间 2026-11-13；数据源 `storage_cf/sciforge/batch10_final_graph.json`
> （449 节点 / 633 断言）与 `ontology/library._all_relations()`（45 类 / 102 关系）。
> 本文所有数字为**实测**，不是定义抄录；判定列给出精简动作。

## 0. 一句话结论

```
TBox 定义        45 类 / 102 关系
图内实际类型     16 类（其中 MetricObservation 未在 TBox）
在用关系         18 个（15 个 TBox 已定义 + 3 个 TBox 缺失）
零节点类         30 个（45 中 67%）
零使用关系       87 个（102 中 85%）
```

精简方向不是「删到 16 类 18 关系」，而是三件事：
1. **补齐** 3 个在用但 TBox 缺失的关系（`REPORTS/OF_METRIC/RELATED_TO`）+ 1 个缺失的类（`MetricObservation`）；
2. **修正** 3 处 domain/range 口径与事实不符；
3. **归档** 零节点类与零使用关系中确认无后续规划的部分（保留少数为 reserved）。

---

## 1. 在用的类（16 个）

| 类 | 节点数 | 功能 | 判定 |
|---|---:|---|---|
| `Algorithm` | 34 | 算法实例；核心是能解决什么问题+机理+任务类型，用于按问题检索与找基线 | 保留 |
| `AlgorithmStep` | 31 | 算法步骤；承载机理分步与代码实现落点(IMPLEMENTS_MODULE 的目标) | 保留 |
| `Benchmark` | 85 | 评测基准/数据集实例；输入输出形式+指标+模型×指标矩阵+动态 SOTA | 保留 |
| `CodeFunction` | 49 | 代码函数；由 AST 对齐产生，是算法步骤的实现证据 | 保留 |
| `CodeRepository` | 10 | 代码仓库；由论文 HAS_CODE 挂到论文，不是算法属性 | 保留 |
| `DataContract` | 3 | 基准的数据契约快照（装配层生成，承载 input/output/metrics） | 保留 |
| `Evidence` | 6 | 证据；来源片段 (section/extraction_method)，支撑断言可核验 | 保留 |
| `LeaderboardEntry` | 73 | 榜单行（模型×基准）；PG 抽取结果的图内镜像 | 保留 |
| `Limitation` | 2 | 局限短语；由科技树 HAS_LIMITATION 产生 | 保留 |
| `MetricDefinition` | 12 | 指标定义；direction(min/max) 决定 SOTA 计算方向 | 保留 |
| `Observation` | 8 | 观测值（论文表格里的数值，含 metric/value/unit） | 保留 |
| `Paper` | 36 | 论文实例；三核心为研究问题/领域/算法族，关系线索供后续抽取 | 保留 |
| `ProblemCategory` | 5 | 问题类别；用于问题层面的聚合与检索 | 保留 |
| `ResearchQuestion` | 17 | 研究问题；论文 ADDRESSES 的对象，BROADER 连到问题类别 | 保留 |
| `SourcePaper` | 5 | 出处论文占位（科技树节点）；COMPARES_WITH/HAS_LIMITATION 的主体 | 保留 |

### 1.1 在用类的属性（按覆盖率排序，只列有用的）

> 覆盖 = 非空节点数 / 该类节点数。`must_have` 但覆盖为 0 = **定义与数据冲突**，必须处理。

#### `Algorithm`（34 节点，定义 7 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `name` | must_have | 34/34 | 名称 |

- 零覆盖 should/optional（精简候选）：`kind`, `granularity`, `architecture`, `algo_codes`, `paper_ids`, `repository_id`
- **图有但 TBox 未定义（需补定义）**：`schema_family`, `task_type`, `task_type_label`, `problems_solved`, `mechanism`, `mechanism_steps`, `why_it_works`, `applicable_to`, `limitations`, `source_paper`

#### `AlgorithmStep`（31 节点，定义 17 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `module_name` | must_have | 31/31 | 模块名 |
| `mechanism` | should_have | 31/31 | 机理 |
| `causal_role` | should_have | 31/31 | 因果关系角色（input/mechanism/state） |
| `inputs` | should_have | 31/31 | 输入变量/张量 |
| `outputs` | should_have | 31/31 | 输出变量/张量 |
| `order` | should_have | 31/31 | 步骤序号 |
| `grounding_status` | should_have | 31/31 | 代码落地状态（matched/partial/gap） |
| `code_symbols` | optional | 26/31 | 关联代码符号（AST 对齐） |
| `equation_ref` | optional | 19/31 | 公式编号（如 (2)） |
| `parameters` | optional | 4/31 | 可学习参数 |

- **零覆盖 must_have（冲突，需修定义或补数据）**：`algorithm_id`
- 零覆盖 should/optional（精简候选）：`role`, `phase`, `input_form_id`, `output_form_id`, `is_baseline`, `composition_id`
- **图有但 TBox 未定义（需补定义）**：`input_schema`, `output_schema`, `paper_id`, `filled_by`

#### `Benchmark`（85 节点，定义 28 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `name` | must_have | 85/85 | 基准名 |
| `modality` | optional | 62/85 | 数据模态 |
| `research_object` | optional | 62/85 | 研究对象 |
| `n_samples` | optional | 21/85 | 样本量 |
| `aliases` | optional | 20/85 | 别名（同名去重） |

- **零覆盖 must_have（冲突，需修定义或补数据）**：`comparability_profile`
- 零覆盖 should/optional（精简候选）：`version`, `data_source`, `task_type`, `n_targets`, `split_rule`, `split_ratio`, `leakage_risk`, `metric_ids`, `top_k`, `sample_budget`, `threshold`, `stage`, `input_schema`, `output_schema`, `problem_ids`, `availability`, `license`, `url`, `source_evidence_ids`, `tested_by_papers`, `tested_by_codes`, `n_observations`
- **图有但 TBox 未定义（需补定义）**：`schema_family`, `schema_version`, `input_form`, `output_form`, `metrics`, `model_results`, `sota_by_metric`, `scale`, `matrix`, `source_locator`

#### `CodeFunction`（49 节点，定义 8 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `name` | must_have | 45/49 | 名称 |
| `signature` | should_have | 45/49 | 函数签名 |
| `causal_role` | should_have | 45/49 | 因果关系角色（input/mechanism/state） |
| `module_path` | should_have | 45/49 | 模块文件路径 |
| `docstring` | optional | 7/49 | 函数文档字符串 |
| `matched_step_ids` | optional | 7/49 | 对齐到的算法步骤 id 列表 |

- 零覆盖 should/optional（精简候选）：`owner_class`, `lineno`
- **图有但 TBox 未定义（需补定义）**：`filled_by`, `source_locator`, `provenance`, `run_id`, `inputs_sha`

#### `CodeRepository`（10 节点，定义 15 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `repo_name` | must_have | 10/10 | 仓库名 |
| `local_path` | optional | 10/10 | 本地仓库路径 |

- 零覆盖 should/optional（精简候选）：`availability`, `license`, `repo_url`, `commit`, `sha256`, `language`, `loc`, `capability_version_id`, `module_ids`, `has_requirements`, `entry_point`, `runnable`, `paper_ids`
- **图有但 TBox 未定义（需补定义）**：`is_original_repo`, `repo_provenance`

#### `DataContract`（3 节点，定义 0 属性）

- **图有但 TBox 未定义（需补定义）**：`source_locator`, `provenance`, `run_id`, `inputs_sha`, `input_form`, `output_form`, `metrics`

#### `Evidence`（6 节点，定义 4 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `quote` | must_have | 6/6 | 原文逐字引文 |
| `paper_id` | should_have | 6/6 | 所属论文 id |

- **零覆盖 must_have（冲突，需修定义或补数据）**：`section_id`
- 零覆盖 should/optional（精简候选）：`attribution`
- **图有但 TBox 未定义（需补定义）**：`section`, `extraction_method`

#### `LeaderboardEntry`（73 节点，定义 9 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `benchmark_id` | must_have | 73/73 | 所属基准 id |
| `metric_id` | must_have | 73/73 | 指标 id |
| `value` | must_have | 73/73 | 数值 |
| `rank` | optional | 73/73 | 榜单排名 |
| `sota_claimable` | optional | 73/73 | 该结果是否可计入 SOTA（非评测表为 false） |
| `paper_id` | optional | 73/73 | 所属论文 id |

- **零覆盖 must_have（冲突，需修定义或补数据）**：`group_key`
- 零覆盖 should/optional（精简候选）：`is_sota`, `code_id`
- **图有但 TBox 未定义（需补定义）**：`unit`, `subject`

#### `Limitation`（2 节点，定义 3 属性）


- **零覆盖 must_have（冲突，需修定义或补数据）**：`statement`
- 零覆盖 should/optional（精简候选）：`kind`, `paper_id`
- **图有但 TBox 未定义（需补定义）**：`source_locator`, `provenance`, `run_id`, `inputs_sha`, `delta`

#### `MetricDefinition`（12 节点，定义 6 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `name` | must_have | 12/12 | 名称 |
| `direction` | should_have | 12/12 | min/max，SOTA 计算方向 |
| `unit` | optional | 8/12 | 单位 |

- 零覆盖 should/optional（精简候选）：`value_type`, `aggregation`, `modality`

#### `Observation`（8 节点，定义 17 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `value` | must_have | 8/8 | 观测数值 |
| `unit` | should_have | 6/8 | 单位 |

- **零覆盖 must_have（冲突，需修定义或补数据）**：`metric_id`
- 零覆盖 should/optional（精简候选）：`subject`, `modality`, `condition`, `aggregation`, `numerator`, `denominator`, `stage`, `threshold`, `top_k`, `sample_budget`, `split_rule`, `missing_state`, `evidence_ids`, `comparability_key`
- **图有但 TBox 未定义（需补定义）**：`source_locator`, `provenance`, `run_id`, `inputs_sha`, `metric`

#### `Paper`（36 节点，定义 8 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `title` | must_have | 36/36 | 论文标题（卡片主标题） |
| `arxiv_id` | optional | 36/36 | arXiv 标识，关联原文 md 与复现入口 |
| `domain_codes` | optional | 36/36 | 领域码（内部） |
| `algo_codes` | optional | 36/36 | 算法码（内部） |
| `year` | optional | 2/36 | 年份 |

- 零覆盖 should/optional（精简候选）：`doi`, `venue`, `versions`
- **图有但 TBox 未定义（需补定义）**：`research_problem`, `problem_type`, `domain`, `domain_code`, `algorithm_family`, `algorithm_family_id`, `why_hard`, `evidence`, `relation_hints`, `schema_version`

#### `ProblemCategory`（5 节点，定义 4 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `code` | must_have | 5/5 | 代码片段/符号 |
| `label` | optional | 5/5 | 显示名 |

- 零覆盖 should/optional（精简候选）：`n_papers`, `n_benchmarks`

#### `ResearchQuestion`（17 节点，定义 5 属性）

| 属性 | 级别 | 覆盖 | 功能 |
|---|---|---:|---|
| `question` | must_have | 17/17 | 研究问题陈述 |
| `granularity` | optional | 17/17 | 粒度 |

- 零覆盖 should/optional（精简候选）：`parent`, `status`, `paper_ids`
- **图有但 TBox 未定义（需补定义）**：`paper_id`

#### `SourcePaper`（5 节点，定义 0 属性）

- **图有但 TBox 未定义（需补定义）**：`source_locator`, `provenance`, `run_id`, `inputs_sha`, `delta`

---

## 2. 零节点类（30 个）

这些类有定义、有属性，但图里 0 个实例。**它们不是 bug，而是「预留/研究层」**：
当前主图只覆盖「论文-算法-代码-数据-指标-榜单-证据」这条主链。

| 分组 | 类 | 判定 |
|---|---|---|
| V3 假设/评测链（预留） | `Hypothesis`, `EvaluationRun`, `EvaluationTool`, `ReproductionResult`, `EvaluationResult` | 归档为 reserved（不删定义，移入 `reserved` 分组） |
| 生成任务链（研究层） | `Proposal`, `CodeGenerationTask`, `StaticCheck`, `CompileReport`, `MethodLock`, `RunPhase`, `ReviewVerdict`, `ClaimAnchor` | 归档为 reserved（不删定义，移入 `reserved` 分组） |
| 叙事/写作链（研究层） | `ManuscriptSection`, `Figure`, `NarrativeConstraint`, `Section` | 归档为 reserved（不删定义，移入 `reserved` 分组） |
| 因果链（研究层） | `CausalGraph`, `CausalNode`, `ExperimentNode` | 归档为 reserved（不删定义，移入 `reserved` 分组） |
| 方法/对象细化 | `MethodApplication`, `AlgorithmComposition`, `AlgorithmFamily`, `DataForm`, `ResearchObject`, `Domain`, `Tool`, `Formula`, `CodeModule`, `GroundingAlignment`, `CapabilityClaim` | 归档为 reserved（不删定义，移入 `reserved` 分组） |

> 精简动作：**不删定义**，在 `ontology/reserved.py` 里集中声明并在 README 标注
> 「当前不产生实例」；这样 `compile_tbox` 计数与测试断言可控，也不会误导后续抽取。

---

## 3. 在用的关系（18 个，含 3 个 TBox 未定义）

| 关系 | 声明 domain → range | 断言数 | 实际类型组合 | 功能 | 判定 |
|---|---|---:|---|---|---|
| `FROM_OBSERVATION` | LeaderboardEntry → Observation | 73 | LeaderboardEntry->MetricObservation x73 | 榜单行→观测，提供数值 | 保留 |
| `HAS_LEADERBOARD` | Benchmark → LeaderboardEntry | 73 | Benchmark->LeaderboardEntry x73 | 基准→榜单行，矩阵行来源 | 保留 |
| `REPORTED_BY` | LeaderboardEntry → Paper|CodeRepository | 73 | LeaderboardEntry->Paper x73 | 榜单行→来源论文，数值可溯源 | 保留 |
| `REPORTS` | —(缺) → MetricObservation | 73 | Paper->MetricObservation x73 | ★TBox 缺：Paper→MetricObservation(73) | 补定义 |
| `OF_METRIC` | —(缺) → MetricDefinition | 73 | MetricObservation->MetricDefinition x73 | ★TBox 缺：MetricObservation→MetricDefinition(73) | 补定义 |
| `IMPLEMENTS_MODULE` | CodeFunction → AlgorithmStep | 48 | CodeFunction->AlgorithmStep x48 | 代码函数→算法步骤，代码实现证据 | 保留 |
| `RELATED_TO` | —(缺) → Paper|Algorithm | 48 | Paper->Paper x26; Paper->Algorithm x22 | ★TBox 缺：论文-论文(26)/论文-算法(22)，关系层主链 | 补定义 |
| `EVALUATED_ON` | Paper|Algorithm|CodeRepository → Benchmark | 45 | Paper->Benchmark x45 | 论文/算法/仓库→基准，复现 R3 与关系浏览器核心链 | 保留 |
| `HAS_MODULE_DETAIL` | Algorithm → AlgorithmStep | 31 | Paper->AlgorithmStep x31 | ★口径不符：声明 Algorithm，实际 Paper→AlgorithmStep(31) | 修口径 |
| `USES_METRIC` | Benchmark|EvaluationRun → MetricDefinition | 27 | Benchmark->MetricDefinition x27 | 基准→指标定义，SOTA 方向来源 | 保留 |
| `ADDRESSES` | Paper → ResearchQuestion | 17 | Paper->ResearchQuestion x17 | 论文→研究问题，论文视图第一链 | 保留 |
| `BROADER` | ResearchQuestion → ProblemCategory | 17 | ResearchQuestion->ProblemCategory x17 | 研究问题→问题类别，问题聚合 | 保留 |
| `PROPOSES_METHOD` | Paper → Algorithm | 12 | Paper->Algorithm x12 | 论文→算法，复现 R1 与算法卡片来源 | 保留 |
| `HAS_CODE` | Paper → CodeRepository | 10 | Paper->CodeRepository x10 | 论文→代码仓库，复现 R2 来源 | 保留 |
| `SUPPORTED_BY` | CapabilityClaim|Limitation|Observation → Evidence|Section | 6 | Benchmark->Evidence x3; Algorithm->Evidence x1 | ★口径不符：实际 Benchmark/Algorithm/CodeFunction/AlgorithmStep→Evidence | 修口径 |
| `HAS_DATA_CONTRACT` | Benchmark → DataContract | 3 | Benchmark->DataContract x3 | 基准→数据契约，装配层 A4 生成 | 保留 |
| `COMPARES_WITH` | SourcePaper → SourcePaper | 2 | SourcePaper->SourcePaper x2 | 科技树：出处对比链 | 保留 |
| `HAS_LIMITATION` | SourcePaper → Limitation | 2 | SourcePaper->Limitation x2 | 科技树：出处局限 | 保留 |

---

## 4. 零使用关系（87 个）

按定义来源分组。**这些关系全部有 0 条断言**，精简时是按来源整组处理，而不是逐个判断。

| 来源 | 数量 | 关系 | 判定 |
|---|---:|---|---|
| `V2` | 7 | `ABOUT_METHOD`, `ABOUT_SUBJECT`, `BENCHMARK_FOR`, `HAS_SECTION`, `IN_DOMAIN`, `PRODUCES_OBSERVATION`, `USES_ALGO_FAMILY` | reserved（随所属组归档） |
| `layers` | 29 | `ALIGNED_BY`, `APPLIED_ON`, `BINDS_TOOL`, `CALLS`, `CAUSES`, `CONSUMES`, `CONTAINS_MODULE`, `CORRECTED_BY`, `DEFINES_FUNCTION`, `EMITS`, `FLOWS_DATA_TO`, `FLOWS_TO`, `GROUNDS_TO`, `HAS_BLOCK`, `HAS_CAUSAL_GRAPH`, `HAS_CAUSAL_NODE`, `HAS_COMPOSITION`, `HAS_INPUT_SCHEMA`, `HAS_OUTPUT_SCHEMA`, `HAS_STEP`, `IMPLEMENTS_ALGORITHM`, `IMPLEMENTS_METRIC`, `IN_COMPOSITION`, `PARENT_OF`, `PARTICIPATES_IN`, `PRODUCES`, `REALIZES`, `RUNS_ON`, `SCORED_BY` | reserved（随所属组归档） |
| `generation` | 24 | `ANCHORED_TO`, `ANCHORS_GAP`, `ASSERTS`, `BINDS_BENCHMARK`, `CHECKED_BY`, `CONSTRAINED_BY`, `CORROBORATES`, `DERIVED_FROM`, `EMBEDS`, `GATED_BY`, `GENERATES`, `GENERATES_MODULE`, `GOVERNS`, `GROUNDS`, `HAS_PHASE`, `HAS_PROPOSAL`, `IMPLEMENTS_STEP`, `LOCKED_BY`, `LOOPS_BACK_TO`, `PRODUCED_BY`, `REPORTS_ON`, `REVIEWS`, `RUNS_IN`, `USES_FIGURE` | reserved（随所属组归档） |
| `V3` | 27 | `ADDRESSED_BY`, `APPLIES_TO`, `BELONGS_TO`, `BINDS_EVAL_TOOL`, `DECLARES_HYPOTHESIS`, `DELTA`, `EVALUATES_METHOD`, `HAS_FORMULA`, `HAS_INPUT_FORM`, `HAS_INPUT_OBJECT`, `HAS_MODULE_IMPL`, `HAS_OUTPUT_FORM`, `HAS_OUTPUT_OBJECT`, `IMPROVED_BY`, `LEADS_TO`, `ON_METRIC`, `REALIZED_BY`, `REFERS_TO`, `REPLACED_BY`, `REPLACES`, `REPORTS_VALUE`, `RESOLVED_TO`, `SITUATED_IN`, `SOURCED_FROM`, `SUPPORTS_HYPOTHESIS`, `TESTS_HYPOTHESIS`, `USES_TOOL` | reserved（随所属组归档） |

> 特别说明：`layers` 与 `generation` 两组关系（算法分层建模、生成任务链）来自
> `docs/GENERATION_*.md` 的研究层设计，当前主图不产生实例；保留定义但标记 reserved。

---

## 5. 口径与定义冲突（必须修的 6 项）

| # | 问题 | 实测 | 修法 |
|---|---|---|---|
| 1 | `REPORTS` 不在 TBox | Paper→MetricObservation 73 条 | 补进 `V3_RELATIONS`：`(Paper, MetricObservation, "论文报告观测")` |
| 2 | `OF_METRIC` 不在 TBox | MetricObservation→MetricDefinition 73 条 | 补：`(MetricObservation, MetricDefinition, "观测所用指标")` |
| 3 | `RELATED_TO` 不在 TBox | 论文-论文 26、论文-算法 22 | 补：`(Paper, "Paper\|Algorithm", "相关文献/方法")` |
| 4 | `MetricObservation` 类缺失 | 73 个节点 | 补进类表（或把 73 节点改型为 `Observation`） |
| 5 | `HAS_MODULE_DETAIL` 声明 Algorithm | 实际 Paper→AlgorithmStep 31 条 | 改 domain 为 `Algorithm\|Paper`，或修上游写入 |
| 6 | `SUPPORTED_BY` domain 过窄 | 实际 Benchmark/Algorithm/CodeFunction/AlgorithmStep→Evidence | domain 扩为 `CapabilityClaim\|Limitation\|Observation\|Benchmark\|Algorithm\|AlgorithmStep\|CodeFunction` |

> 前 3 项是「图里有、TBox 没有」，会让 TBox 校验形同虚设（7 处断言绕过校验）；
> 第 4 项让 73 个节点类型悬空；第 5/6 项是声明与事实相反。**精简前先修这 6 项**。

---

## 6. 属性层面的两个反向问题

### 6.1 图有、TBox 未定义（TBox 校验漏检）

| 类 | 未定义但大量使用的属性 | 条数 | 处理 |
|---|---|---:|---|
| `Paper` | `research_problem / problem_type / domain / domain_code / algorithm_family / algorithm_family_id / why_hard / relation_hints` | 36 | **补进类定义**（这是论文三核心，必须进 TBox） |
| `Algorithm` | `schema_family / task_type / task_type_label / problems_solved / mechanism / mechanism_steps / why_it_works / applicable_to / limitations / baseline_group / search_text` | 34 | 补进类定义（问题/机理核心） |
| `Benchmark` | `schema_family / input_form / output_form / metrics / model_results / sota_by_metric / matrix / is_evaluation / n_samples / scale / modality / research_object` | 85 | 补进类定义（数据契约核心） |
| `LeaderboardEntry` | `unit / subject` | 73 | 补进类定义 |
| `DataContract` | `input_form / output_form / metrics` | 3 | 补进类定义 |
| `CodeRepository` | `is_original_repo / repo_provenance` | 10 | 补进类定义 |
| `Evidence` | `section / extraction_method` | 6 | 补进类定义 |
| `Observation` | `metric` | 8 | 补进类定义 |

> 这 8 项合计约 20 个属性是当前**真正在用的属性**，却没在 TBox 里；
> `compile_tbox` 校验因此无法约束它们。精简的第一优先级是**补定义**，不是删东西。

### 6.2 must_have 但零覆盖（定义与数据冲突）

| 类 | 属性 | 问题 |
|---|---|---|
| `AlgorithmStep` | `algorithm_id` (must_have) | 31 个节点全空；实际用 `paper_id` 关联，说明该必填字段设计错了 |
| `Benchmark` | `split_rule` (should_have) | 0 覆盖，但 `split_type` 在 algorithm/paper 侧有值 → 命名不统一 |
| `Algorithm` | `kind` (should_have) | 0 覆盖，实际用 `task_type` 替代 |

处理：把 `algorithm_id` 降级为 optional 或改名为 `paper_id`；`split_rule` 与 `split_type` 统一命名。

---

## 7. 精简方案（三档，按风险排序）

### 第一档：补定义 + 修口径（必须做，零风险）

| 动作 | 效果 |
|---|---|
| 补 `REPORTS / OF_METRIC / RELATED_TO` 3 个关系 | 消除 7 处「不在 TBox」绕过，TBox 关系 102 → 105 |
| 补 `MetricObservation` 类 | 73 个节点不再悬空，类 45 → 46 |
| 修 `HAS_MODULE_DETAIL` domain、`SUPPORTED_BY` domain | 消除 36 条口径不符 |
| 补 6.1 的约 20 个在用属性 | TBox 校验真正覆盖主链 |
| 降级 `AlgorithmStep.algorithm_id`、统一 `split_rule/split_type` | 消除零覆盖 must_have |

做完后：**在用项覆盖率 100%**，`compile_tbox().issues` 仍为 0，测试计数断言同步 +3/+1。

### 第二档：reserved 分组（保守，推荐）

在 `ontology/tbox.py` 增加：

```python
RESERVED_CLASSES = {...30 个零节点类...}
RESERVED_RELATIONS = {...83 个零使用关系...}
def active_snapshot() -> dict   # 只含在用项
def reserved_snapshot() -> dict # 只含 reserved
```

`compile_tbox` 输出 `n_classes/n_relations` 仍为全量（测试不破），
但页面与抽取提示词只引用 `active_snapshot()`。这样：
- 不删任何定义，不影响 670 测试；
- 后续抽取不会去填 30 个空类；
- 新增能力时从 reserved 里「升级」而不是新造词。

### 第三档：真正删除（后续，需迁移测试）

确认 reserved 中某组永不使用后：
1. 删除定义源条目 → `tbox.snapshot()['n_relations']` 下降；
2. 同步 `tests/test_ontology_library.py`、`tests/Phase/test_phase00_intake.py`、
   `tests/test_architecture.py` 的计数断言；
3. 重跑 670 + 81 + 冒烟。

> 建议顺序：**第一档立即执行**；第二档本轮即可加（纯新增，不改语义）；
> 第三档等主图扩展到评测/生成链后再做，否则会反复增删。

---

## 8. 功能标注总览（一句话看懂每类/每关系的作用）

**主链 7 环**：

```
Paper --PROPOSES_METHOD--> Algorithm --HAS_MODULE_DETAIL--> AlgorithmStep
  |                              ^                                ^
  |--HAS_CODE--> CodeRepository  |                                |
  |                              +----IMPLEMENTS_MODULE-----------+
  |--EVALUATED_ON--> Benchmark --HAS_LEADERBOARD--> LeaderboardEntry
                        |                                |
                        |--USES_METRIC--> MetricDefinition
                        |--HAS_DATA_CONTRACT--> DataContract
                        +--FROM_OBSERVATION--> MetricObservation --OF_METRIC--> MetricDefinition
                        +--REPORTED_BY--> Paper
Paper --ADDRESSES--> ResearchQuestion --BROADER--> ProblemCategory
任何实体 --SUPPORTED_BY--> Evidence
SourcePaper --COMPARES_WITH/HAS_LIMITATION--> SourcePaper/Limitation
```

其余 87 个关系与 30 个类属于**研究层/预留层**，当前不产生实例。

---

## 9. 复现本文数字

```bash
python3 - <<'PY'
from capfactory.po import POGraph
from capfactory.ontology.library import default_library
g=POGraph.load('storage_cf/sciforge/batch10_final_graph.json')
lib=default_library()
print('TBox', len(lib.classes),'类 /',len(lib.relations),'关系')
print('图内类型', len({n.type for n in g.nodes.values()}))
print('在用关系', sum(1 for a in set(x.relation for x in g.assertions)))
PY
```

中间数据：`storage_cf/sciforge/tbox_usage.json`（每类属性覆盖率、每关系断言数与实际类型组合）。

---

## 10. 执行状态（2026-11-13 已实施第一档 + 第二档）

| 动作 | 结果 |
|---|---|
| 补 3 个关系 `REPORTS / OF_METRIC / RELATED_TO` | TBox 关系 102 → **105** |
| 补 `MetricObservation` 类（Observation 的别名子类，5 字段） | 类 45 → **46**，shapes 45 → **46** |
| 修 `HAS_MODULE_DETAIL` domain → `Algorithm\|Paper` | 31 条口径不符消除 |
| 修 `SUPPORTED_BY` domain 扩到 7 个类 | 6 条口径不符消除 |
| `tbox.resolve_type()` 别名归一（7 条 TYPE_ALIASES） | `MetricObservation` 73 节点不再悬空 |
| 补 7 个类的在用属性（Paper16/Algorithm18/Benchmark38/Leaderboard11/Evidence6/Observation18/CodeRepository17 字段） | TBox 覆盖在用属性 |
| `AlgorithmStep.algorithm_id` must_have → optional，新增 `paper_id` | 消除 31/31 零覆盖必填冲突 |
| `Benchmark` 增 `split_type`（与 `split_rule` 并存） | 命名统一过渡 |
| 新增 `RESERVED_CLASSES(30)` / `RESERVED_RELATIONS(87)` | 第二档：不删定义，标记 reserved |
| 新增 `active_snapshot() / reserved_snapshot() / is_reserved()` | 页面与抽取提示词只引用 active |

**实测验收**：

```
TBox 定义        46 类 / 105 关系（version v3.2-105）
active           16 类 /  18 关系  ← 页面/抽取应只引用
reserved         30 类 /  87 关系  ← 保留定义，不产生实例
口径不符断言      36 → 0
compile_tbox().issues = 0
装配黄金用例      gate=PASS / 悬空边 0 / violations 0
回归             670 unittest OK · Phase 81 OK · 冒烟 60/60
```

**未做（第三档，按计划留待后续）**：删除 reserved 中的确定无用项。原因：评测链
（`EvaluationRun/EvaluationTool`）、生成任务链（`Proposal/CodeGenerationTask`）、
叙事链（`ManuscriptSection/Figure`）是下一步能力，删了需重建；等主图扩展到这些链后
再按「定义删除 + 断言同步」执行。

**下一步建议**：
1. 页面与抽取提示词改用 `active_snapshot()`（目前仍读全量，行为未变）；
2. 用 reserved 分组做「能力升级清单」：每扩一条链，就把对应类/关系从 reserved 移出；
3. `split_rule` 与 `split_type` 在下一轮抽取中统一为 `split_type`，随后删除 `split_rule`。
