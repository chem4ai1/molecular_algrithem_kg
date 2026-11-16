# 语义层 S1 + 应用层 S2 升级说明

> 依据：`docs/question_knowledge_skills/new/00`–`13`。
> 一句话：语义层补「写作方法论事实」，应用层从 8 类扩到 17 类，任务从
> `reproduction`/`generation` 改为 `reproduction`/`writing`（`generation` 保留别名）。

## 1. 语义层：11 个新字段

| 类 | 新字段 | 用途 |
|---|---|---|
| **Paper** | `paradigm` | 研究范式（formal/empirical/design/interpretive） |
| | `evidence_type` | 证据类型（6 类，决定失败模式与章节硬要求） |
| | `evidence_norm` | 该领域认可的指标与证据规范 |
| | `figures` | 图表清单 `[{label,caption,kind,for_contribution}]` |
| | `section_map` | 章节→论断映射 |
| **Algorithm** | `assumptions` | 方法成立前提（Type II 泄露检查） |
| | `novelty_basis` | 新颖性依据（技术约束/理论盲点/数据可得性） |
| **AlgorithmModule** | `is_novel_component` | 是否论文声称的创新组件 |
| | `component_role` | backbone/encoder/decoder/loss/sampler/other |
| **Benchmark** | `protocol` | `{seeds,split,eval_script,epochs,hardware}` |
| | `failure_modes` | 适用本基准的失败模式 id |

字段数：Paper 12→17、Algorithm 8→10、Module 5→7、Benchmark 11→13。

**不改 `stable_key()`**，历史 `spec_hash` 与 5 套复现产物不受影响。

## 2. 应用层：8 类 → 17 类

原有 8 类（`ResearchQuestion` / `ProblemCategory` / `LeaderboardEntry` /
`MetricDefinition` / `DataContract` / `Evidence` / `Limitation` / `SourcePaper`）保留，
新增 9 类：

| 新节点 | 关键属性 | 关系 |
|---|---|---|
| `Contribution` | statement / kind / novelty_basis / section / claimed_strength | `Paper -DECLARES->`；`-TESTED_BY-> ExperimentArm` |
| `ExperimentArm` | kind(main/baseline/ablation/hyperparam) / name / config / n_seeds | `Paper -RUNS->`；`-ON-> Benchmark` |
| `Assumption` | statement / scope / applicability | `Algorithm -ASSUMES->` |
| `FailureMode` | name / severity / detection / domain_tags | `EvidenceNorm -APPLIES->` |
| `EvidenceNorm` | evidence_type / accepted_metrics / min_fidelity | `Paper -CONFORMS_TO->` |
| `FigureAsset` | fig_label / caption / kind / placement | `Contribution -SHOWN_BY->` |
| `CitationCheck` | doi / venue / year / existence / metadata_ok / context_ok | `Paper -CITES->` |
| `SectionPlan` | section / claims / word_budget | `Paper -OUTLINES->` |
| `ReviewPoint` | axis / attack / response / severity | `Contribution -CHALLENGED_BY->` |

关系数：9 → 20。

## 3. 任务 spec

| 任务 | 类 | 关系 | 挖掘器 | 产物 |
|---|---|---|---|---|
| `reproduction` | 15（复现专用，含运行时类） | 12 | 6 | `app_reproduction.json` |
| `writing` | 14（9 新 + 5 共享） | 16 | 14 | `app_writing.json` |
| `generation` | 别名 → `writing` | — | — | 同 writing |

`ALIASES = {"generation": "writing"}`，旧代码与前端 `task=generation` 仍可用。

## 4. 14 个挖掘器

| 挖掘器 | 输入 | 依赖 |
|---|---|---|
| contributions | `Paper.contributions[]` | S1 落库 |
| experiment_arms | `model_results[].outcome_class` 分组 | S1 落库 |
| assumptions | `Algorithm.assumptions[]` | S1 落库 |
| **failure_modes** | **内置目录**（按 `evidence_type` 选） | 不依赖抽取 |
| **evidence_norms** | **内置映射**（evidence_type → 指标集） | 不依赖抽取 |
| figures | `Paper.figures[]` | S1 落库 |
| citations | `RELATED_TO` 边 | 已有 |
| **section_plans** | **内置章节骨架**（按 evidence_type） | 不依赖抽取 |
| **review_points** | **内置 6 维** × 每条贡献 | 需 contributions |
| metrics / contracts / evidence / limitations / source_papers | 原有 5 个 | 已有 |

**4 个内置规则挖掘器**（加粗）不依赖 LLM 抽取，只要 `evidence_type` 落库就能产出。

## 5. YAML 变更清单

### stages（一次抽取）

