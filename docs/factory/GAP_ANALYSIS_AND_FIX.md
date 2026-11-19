# 对照真实流程（P0–P11）的 Gap 分析与全面修正

> 基准：`REAL_PAPER_PIPELINE.md`（从 MECo / SynFlowNet / AgentDrug / SynCraft 4 篇反推）
> 方法：先精确核对 schema 缺口，再补节点、补维度、重写路由，最后用 MECo 真实数据验证。

## 1. Gap 清单（修正前）

| 阶段 | 需要的节点 | 修正前 | 缺口说明 |
|---|---|---|---|
| P0 问题形式化 | `ProblemFormulation` | ❌ | 只有 `ProblemAnchor`（问题描述），**没有数学定义和旧法缺陷** |
| P1 技术路线 | `TechnicalRoute` | ❌ | `IdeaCandidate` 有 mechanism，**没有模块划分/why_not_other/架构要素** |
| P2 数据构造 | `DatasetSpec` | ❌ | 完全没有——这是真实科研的第一步动手 |
| P3 代码实现 | `CodeArtifact` | ❌ | 只有 `CodeFunction` 抽取（49 个），无模块/入口/冒烟测试 |
| P4 训练 | `TrainingRun` | ❌ | 无超参/曲线/checkpoint |
| P5 Baseline | `BaselineResult` | ❌ | `ExecutionRun` 太泛，不区分 baseline/主方法/同口径 |
| P6 主实验 | `MainResultTable` | ❌ | `Evidence` 是单条数值，**没有「方法×指标」矩阵** |
| P7 消融 | `AblationTable` / `CaseStudy` | ❌ | 无 |
| P8 图表 | `FigurePlan` | ⚠️ | 有 claim_ref，但**缺 figure_kind（架构/结果/case）和 source_data** |
| P9 写作 | `SectionPlan` | ⚠️ | 有 section/claims，但**缺流派模板标识**（编辑序列 5 子节 vs agent 单节） |
| P10 引用 | `CitationVerification` | ❌ | 有 citation-audit skill 但无节点 |
| P11 复现包 | `ReproductionPackage` | ✅ | 已有 |

**汇总**：12 阶段里 9 个缺节点、2 个字段不全、1 个完整。

**另外两个结构性问题**：
1. `Evidence` 字段太弱（只有 quote/kind/paper_id/source），无法承载「数值+协议+seeds+hash」
2. 分类缺 **D7 数据模态**——P2 不知道用什么工具链

## 2. 已修正

### 2.1 新增 10 个节点类（43 → 53 类）

| 类 | 关键字段 | 对应阶段 |
|---|---|---|
| `ProblemFormulation` | `formal_def` / `symbols` / `old_forms` / `limits` / `motivation` | P0 |
| `TechnicalRoute` | `method_family` / `modules` / `why_not_other` / `arch_figure` / `key_challenge` | P1 |
| `DatasetSpec` | `sources` / `modality` / `dedup_rule` / `split` / `sizes` / `train_visible` | P2 |
| `CodeArtifact` | `modules` / `entrypoints` / `deps` / `smoke_test` / `repo_ref` | P3 |
| `TrainingRun` | `hyperparams` / `loss_curve` / `checkpoint` / `seed` / `converged` | P4 |
| `BaselineResult` | `method` / `metrics` / `protocol` / `same_setting` | P5 |
| `MainResultTable` | `table_label` / `methods` / `metrics` / `values` / `n_seeds` / `significance` | P6 |
| `AblationTable` | `components` / `delta` / `protocol` | P7 |
| `CaseStudy` | `input` / `output` / `claim_ref` / `figure_ref` | P7 |
| `CitationVerification` | `cite_key` / `existence` / `metadata_ok` / `context_ok` | P10 |

### 2.2 扩展 3 个既有类

| 类 | 新增字段 | 为什么 |
|---|---|---|
| `Evidence` | `run_id` / `metric` / `model` / `value` / `unit` / `protocol` / `seeds` / `sha256` / `table_ref` | 从「一句引文」升级为「可复算数值」 |
| `FigurePlan` | `figure_kind`(必须) / `source_data` / `script` | 区分架构图/结果图/case图，并绑定数据来源 |
| `SectionPlan` | `template_family` / `subsections` / `has_equation` / `has_algorithm_block` | 按流派选章节模板 |

