# 应用层定稿：20 个节点

> 对照 `docs/skills` 的 65 个类 + 当前落地 18 个类，逐个处置后的最终清单。
> 判据三条：① 描述「论文写了什么」还是「这次用什么」；② 同名合并会不会串味；③ 没有它能否回溯选择。

## 1. 处置汇总

| 处置 | 数量 | 类 |
|---|---:|---|
| **保留** | 14 | ProblemCategory / Contribution / Assumption / FailureMode / EvidenceNorm / ExperimentArm / LeaderboardEntry / MetricDefinition / Evidence / Limitation / SourcePaper / SectionPlan / FigureAsset / DataContract |
| **已改（任务级）** | 2 | ResearchGap / CitedPaper |
| **改造（任务级）** | 1 | ReviewPoint |
| **新增** | 3 | FailureCheck / ConsultedPaper / SectionDraft |
| **删除** | 1 | ~~ResearchQuestion~~（是 `Paper.research_question` 的 1:1 副本，聚类职能由 ProblemCategory 承担） |
| **不建** | 45 | 见 §6 |

**结论：18 → 20 个类，23 → 28 条关系。**

> 当前代码为 **21 类 / 29 关系**（含待删的  与已加的 6 条任务级关系）；
> 执行"代码改动清单"第 1 步后即为 20 / 28。

## 2. 最终清单（5 个域）

记法：`类(属性) ← 关系` ；`生命周期` = `global`（全库）/ `task-w`（写作态）/ `task-r`（读态）。

### 2.1 论文域（3）

| 类 | 属性 | 关系 | 生命周期 | 产出 |
|---|---|---|---|---|
| `ProblemCategory` | code / label / n_papers | `Paper -HAS_CATEGORY->` | global | 规则（domain_code 聚合） |
| `Contribution` | statement / kind / novelty_basis / section / claimed_strength / evidence | `Paper -DECLARES->`；`-TESTED_BY-> ExperimentArm`；`-SHOWN_BY-> FigureAsset`；`-CHALLENGED_BY-> ReviewPoint` | global | E1 + R1 |
| `ResearchGap` | run_id / gap_id / gap_type / statement / evidence / priority / source_papers / selected_at | `-SEEKS_FROM-> Paper`；`-GAP_SUPPORTED_BY-> CitedPaper`；`-ANCHORS-> Contribution` | **task-w** | WritingContext |

### 2.2 方法域（3）

| 类 | 属性 | 关系 | 生命周期 | 产出 |
|---|---|---|---|---|
| `Assumption` | statement / scope / applicability / evidence / verified_status | `Algorithm -ASSUMES->`；`-TESTED_BY-> ExperimentArm` | global | E2 + R3 |
| `FailureMode` | name / severity / detection / domain_tags | `EvidenceNorm -APPLIES->` | global（知识） | 内置目录 |
| `EvidenceNorm` | evidence_type / accepted_metrics / min_fidelity / 5 个 norm | `Paper -CONFORMS_TO->`；`-APPLIES-> FailureMode` | global（知识） | 内置映射 |

### 2.3 实验域（3）

| 类 | 属性 | 关系 | 生命周期 | 产出 |
|---|---|---|---|---|
| `ExperimentArm` | kind / name / config / n_seeds / benchmark / evidence | `Paper -RUNS->`；`-ON-> Benchmark`；`Contribution -TESTED_BY->` | global | E3+E4 + R2 |
| `LeaderboardEntry` | benchmark / model / metric / value / unit / is_sota / outcome_class / seeds / fidelity | `Benchmark -HAS_ENTRY->`；`-USES_METRIC->`；`-SUPPORTED_BY-> Evidence` | global | leaderboard |
| `MetricDefinition` | name / direction / unit / n_benchmarks / sota_model / contribution_link | `Benchmark -HAS_METRIC->` | global | metrics |

### 2.4 证据域（4）

| 类 | 属性 | 关系 | 生命周期 | 产出 |
|---|---|---|---|---|
| `Evidence` | quote / kind / paper_id / source / used_in[] / char_span | `LeaderboardEntry -SUPPORTED_BY->`；`SectionDraft -USES_EVIDENCE->` | global | evidence |
| `Limitation` | statement / algorithm / kind | `Algorithm -HAS_LIMITATION->` | global | limitations |
| `CitedPaper` | run_id / cite_key / title / doi / authors / year / venue / layers / existence / metadata_ok / context_ok / context_quote / cited_in / recency_ratio | `SectionDraft -CITES->`；`ResearchGap -GAP_SUPPORTED_BY->` | **task-w** | WritingContext |
| `SourcePaper` | title / ref_paper / relation / resolved | `Paper -SITUATED_IN->` | global | source_papers |