| 文件 | 变更 |
|---|---|
| `E1_paper.yaml` | `all_fields` +5（paradigm/evidence_type/evidence_norm/figures/section_map）；模板加「范式与证据类型判定」段 |
| `E2_algorithm.yaml` | +4（assumptions/novelty_basis/is_novel_component/component_role）；模板加「不要全标 novel」约束 |
| `E3_benchmark.yaml` | +2（protocol/failure_modes）；`metrics[]` 增 `contribution_link`；模板加「不编造 split/seeds」约束 |
| `E4/E5/E6` | 未改，prompt 与旧实现逐字节一致 |

### refine（二次抽取）

| 文件 | 目标类 | 挂载关系 |
|---|---|---|
| `R1_contribution.yaml` | Contribution | Paper -DECLARES-> |
| `R2_experiment_arm.yaml` | ExperimentArm | Paper -RUNS-> |
| `R3_assumption.yaml` | Assumption | Algorithm -ASSUMES-> |
| `R4_figure.yaml` | FigureAsset | Contribution -SHOWN_BY-> |
| `R5_citation.yaml` | CitationCheck | Paper -CITES-> |

## 6. 实测

```
真实语义层（S1 未重抽）：writing 任务层 8079 节点 / 2195 断言
  产出 metrics 481 · contracts 604 · evidence 247 · limitations 728
       source_papers 26 · citations 26
  contributions/experiment_arms/assumptions/failure_modes/
  evidence_norms/figures/section_plans/review_points 均为 0（缺 S1 字段）

合成论文（带 S1 字段）：9 类全部产出
  contributions 1 · experiment_arms 1 · assumptions 1 · failure_modes 6
  evidence_norms 1 · figures 1 · citations 1 · section_plans 5 · review_points 6
```

## 7. 迁移与下一步

- 旧 `app_generation.json` 保留不删（历史产物），代码不再生成它；新产物为 `app_writing.json`
- 下一步：按 S1 重抽 4 篇 → 新挖掘器从 0 变为非 0；再用 `refine_run.py --apply` 补 Contribution/ExperimentArm
- 验收：`tests/test_applayer_s2.py`（9 项）+ 全仓 218 项

## 8. S2.5 补充：从 docs/skills 追加的 2 个节点

读完 `docs/skills`（24 份 / 4404 行，含 `APPLICATION_ONTOLOGY_FRAMEWORK.md` 的 60 个类）后，
按 `AlgorithmModule` 的五个特征筛：**多属性 + 多关系 + 抽取时建 + 是判定输入 + 跨论文复用**。

| 候选 | 属性数 | 关系数 | 结论 |
|---|---:|---:|---|
| `ResearchGap` | 6 | 3 | **加**（缺失，且是 novelty 的另一半） |
| `CitedPaper` / `VerifiedPaper` | 12 | 3 | **加**（引用网络基座，当前只有 48 条 RELATED_TO） |
| `ExperimentNode` / `Result` | 3–5 | 2 | 已由 `ExperimentArm` + `model_results[]` 覆盖 |
| `Claim` | 4 | 2 | 已由 `numeric` SAU + `ClaimAnchor` 覆盖 |
| `Assumption` | 2 | 1 | 已有（属性 + 节点） |
| `Tool` / `ToolContract` | 5 | 2 | E5 已抽名字；建节点会与通用库冲突，保持字符串 |
| `Panel` | 3 | 1 | 复合图子图分解，价值低于前三 |
| `FalsificationRecord` / `MCTSRound` / `FailedIdea` | 3–6 | 2–3 | 研究**过程**产物，不是论文事实，不进图 |
| `Gate` / `Verdict` / `LoopBack` / `RunBudget` | 3–5 | 2 | 运行时治理，已有 `gates.py` / `effort_limits` |

### 新增内容

| 项 | 内容 |
|---|---|
| `ResearchGap` | `gap_type`（capability/scale/data/theory/efficiency）/ `statement` / `evidence` / `priority` / `supported_by` |
| `CitedPaper` | `cite_key` / `title` / `doi` / `authors` / `year` / `venue` / `layers[3]` / `existence` / `metadata_ok` / `context_ok` / `context_quote` / `recency_ratio` |
| 关系 | `Paper -IDENTIFIES-> ResearchGap`；`ResearchGap -GAP_SUPPORTED_BY-> CitedPaper`；`ResearchGap -ANCHORS-> Contribution`；`CITES` 改指向 `CitedPaper` |
| `EvidenceNorm` +5 | `sample_size_norm` / `control_design_norm` / `effect_reporting_norm` / `negative_result_norm` / `exemplar_venues` |
| 语义层 +1 | `Paper.gaps[]`（ResearchGap 的抽取来源） |
| 挖掘器 +2 | `gaps`（按 `gap_type+statement` 跨论文归并）、`cited_papers`（RELATED_TO → CitedPaper） |
| YAML +1 | `R6_gap.yaml`（Introduction/Related Work 的 however/remains/fails to） |