### 2.3 新增 D7 数据模态维度

```
FORM_TO_MODALITY: SMILES→smiles / 3D坐标→3d / 图→graph / 序列→sequence / 文本→text
从 Paper --EVALUATED_ON--> Benchmark.input_form 聚合
实测：smiles 22 / graph 9 / text 20 / sequence 1
```

**用途**：P2 据此选工具链（smiles→RDKit+RDChiral；3d→OpenBabel；graph→PyG）。

## 3. 重写路由（phase_router_v2）

| 阶段 | 读哪个维度 | 路由输出 |
|---|---|---|
| P0 | D1 流派 | `form`: 有公式流派(edit/gflownet/retro/diffusion) → `math_definition+limits`；llm_agent → `problem_statement+workflow` |
| P1 | D1 | `modules` / `why_not` / `arch_elems` / `key_challenge` 模板 |
| P2 | **D7 模态** | 工具链 + 去泄漏规则 |
| P3 | D1 | 模块清单 |
| P6 | D2 证据 | 指标集 |
| P7 | P1 的 modules | 消融对象 = 创新组件 |
| P8 | D1 | 图类型（gflownet 不做 case 图） |
| P9 | D5 venue × D1 | 章节模板（12 节 / 9 节 / 6 节 / Nature 5 节） |
| P11 | D6 交付 | 复现包必需项 |

## 4. 用 MECo 真实数据验证

**profile**：`edit_sequence / experimental / design / NeurIPS / code+data / smiles`

| 阶段 | 路由输出 | MECo 论文实际 | 是否吻合 |
|---|---|---|---|
| P0 | `math_definition+limits` | 3.1 有 `Mo=F(Mi,T)` + 两条局限 | ✅ |
| P1 | modules=[edit_generator, edit_executor] | 3.2 reasoning LLM + code LLM 两模块 | ✅ |
| P2 | rdkit/rdchiral + `Tanimoto<0.6` | 4.1 去泄漏 Tanimoto<0.6 | ✅ |
| P6 | success_rate/validity/similarity/constraint | Table1 用 SR%/VR%/Sim/CR% | ✅ |
| P7 | 消融 [edit_generator, edit_executor] | 4.3 提升实验 + 4.4 case | ✅（组件级） |
| P9 | 12 节含 method.problem_formulation/data/training/benchmark | 3.1–3.5 + 4.1–4.4 | ✅ |
| P11 | code/data/env/script | Code availability | ✅ |

**路由与论文实际结构逐项吻合**，说明从 4 篇反推的模板是对的。

## 5. 修正后仍未解决的（诚实清单）

| 问题 | 影响 | 为什么没修 |
|---|---|---|
| **P2–P7 无真实执行** | 节点和路由有了，但**没有真的造数据/写代码/跑实验** | 需要真实算力和用户的具体研究目标，不是 schema 能解决的 |
| `data_modality` 有 20 篇判成 text | 可能误判（无 EVALUATED_ON 边时默认） | 需从原文补充判定规则 |
| P7 消融对象只到模块级 | 组件内部超参消融（如 AgentDrug 的迭代次数）没覆盖 | 需要更细的组件粒度 |
| P5 baseline 集合没有具体方法名 | 只知「要复现 baseline」，不知「复现哪几个」 | 需从同流派社区的 SOTA 查询 |
| P8 图表只有计划，无生成脚本 | 图要真画出来 | 需要实际绘图代码 |

## 6. 结论

**这次修正解决的是「承载结构」**：
- 12 个阶段现在都有对应节点（之前 9 个空缺）
- 路由能从论文画像推出「这阶段该做什么、用什么工具、过什么门」
- 用 MECo 验证，路由输出与论文实际逐项吻合

**没解决的是「真实执行」**：
- P2–P7 需要真的动手（造数据、写代码、跑实验），这是人的工作，schema 只能记录和门控
- 当前系统能做到「告诉你该做什么、检查你做了没有、把结果组织成论文」，不能替你做实验

**下一步优先级**：
1. 把 P2 `DatasetSpec` 接真实数据脚本（去泄漏检查可自动化）
2. 把 P6 `MainResultTable` 接 CSV→LaTeX（数值已有，缺表格生成）
3. 把 P9 `SectionPlan` 按模板真正生成章节骨架