### 2.5 写作域（7）

| 类 | 属性 | 关系 | 生命周期 | 产出 |
|---|---|---|---|---|
| `SectionPlan` | section / claims[] / word_budget / figure_min / evidence_norm | `Paper -OUTLINES->` | global（骨架） | 内置模板（按 evidence_type） |
| `SectionDraft` | run_id / section / section_plan / claims[] / word_budget / status / cited[] / evidence[] | `Paper -DRAFTS->`；`-INSTANCE_OF-> SectionPlan`；`-CITES-> CitedPaper`；`-USES_EVIDENCE-> Evidence`；`-CONSULTED-> ConsultedPaper` | **task-w** | WritingContext |
| `FigureAsset` | fig_label / caption / kind / for_contribution / placement / archetype / inferential_role | `Contribution -SHOWN_BY->` | global（属性可任务级覆盖） | E1 + R4 |
| `ReviewPoint` | run_id / axis / attack / response / severity / evidence_gap | `Contribution -CHALLENGED_BY->` | **task-w** | WritingContext |
| `FailureCheck` | run_id / status / note / checked_at | `-CHECK_OF-> FailureMode`；`Paper -CHECKED->` | **task-r** | WritingContext |
| `ConsultedPaper` | run_id / paper_id / reason / used_in | `SectionDraft -CONSULTED->` | **task-r** | WritingContext |
| `DataContract` | benchmark / input_form / output_form / n_samples / scale / modality | `Benchmark -HAS_CONTRACT->` | global | contracts |

## 3. 生命周期三分

| 生命周期 | 类 | 存储位置 | 幂等 |
|---|---|---|---|
| **global**（14） | ProblemCategory / Contribution / Assumption / FailureMode / EvidenceNorm / ExperimentArm / LeaderboardEntry / MetricDefinition / Evidence / Limitation / SourcePaper / SectionPlan / FigureAsset / DataContract | `app_writing.json` | 可重算覆盖 |
| **task-w**（4） | ResearchGap / CitedPaper / ReviewPoint / SectionDraft | `storage/writing_runs/<run_id>.json` | 同 run 同 key 复用 |
| **task-r**（2） | FailureCheck / ConsultedPaper | 同上 | 同上 |

**硬约束**：task 级节点永不写回 `app_writing.json`；global 节点不带 `run_id`。

## 4. 关系总表（28）

| # | 关系 | Domain → Range | 基数 |
|---|---|---|---|
| 1 | `HAS_CATEGORY` | Paper → ProblemCategory | N:1 |
| 2 | `DECLARES` | Paper → Contribution | 1:N |
| 3 | `RUNS` | Paper → ExperimentArm | 1:N |
| 4 | `ON` | ExperimentArm → Benchmark | N:1 |
| 5 | `TESTED_BY` | Contribution → ExperimentArm | N:M |
| 6 | `ASSUMES` | Algorithm → Assumption | 1:N |
| 7 | `CONFORMS_TO` | Paper → EvidenceNorm | N:1 |
| 8 | `APPLIES` | EvidenceNorm → FailureMode | 1:N |
| 9 | `HAS_ENTRY` | Benchmark → LeaderboardEntry | 1:N |
| 10 | `USES_METRIC` | LeaderboardEntry → MetricDefinition | N:1 |
| 11 | `HAS_METRIC` | Benchmark → MetricDefinition | N:M |
| 12 | `SUPPORTED_BY` | LeaderboardEntry → Evidence | N:M |
| 13 | `HAS_CONTRACT` | Benchmark → DataContract | 1:1 |
| 14 | `HAS_LIMITATION` | Algorithm → Limitation | 1:N |
| 15 | `SITUATED_IN` | Paper → SourcePaper | N:M |
| 16 | `SHOWN_BY` | Contribution → FigureAsset | N:M |
| 17 | `OUTLINES` | Paper → SectionPlan | 1:N |
| 18 | `CHALLENGED_BY` | Contribution → ReviewPoint | 1:N |
| 19 | `SEEKS_FROM` | ResearchGap → Paper | N:M |
| 20 | `GAP_SUPPORTED_BY` | ResearchGap → CitedPaper | N:M |
| 21 | `ANCHORS` | ResearchGap → Contribution | N:1 |
| 22 | `DRAFTS` | Paper → SectionDraft | 1:N |
| 23 | `INSTANCE_OF` | SectionDraft → SectionPlan | N:1 |
| 24 | `CITES` | SectionDraft → CitedPaper | N:M |
| 25 | `USES_EVIDENCE` | SectionDraft → Evidence | N:M |
| 26 | `CONSULTED` | SectionDraft → ConsultedPaper | N:M |
| 27 | `CHECKED` | Paper → FailureCheck | 1:N |
| 28 | `CHECK_OF` | FailureCheck → FailureMode | N:1 |

## 5. 与 skills 65 个类的映射

| skills 类 | 我方 | 处置 |
|---|---|---|
| `Gap` | `ResearchGap` | 改任务级 |
| `VerifiedPaper` / `CandidatePaper` / `VerificationLayer` | `CitedPaper`（layers[] 收三层） | 三合一 |
| `EvidenceNormProfile` | `EvidenceNorm` | 已并 |
| `Assumption` | `Assumption` | 直接对应 |
| `MethodRegistry` / `ExperimentMatrix` | `ExperimentArm` + `METHOD_LOCK` | 部分 |
| `Result` | `LeaderboardEntry` | 对应 |
| `Claim` | `numeric` SAU + `ClaimAnchor` | 不建类 |
| `FigureSpec` / `Figure` / `Caption` | `FigureAsset` | 三合一 |
| `PaperSection` | `SectionPlan`（骨架）+ `SectionDraft`（实例） | 拆二 |
| `DomainProfile` | `Paper.paradigm` + `evidence_type` | 降为属性 |
| `FrontierBaseline` / `DeltaClaim` / `WhyNotBefore` | `novelty_basis` + `ResearchGap` | 拆二 |
| `Tool` / `ToolContract` | E5 字符串 | 不建 |
| `Panel` | — | 不建（低价值） |
| 治理层 10 个 | `gates.py` / `effort_limits` / `METHOD_LOCK` | 运行时 |
| `IdeaNode` / `MCTS*` / `FinalProposal` / `Survivor` | — | 选题阶段，不属于「论文已有事实 + 写作」 |
| `Sandbox*` / `DeviceProfile` / `DependencyRoot` | `reprospec` 运行时 | 不建 |
| `DataSource` / `CollisionMatrix` / `TypeASpec` | 检索/筛选工具 | 不建 |

## 6. 不建的 45 个（分类理由）

| 类别 | 数量 | 理由 |
|---|---:|---|
| 治理与流程（ProblemAnchor / Phase / Skill / Gate / Verdict / LoopBack / RunBudget / ArtifactRegistry / ClaimAnchor / Hash） | 10 | 已由 `gates.py`、`METHOD_LOCK`、`effort_limits` 承担，进图会变成「流程元数据」 |
| 选题阶段（IdeaNode / MCTSRound / FailedIdea / BAEvent / Survivor / FinalProposal / CollisionMatrix / TypeASpec / FrontierNode / WhyNotBefore / DeltaClaim / FrontierBaseline） | 12 | 属于「生成新论文」的决策过程，不是「已有论文的事实」 |
| 检索与核验（DataSource / CandidatePaper / VerificationLayer） | 3 | 已折叠进 `CitedPaper.layers[]` |
| 工具与沙箱（Tool / ToolContract / ToolTemplate / CapabilityGap / DependencyRoot / DeviceProfile / SandboxSession / SandboxCode / SecurityFinding / SmokeEvidence / TripleHash） | 11 | 运行时产物，`reprospec` 已有对应文件，不必进图 |
| 呈现细节（Panel / Renderer / FigureBudget / VisualReview / DesignToken / DataEncodingColormap / InputData / OutputData） | 8 | 渲染层实现细节，`FigureAsset` 已覆盖「图是什么、支撑谁」 |
| 已被覆盖（VerifiedPaper） | 1 | 并入 `CitedPaper` |

## 7. 代码改动清单（落地顺序）

| 步 | 改动 | 影响文件 | 风险 |
|---|---|---|---|
| 1 | 删 `ResearchQuestion`，加 `HAS_CATEGORY` | `applayer/tbox.py`、`miner.py`（删 1 段）、`tasks.py` | 低（无下游强依赖） |
| 2 | 加 `SectionDraft` / `FailureCheck` / `ConsultedPaper` | `tbox.py` + `context.py` 加 4 个方法 | 低（纯新增） |
| 3 | `ReviewPoint` 改任务级 | `miner.py` 删 review_points 段；`context.py` 加 `review()` | 中（现有测试断言 6 条） |
| 4 | `SectionPlan` 拆骨架/实例 | `miner.py` 保留骨架；`context.py` 加 `plan_section()` | 中 |
| 5 | `FigureAsset` 加 `archetype` / `inferential_role` | `tbox.py` + `E1`/`R4` YAML | 低 |
| 6 | `Evidence` 加 `used_in[]` / `char_span` | `tbox.py` + `evidence` 挖掘器 | 低 |
| 7 | `Assumption` 加 `verified_status` | `tbox.py` | 低 |

**第 1–2 步可以立即做**（不破坏现有行为）；第 3–4 步要先改测试预期。
