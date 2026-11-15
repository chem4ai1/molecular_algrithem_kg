# 代码复现应用层蓝图：图接地的规格驱动复现（GGR）

> **定位**：本文是「基于已有语义层图做论文代码复现」的应用层设计依据，面向后续实现智能体。
> **调研基准日**：2026-11-14　**代码基线**：`ARCHITECTURE.md`（2026-11-13）+
> `md/SEMANTIC_LAYER_ARCHITECTURE.md`（2026-11-14）+ `md/APPLICATION_TASK_LAYERS.md`（2026-11-14）
> **语义层依据**：`md/TBOX_INVENTORY.md`（legacy 清点）+ `capfactory/semantic/tbox_v4.py`（v4.1 权威）
> **参考框架**：`/home/zengshuxin/xKG-main/SciForge-OSS-master`（S2 协议 / skills）

---

## 0. 一页摘要

**文献共识（2024→2026）**：所有有效系统都不是「论文 PDF → 直接吐代码」，而是
**论文 → 结构化中间规格 → 代码 → 执行反馈 → 语义对齐判定**。中间规格的粒度决定复现质量。

**2026 的关键转折**：从「能不能跑」转向「跑的是不是论文说的东西」。SA-Bench 定义
`semantic drift`，最强配置（Claude + PaperCoder）SAU 得分仅 **0.301/1.0**；结论是
**面向可执行性的 scaffold 对科学复现帮助有限，必须做语义规格验证**。这恰好是我方
「先建语义层图、再复现」路线的外部验证。

**我方现状**：已有 6001/7460 语义层图（含 AST 对齐的 `CodeFunction`）、任务驱动应用层、
R0–R6 复现 DAG、门系统与 events 重放。缺的不是「骨架」，而是三件事：
1. **R5 目前不真跑**（`dry` 模式，R6 诚实 BLOCKED）；
2. **没有可验证规格（SAU）**，无法检测语义漂移；
3. **没有执行反馈闭环与 paper lineage**。

**方案**：提出 **GGR（Graph-Grounded Reproduction）**——把应用层图编译成
`ReproSpec`（5 类语义对齐单元 SAU），在既有 R0–R6 七阶段内补齐 4 个子步骤，
不新增语义层类、不污染语义层图。

---

## 1. 文献全景（2024–2026）

### 1.1 三条演进线

```
2024  能不能把别人仓库跑起来        CORE-Bench / SUPER / MLAgentBench
2025  能不能从论文生成可运行仓库    PaperBench / PaperCoder / SciReplicate-Bench
                                  / AutoP2C / ResearchCodeAgent / AutoReproduce
2026  生成的代码是否忠实于论文      SA-Bench / PRBench / Artisan
```

### 1.2 逐篇解析

#### ① CORE-Bench（2024-09, arXiv 2409.11363, v2 2026-06）
- **任务**：给定论文 + 代码 + 数据，复现结果。**270 个任务 / 90 篇论文 / 3 学科**（CS、社科、医学），三档难度 + 语言/视觉-语言两类输入。
- **概念节点**：`task capsule`（论文 + capsule 依赖 + 目标结果），不给结构化方法规格。
- **代码解析**：不生成代码，重点是**环境安装、依赖解析、找到正确入口脚本、执行**。
- **推理**：通用 agent（AutoGPT）与专用 agent（CORE-Agent）两基线；并行评测框架。
- **结果**：最难档最好 **21%**。
- **可借鉴**：环境/入口脚本解析是复现第一道物理门槛；三档难度应映射为我方 `effort=dry/lite/full` 之外的「输入完备度」维度。

#### ② SUPER（2024-09, arXiv 2409.07440, EMNLP 2024）
- **任务**：从真实 ML/NLP GitHub 仓库**配置并执行**任务。45 个端到端问题 + 152 个子问题 + 602 个自动生成问题。
- **概念节点**：`end-to-end problem` / `sub-problem`（专门针对环境配置、依赖、数据准备、执行四类挑战）。
- **代码解析**：仓库级探索，读 README、requirements、脚本入口。
- **结果**：GPT-4o 端到端仅 **16.3%**。
- **可借鉴**：把「跑不起来」拆成可单独评分子任务——对应我方 `StaticCheck` / `CompileReport`。

#### ③ PaperBench（2025-04, arXiv 2504.01848, ICML 2025）
- **任务**：从零复现 **20 篇 ICML 2024 Spotlight/Oral**，理解贡献 + 建代码库 + 执行实验。
- **概念节点**：★ **层次化 rubric 树**——与论文作者共同把每篇复现任务分解为**可单独打分的子任务**，共 **8,316** 个。这是文献里最接近「TBox 实例化」的设计。
- **推理/评分**：`SimpleJudge`（LLM judge），并单独做了 judge 的 benchmark；`PaperBench Code-Dev` 变体只评静态代码、不执行。
- **结果**：Claude 3.5 Sonnet (New) + 开源 scaffold **21.0%**，o1 13.2%；人类 ML 博士生 48h/3 次尝试 **41.4%**。
- **可借鉴**：**rubric 树 = 可验证规格树**。我方应把 `AlgorithmModule` 链编译成同类层次化检查单，而不是一个整体分数。

#### ④ Paper2Code / PaperCoder（2025-04, arXiv 2504.17192, ICLR 2026；v5 2026-02）
- **任务**：无官方代码时，从论文生成完整可运行仓库。
- **★ 三阶段 + 专用智能体**：
  1. **Planning**：高层路线图 → 系统架构图 → 文件依赖 → 配置文件
  2. **Analysis**：逐文件解释实现细节（interpret implementation-specific details）
  3. **Generation**：按依赖顺序、模块化生成代码
- **概念节点**：`roadmap` / `architecture diagram` / `file dependency graph` / `config` / `per-file logic spec`。
- **推理**：多智能体协作 + 依赖感知的自顶向下分解；不执行、不 debug。
- **评估**：模型打分 + **原论文作者人工评估**（以作者发布仓库为 ground truth）。PaperBench Code-Dev 上 PaperCoder(o3-mini) **45.1%**。
- **可借鉴**：`CODE_PLAN.json` 应是**依赖有序的文件/模块图**，不是一段 prompt。

#### ⑤ SciReplicate-Bench / Sci-Reproducer（2025-03, arXiv 2504.00255, v2 2025-08）
- **任务**：从 NLP 论文的算法描述生成代码。**100 任务 / 36 篇 2024 NLP 论文**，带详细标注与测试用例。
- **★ 双智能体**：`Paper Agent`（理解算法概念、综合文献） + `Code Agent`（从仓库检索依赖、实现 API）。
- **概念节点**：★ **reasoning graph**——从代码注释与结构导出推理图，用「生成图 vs 参考图」相似度衡量算法理解。
- **代码解析**：仓库依赖检索 + API 定位；指标除 execution accuracy 外还有 `repository dependency/API recall`、CodeBLEU。
- **结果**：最好 **39%** execution accuracy；主要障碍是**论文算法描述缺失或前后不一致**。
- **可借鉴**：`AlgorithmModule.inputs/outputs/mechanism` 正是 reasoning graph 的天然节点；`MODULE_IMPLEMENTED_BY` 是 API recall 的天然标注。

#### ⑥ AutoP2C（2025-04, arXiv 2504.20115）/ ResearchCodeAgent（arXiv 2504.20117）
- **任务**：从**多模态**论文（正文 + 公式 + 图 + 表）生成完整仓库；AutoP2C 四阶段多智能体，在 8 篇论文上验证。
- **概念节点**：多模态内容块（equation / figure / table）→ 代码模块。
- **可借鉴**：论文里公式/图的证据应进 `Evidence` 与 `Formula`（当前在 `application_hints.json` 未节点化）。

#### ⑦ AutoReproduce（2025-05, arXiv 2505.20662v4 2026-04, ACL 2026 Main）—— **与本项目最相关**
- **任务**：给定论文 + 实验指令（TASK / MODEL / METRIC），端到端生成**可执行**实验代码。
- **★ 三阶段 / 双智能体**（Research Agent 管文本、Code Agent 管代码）：
  1. **Literature Review**：三级层次化摘要（全文 → 方法细节含公式 → 实验设置）；用 **MinerU** 把 PDF 转 Markdown；可选视觉结构图。
  2. **★ Paper Lineage**：从参考文献选 top-k（默认 **3**）相关论文（优先主实验里的对比基线）→ arXiv API 取全文 → 找关联仓库 → GitHub 克隆 → Code Agent 按任务筛出关键文件 → 组成 `<summary, code>` 元组，作为「领域隐式实现惯例」范例。
  3. **Code Development**：三小步
     - **Data Acquisition**：标准基准走库、定制数据走预处理流水线；★ **mini-batch 采样执行分析代码**，推断 tensor shape / dtype，避免运行期崩。
     - **Method Replication**：Code Agent 生成并 debug；Research Agent 用方法摘要**校验代码**并动态更新摘要；循环至对齐。
     - **Experiment Execution**：完整实验脚本加 `break` 早退做 dry run；最后重构清理调试代码。
  - **★ 执行反馈机制**：Docker（Python + PyTorch/NumPy）；错误 → 先分析 traceback → **`EDIT N M <new code>` 定点替换行 N..M**（不整文件重生成）；最多 20 次 debug，实测 5–8 次收敛；单实验约 **$1.87**（o3-mini），A100。
- **评估 ReproduceBench**：13 篇人工核验实现；**5 个指标**：
  - `Align-Score` 三层：Paper-Level（从论文抽 5 个关键点）/ Code-Level（对照参考实现，4 维×25 分）/ **Mixed-Level**（关键点 + 参考代码一起给 judge，与人类判断相关性最高 0.81–0.83）
  - `Exec-Score`：`Exec Rate` + `Perf Gap = (1/n)Σ|P_ref−P_agent| / max(P_ref, P_agent)`
- **结果**：Gemini-2.5-Pro 最佳 **Exec Rate 94.87% / Perf Gap 19.72% / Mixed 77.56**；
  消融：去掉 Paper Lineage → Mixed 63.15 / Gap 39.59；去掉 Debug+Refine → **Gap 88.78**；
  PaperBench Code-Dev **48.5%**（加视觉图 49.6%）。
- **可借鉴（最高优先级）**：paper lineage、mini-batch 属性推断、EDIT 定点修复、Research/Code 双 agent 交叉校验、Mixed-Level 评分。

#### ⑧ AI Scientist-v2（2025）/ Agent Laboratory（2025）
- 不是复现框架，但贡献了**执行侧推理机制**：agentic tree search（best-first 实验树）、`code_model` 生成 + `feedback_model` 分析错误 + 迭代精化、VLM 解读图、并行 worker + 自动 debug。Agent Laboratory 三阶段（文献综述 → 实验 → 报告）常被当基线。
- **可借鉴**：把「调试」建模成**树搜索**而非线性重试，可与我方 `loopback` 预算结合。

#### ⑨ SA-Bench（2026-08, arXiv 2608.24252, EMNLP Findings 2026）—— **2026 最重要的诊断**
- **任务**：诊断 `semantic drift`：生成代码静默偏离论文规格。
- **★ 概念节点**：**SAU（Semantic Alignment Unit）** = 把论文规格分解为**原子且可验证的实现声明**；30 篇 ICLR/ICML/NeurIPS 2025 论文 → **1,491 条 SAU**，5 个 ML 领域。
- **四类漂移维度**：`numerical` / `methodological` / `protocol` / `ordering`。
- **评估**：12 组配置（4 模型 × 3 scaffold），共 360 次评估；最强 Claude+PaperCoder **均值 0.301/1.0**，全体均值 **0.221**。
- **失败分类**：多数要求"尝试了但实现错"，`implementation mismatch` 与 `stub（空实现）` 是零分主因。
- **★ 结论**：**面向可执行性的 scaffold 对科学复现帮助有限；缩小差距要靠语义规格验证**。
- **可借鉴**：SAU 就是我方应用层缺少的那一层。本方案 §4 把它落成 5 类。

#### ⑩ PRBench（2026-03, arXiv 2603.27646）/ Artisan（2026-02, arXiv 2602.10046）
- **PRBench**：物理领域 30 个专家策划任务；四阶段任务构建（论文筛选 → 参考实现 → 任务规范 → 独立专家验证）；输出标准化 CSV 便于定量比对；「agentic evaluation」多智能体评估而非静态精确匹配。
- **Artisan**：把 artifact evaluation 形式化为**代码生成任务**——产出**可独立执行的 reproduction script**（可调用既有代码、修复过时代码、把执行输出格式化成表格），配两层 judge。
- **可借鉴**：复现产物必须是**可独立重跑的脚本/报告**，而不是 agent 的自述结论；对应我方 `REPRO_REPORT.md` + `events.ndjson`。

---

## 2. 横向总结：四个问题的答案

### 2.1 用了什么样的「概念节点」

| 概念节点 | 出现于 | 粒度 | 是否可验证 |
|---|---|---|---|
| Rubric 子树（8,316 项） | PaperBench | 任意细 | ✅ 单独打分 |
| Roadmap / 架构图 / 文件依赖 / config | PaperCoder | 仓库级 | ❌ 结构件 |
| Reasoning graph（注释+结构导出） | Sci-Replicator | 算法逻辑级 | ✅ 图相似度 |
| `<summary, code>` lineage 元组 | AutoReproduce | 跨论文惯例 | ❌ 上下文范例 |
| 5 个关键复现点 / 4 维代码对照 | ReproduceBench | 论文级 + 代码级 | ✅ mixed-level judge |
| ★ SAU（原子实现声明） | SA-Bench | **最细，逐条可判** | ✅ |
| Task capsule / sub-problem | CORE-Bench / SUPER | 任务级 | ✅ 执行结果 |
| Reproduction script | Artisan | 产物级 | ✅ 可独立重跑 |

**趋势**：节点从「文档结构件」（2025 上）→「原子可验证实现声明」（2026）。

### 2.2 怎么解析代码

| 方式 | 代表 | 具体做法 |
|---|---|---|
| 仓库上下文检索 | Sci-Replicator / SUPER / AutoReproduce | 读 README、requirements、筛关键文件、定位 API 与依赖；指标含 repo dependency/API recall |
| AST / 结构导出 | Sci-Replicator（reasoning graph）、我方 `CodeFunction` | 从注释与结构导出推理图；AST 提函数签名/docstring/params |
| 执行期属性推断 | ★ AutoReproduce mini-batch | 生成并执行分析代码，采样小批量推断 shape/dtype |
| 静态检查 | PaperCoder 依赖图 / SciForge `StaticCheck` | 文件依赖顺序、语法、import 白名单 |
| 定点编辑 | ★ AutoReproduce `EDIT N M` | 错误归因 → 替换行区间，不整文件重生成 |
| 源码对照评分 | ReproduceBench code-level | 生成代码 vs 参考实现，逐层/逐模块对比 |

### 2.3 怎么做推理

| 机制 | 代表 | 说明 |
|---|---|---|
| 层次化规划 | PaperCoder | planning → analysis → generation，依赖感知自顶向下 |
| 双 agent 交叉校验 | AutoReproduce / Sci-Reproducer | 一个管文本规格、一个管代码；Research Agent 用摘要校验生成代码并回写摘要 |
| 隐式知识补全 | ★ AutoReproduce Paper Lineage | 从被引论文与仓库恢复「论文没写的实现惯例」 |
| 执行反馈闭环 | AutoReproduce / AI Scientist-v2 | traceback → 分析 → EDIT → 重跑；tree search 版为 best-first 实验树 |
| 三态 Critic | ★ SciForge S2 ladder | BAD / ENGINEER(≤2 轮) / GOOD；GOOD 才进 full set，且必须严格优于 baseline |
| LLM judge | PaperBench SimpleJudge / AutoReproduce mixed-level | 关键点 + 参考代码联合评分；与人类相关性 0.81–0.83 |
| 语义对齐判定 | ★ SA-Bench | 逐 SAU 判四类 drift，而非整体"能跑吗" |
| 事件重放 | SciForge / 我方 `resume_repro` | `events.ndjson` 为 durable truth，`RUNSTATE` 为派生快照 |

### 2.4 通用步骤（跨文献归纳的 8 步）

```
S1 规格化    PDF→MD（MinerU）→ 抽方法/实验/数值 → 结构化规格
S2 补隐式    参考文献 lineage / 仓库范例 / 词表与实现惯例
S3 规划      路线图 + 架构 + 文件依赖 + 配置（依赖有序）
S4 数据准备  基准加载或预处理；mini-batch 采样推断 shape/dtype
S5 代码生成  按模块/文件生成；有仓库时先 AST 审计再补
S6 执行调试  toy/subset → full；traceback → EDIT → 重跑；budget 与 loopback
S7 数值比对  实跑值 vs 论文/SOTA 基线；direction + 单位 + 相对偏差
S8 语义判定  逐 SAU 判 drift；mixed-level align score；claim anchor + 可独立重跑脚本
```

**失败模式（文献一致）**：数据 shape 不一致、超参/训练配置论文没写、模块实现"看起来对但逻辑错"、stub 空实现、缺依赖/入口脚本。

---

## 3. 我方现状与口径澄清（实现前必读）

### 3.1 三层 TBox 并存，别拿错清单

| 层 | 权威文件 | 规模 | 用途 |
|---|---|---|---|
| **语义层 v4.1** | `capfactory/semantic/tbox_v4.py` | **6 类 / 9 关系**，图 `batch10_semantic_v4.json` 6001 节点 / 7460 断言 | 客观事实，唯一事实源 |
| **应用层 v1** | `capfactory/applayer/tbox.py` + `tasks.py` | 8 类 / 9 关系；`reproduction` 任务 6 类 / 7 关系 | 任务派生视图，`app_reproduction.json` 8300/10260 |
| **legacy TBox** | `ontology/tbox.py` + **`md/TBOX_INVENTORY.md`** | 46 类 / 105 关系（active 16/18，reserved 30/87） | 判定入口 `check_domain_range()` |

> ⚠️ 用户指定的 `TBOX_INVENTORY.md` 是 **legacy 全量清点**，不是当前语义层定义。
> 本方案遵循「**语义层只放客观事实 / 应用层只放任务派生 / legacy 只做判定**」三原则，
> 复现应用层**不新增语义层类**，只从 reserved 升级少量任务类。

### 3.2 现有节点 → 复现语义的完整映射（无需造新词）

| 复现概念 | 现有节点 | 所在层 | 可提供字段 |
|---|---|---|---|
| 复现目标论文 | `Paper` | 语义层 | `research_problem / domain / problem_category / why_hard / relation_hints` |
| 方法规格 | `Algorithm` | 语义层 | `mechanism / problems_solved / task_type / flow_family / limitations` |
| ★ 方法原子步骤 | `AlgorithmModule`（=legacy `AlgorithmStep`） | 语义层 | `name / mechanism / inputs / outputs / formula`；共 2856 个 |
| 环境与依赖 | `CodeRepository` | 语义层 | `repo_url / local_path / license / is_original_repo`；仅 10 个 |
| ★ 代码落地证据 | `CodeFunction` | 语义层 | AST：`name / signature / params / returns / purpose / func_type / lineno`；49 个 |
| 数据/协议规格 | `Benchmark` | 语义层 | `input_form / output_form / n_samples / scale / metrics[] / model_results[] / sota_by_metric` |
| 指标与方向 | `MetricDefinition` | **应用层** | `name / direction / unit`（447 个） |
| 目标数值/基线 | `LeaderboardEntry` | **应用层** | `benchmark_id / metric_id / value / rank / sota_claimable`（247 个） |
| 输入/输出契约 | `DataContract` | **应用层** | `input_form / output_form / metrics`（604 个） |
| 逐格溯源 | `Evidence` | **应用层** | `quote / paper_id / provenance`（247 个） |
| Paper Lineage | `SourcePaper` + `Limitation` | **应用层** | 26 / 728 个；配合 `RELATED_TO`、`SUBCLASS_OF` |
| 实跑观测 | `Observation` / `MetricObservation` | legacy active | `value / unit / metric` |
| 声明锚 / 静态检查 / 编译 / 实验结果 | `ClaimAnchor` / `StaticCheck` / `CompileReport` / `ReproductionResult` / `EvaluationResult` / `MethodLock` / `CodeGenerationTask` | **reserved** | 按 §3.4 升级 |

### 3.3 关系映射

| 复现语义 | 现有关系 | 层 | 条数 |
|---|---|---|---|
| 论文 → 方法 | `PROPOSES_METHOD` | 语义层 | 1666 |
| 方法 → 模块 | `HAS_MODULE` | 语义层 | 2862 |
| 模块 → 函数（代码落地） | `MODULE_IMPLEMENTED_BY` | 语义层 | 758 |
| 仓库 → 函数 | `HAS_FUNCTION` | 语义层 | 49 |
| 论文/算法 → 基准 | `EVALUATED_ON` | 语义层 | 984 |
| ★ Lineage / 谱系 | `RELATED_TO` + `SUBCLASS_OF(kind, evidence)` | 语义层 | 48 / 1083 |
| 基准 → 榜单行 | `HAS_ENTRY` / `USES_METRIC` | 应用层 | 2800 应用关系内 |
| 榜单行 → 证据 | `SUPPORTED_BY` | 应用层 | 同左 |

> ⚠️ **命名双轨（必须修）**：`sciforge/repro/phasegraph.json:18` 的 reads 写
> `REALIZED_BY / IMPLEMENTS_MODULE`（legacy 名），而语义层实际边是
> `MODULE_IMPLEMENTED_BY / HAS_MODULE`（`SEMANTIC_LAYER_ARCHITECTURE.md:49-59`）。
> `planner.py:63` 又绕开图、改读 `relation_index.json` 的 `algorithm_code` 链。
> 三套口径并存会让门判定与真实图脱节。

### 3.4 建议从 reserved 升级为「复现应用层 active」的类（8 个）

| 类 | 用途 | 对应文献 |
|---|---|---|
| `MethodLock` | 冻结方法规格（SAU_method 的哈希） | SciForge method-registry |
| `CodeGenerationTask` | 依赖有序的代码生成任务 | PaperCoder planning |
| `StaticCheck` | 语法/import/依赖检查 | PaperCoder / SUPER |
| `CompileReport` | 环境安装与 smoke 结果 | CORE-Bench / SUPER |
| `ExperimentNode` | 一次 toy/full 实验运行 | SciForge S2 ladder |
| `ReproductionResult` | 实跑数值 | AutoReproduce Exec-Score |
| `EvaluationResult` | 逐 SAU 判定 | SA-Bench / PaperBench rubric |
| `ClaimAnchor` | `code_sha / inputs_sha / outputs_sha` 三锚 | SciForge result-to-claim |

**新增应用关系（4 条，只写 `app_reproduction.json`）**：
`VERIFIES`（EvaluationResult → SAU/AlgorithmModule）、`DEVIATES_FROM`（ReproductionResult → LeaderboardEntry）、
`LINEAGE_OF`（SourcePaper → Paper）、`GENERATED_BY`（CodeGenerationTask → AlgorithmModule）。
> 不新增语义层关系；每条带 `layer="application"` + `task="reproduction"` + `derived_from`。

### 3.5 现有 R0–R6 复现框架（本方案的宿主）

`capfactory/sciforge/repro/phasegraph.json` 七阶段、`gates.py` 七门、`runner.py` 事件重放：

| 阶段 | 门 | 当前状态 |
|---|---|---|
| R0 intake-paper | `paper_core_present` | 读 `Paper` 三字段 |
| R1 resolve-method | `method_grounded` | 读 `PROPOSES_METHOD` + mechanism |
| R2 ground-code | `code_located` | 读 `HAS_CODE` + relation_index |
| R3 bind-data | `data_bound` | 读 `EVALUATED_ON` + input/output_form |
| R4 fix-metrics | `metrics_comparable` | 读 metrics/direction/SOTA |
| R5 execute | `verdicts_valid` | ★ **dry 模式不执行**（`runner.py:44-46`） |
| R6 verify-and-replay | `reproduction_close` | ★ 无实跑值时诚实 BLOCKED；有值时按 5% 偏差判 PARTIAL |

`effort_limits`：`dry 60s / lite 3600s / full 86400s`；`loopback` L1(no_code→R2)、L2(deviation→R5)，预算各 1。

**结论**：骨架与 SciForge 风格门系统已就位，方案是「**在骨架内补语义规格与执行闭环**」，不另起炉灶。

---

## 4. GGR 框架：Graph-Grounded Reproduction

### 4.1 分层

```
语义层（只读） 6001/7460
   ↓ build_task_layer("reproduction")            已有
应用层 app_reproduction.json 8300/10260
   ↓ compile_reprospec(paper_id)                 ★ 本方案新增
ReproSpec（5 类 SAU 的可验证规格树）
   ↓ R0–R6+ 七阶段（宿主 phasegraph）            已有骨架
执行产物 + 逐 SAU 判定 + claim anchor
   ↓ 只写 app_reproduction.json / repro_runs/     不回写语义层
```

### 4.2 `ReproSpec` 数据契约

```python
@dataclass
class SAU:                       # Semantic Alignment Unit（对齐 SA-Bench）
    id: str                      # sau:{aid}:{kind}:{n:03d}
    kind: str                    # numeric|method|protocol|ordering|code_grounding
    statement: str               # 原子可验证声明（一句话）
    source_node_ids: List[str]   # 语义层节点 id（derived_from）
    evidence_ids: List[str]      # 应用层 Evidence id
    check: dict                  # {"op":..., "target":..., "tolerance":...}
    required: bool
    provenance: str              # extracted | derived | inferred

@dataclass
class ReproSpec:
    paper_id, arxiv_id, spec_hash
    sau: List[SAU]
    method_lock: dict            # 方法 SAU 的哈希冻结
    data_contract: dict          # shape/dtype/split/n_samples
    metric_plan: dict            # name/direction/unit/baseline
    lineage: List[dict]          # Paper Lineage 的 <summary, code> 元组
    code_plan: dict              # 依赖有序的文件/模块图
    budgets: dict                # effort + loopback + debug_tries
```

### 4.3 五类 SAU 与节点来源（★ 核心映射表）

| SAU kind | 从哪些节点编译 | 检查什么 | 文献依据 |
|---|---|---|---|
| `method` | `Algorithm` + 每个 `AlgorithmModule`（mechanism/inputs/outputs/formula） | 每个模块是否在生成代码中有对应实现；机理是否一致（非仅同名） | SA-Bench methodological / PaperCoder analysis |
| `code_grounding` | `MODULE_IMPLEMENTED_BY` → `CodeFunction`（signature/params/func_type） | 生成的函数是否命中原仓库符号；`stub` 检测 | Sci-Replicator API recall / SA-Bench stubs |
| `protocol` | `Benchmark` + `DataContract` + `Evidence` | 数据集、split、预处理、epoch、评测流程是否一致 | SA-Bench protocol / AutoReproduce data acquisition |
| `numeric` | `LeaderboardEntry` + `MetricDefinition` + `Benchmark.model_results` | 实跑值 vs 论文值/SOTA，按 `direction` 与 `unit` 归一 | SA-Bench numerical / PaperBench rubric |
| `ordering` | `AlgorithmModule` 的 `inputs/outputs` 依赖闭包 + `SUBCLASS_OF(kind)` | 模块执行顺序、数据流先后、基线谱系顺序 | SA-Bench ordering / Sci-Replicator reasoning graph |

**编译规则**：全部从图读，不调 LLM；LLM 只在 §5 的 R1.5/R4.5 做判定，不改变 SAU 集合。
`spec_hash = sha256(规范化后的 SAU 列表)`，写进 `MethodLock`；重跑同 hash 直接复用。

### 4.4 为什么这套映射适合我方

- 文献里 PaperBench 的 rubric 树是**人工与作者共建**的；我方的 rubric 树可以**从已有 2856 个 `AlgorithmModule` + 758 条代码边 + 604 个 `Benchmark` 自动编译**，边际成本近零。
- SA-Bench 的 SAU 是人工标注 1491 条；我方 `SAU` 天然带 `source_node_ids` 与 `evidence_ids`，**每条判定都可回溯到图和原文**。
- AutoReproduce 的 paper lineage 需要现场 arXiv/GitHub API；我方 `RELATED_TO` / `SUBCLASS_OF` / `SourcePaper` 已经是**离线建好的 lineage**。
- 我方 `CodeFunction` 是 AST 事实（`NON_LLM`），正好补上 Sci-Replicator「依赖/API recall」缺的标注。

---

## 5. R0–R6+ 逐步流程（宿主 `phasegraph.json`，括号为新增子步骤）

### R0 `intake-paper` — 锁定论文与预算
- **输入节点**：`Paper`；门 `paper_core_present`（已有）
- **新增 R0.5 `compile_reprospec`**：从应用层图编译五类 SAU，写 `REPRO_SPEC.json` + `SAU_LIST.json`；算 `spec_hash`
- **产物**：`RUN_BUDGET.json`、`PROBLEM_HASH.txt`、`REPRO_SPEC.json`、`SAU_LIST.json`
- **门增强**：`sau_count(kind) > 0` 至少覆盖 method/numeric；否则 BLOCKED

### R1 `resolve-method` — 方法规格 + Lineage
- **输入**：`PROPOSES_METHOD` → `Algorithm` → `HAS_MODULE` → `AlgorithmModule`
- **新增 R1.5 `paper_lineage`**（AutoReproduce）：沿 `RELATED_TO` / `SUBCLASS_OF(kind=extends|improves)` / `SourcePaper` 取 top-k（默认 3，优先主实验基线），组 `<summary, code>` 元组；有 `CodeRepository` 的补 `CodeFunction` 列表
- **新增 R1.6 `method_lock`**：冻结 method SAU 哈希，结果出来后不得改规格
- **产物**：`METHOD_CARD.json`、`LINEAGE.json`、`METHOD_LOCK.json`（写 `MethodLock` 节点）
- **门**：`method_grounded` + 「每个 method SAU 有 `source_node_ids`」

### R2 `ground-code` — 代码定位与代码计划
- **输入**：`HAS_CODE` → `CodeRepository` → `HAS_FUNCTION` → `CodeFunction`；`MODULE_IMPLEMENTED_BY`
- **有仓库**（对应 Sci-Replicator / CORE-Bench）：AST 审计 → 定位入口、依赖、requirements → 生成 `CODE_PLAN`（依赖有序）；用 `CodeFunction.purpose/params/returns` 做 API recall 标注
- **无仓库**（对应 PaperCoder）：planning 三件套 `roadmap / architecture / file_dependencies / config`，按 `AlgorithmModule.inputs→outputs` 排模块顺序
- **产物**：`CODE_PLAN.json`、`STATIC_CHECKS.json`（`StaticCheck` 节点）、`AST_INDEX.json`
- **门**：`code_located` + `static_checks.pass`；`loopback L1(no_code)` 预算 1

### R3 `bind-data` — 数据契约 + 属性推断
- **输入**：`EVALUATED_ON` → `Benchmark`；应用层 `DataContract` / `Evidence`
- **新增 R3.5 `mini_batch_probe`**（AutoReproduce）：生成并执行 20 行分析代码，实测 shape/dtype/值域，写回 `DATA_PLAN.shape`；与 `Benchmark.input_form/output_form` 冲突即记 `protocol` SAU 违规
- **产物**：`DATA_PLAN.json`、`SHAPE_PROBE.json`
- **门**：`data_bound` + shape 与契约一致

### R4 `fix-metrics` — 指标、基线、混合级校验规格
- **输入**：`Benchmark.metrics[]` / `model_results[]` / `sota_by_metric`；应用层 `MetricDefinition.direction` / `LeaderboardEntry`
- **新增 R4.5 `align_rubric`**（AutoReproduce Mixed-Level）：为每类 SAU 生成「关键点 + 参考代码片段」的判定材料；参考代码来自 `CodeFunction`（有仓库）或 lineage 元组
- **产物**：`METRIC_PLAN.json`、`SOTA_BASELINE.json`、`ALIGN_RUBRIC.json`
- **门**：`metrics_comparable`（`direction_source=heuristic` 保留 PARTIAL）

### R5 `execute` — 真跑（当前最大缺口）
- **★ 必须实现 `lite/full` 执行器**，`dry` 仅用于回归
- **顺序**（SciForge S2 ladder + AutoReproduce）：
  1. `subset/toy` 复现 baseline（同协议、记 seed）→ 无 baseline 复现则不进 ladder
  2. `subset` 跑 candidate → `decide(baseline, candidate, direction)` 三态 Critic
  3. `BAD` → 丢弃；`ENGINEER` → 调参 ≤2 轮；`GOOD` → 进 `full`，且 **full 必须严格优于**（ties fail）
  4. 错误 → traceback 归因 → **`EDIT N M`** 定点修复 → 重跑；`debug_tries ≤ 20`（实测 5–8 收敛）
  5. 全阶段写 `events.ndjson`（durable truth），`RUNSTATE.json` 为派生快照，支持 `resume_repro`
- **产物**：`events.ndjson`、`RUNSTATE.json`、`raw_results.json`、`S2_LADDER.json`、`EDIT_LOG.jsonl`
- **门**：`verdicts_valid` + `ladder_gate` + execution budget

### R6 `verify-and-replay` — 语义判定而非只看数值
- **逐 SAU 判定**（SA-Bench 四类 drift + 我方 `code_grounding`）：每条输出
  `verdict ∈ {aligned, mismatch, stub, absent}` + 证据（代码行/AST 符号/实跑值）
- **混合级评分**：`Align-Score = w1·paper_level + w2·code_level + w3·mixed_level`，
  推荐以 mixed 为主（与人类相关性 0.81–0.83）
- **执行评分**：`Exec Rate`、`Perf Gap = (1/n)Σ|P_ref−P_agent|/max(...)`；沿用 `reproduction_close` 的 5% 偏差门
- **★ Claim Anchor**：`code_sha / inputs_sha / outputs_sha` 三哈希 + 每条声明的 SAU id；任一变更即 `drift`
- **产物**：`REPRO_REPORT.md`（可独立重跑脚本 + 结果表）、`REPRO_VERDICTS.json`、`SAU_VERDICTS.json`、`CLAIM_ANCHORS.json`、`REPRO_SCRIPT.py`（Artisan 式独立脚本）
- **门**：`reproduction_close` + `sau_drift_rate ≤ 阈值`；`loopback L2(deviation→R5)` 预算 1

### 5.1 门与回退总表

| 门 | 判定 | 失败动作 |
|---|---|---|
| R0 paper / SAU 完备 | BLOCKED | 不进入 R1 |
| R1 method grounded | PARTIAL/BLOCKED | 补 lineage，不编造 |
| R2 code located + static | BLOCKED | L1 → R2（预算 1） |
| R3 shape 一致 | PARTIAL | 记 protocol drift |
| R4 direction 非启发式 | PARTIAL | 人工确认 |
| R5 ladder / verdicts | BLOCKED | EDIT 循环或预算耗尽 |
| R6 close + drift | PARTIAL | L2 → R5（预算 1） |

---

## 6. 评估体系（把文献指标落到节点）

| 指标 | 定义 | 数据来源节点 |
|---|---|---|
| `SAU_score` | 逐条 SAU 对齐比例（四类 drift 分列） | `EvaluationResult` → `AlgorithmModule`/`CodeFunction` |
| `Align_paper / code / mixed` | 关键点 5 项 / 代码 4 维 / 联合 | `METHOD_CARD` + `CodeFunction` + lineage |
| `Exec Rate` | 可完整执行实验比例 | `ExperimentNode` / `CompileReport` |
| `Perf Gap` | 相对偏差 | `ReproductionResult` vs `LeaderboardEntry` |
| `API/Symbol Recall` | 命中原仓库符号比例 | `MODULE_IMPLEMENTED_BY` 命中数 / method SAU 数（MolMiner 12/12 可作金例） |
| `Drift Rate` | mismatch + stub 占比 | `SAU_VERDICTS.json` |
| `Anchor Integrity` | 三哈希一致且双跑一致 | `ClaimAnchor` + `events.ndjson` 重放 |

**关键原则**：**数值接近不等于复现成功**。SA-Bench 证明最强配置 SAU 仅 0.301；
因此 R6 必须同时看 `Perf Gap` 与 `SAU_score`，任一不合格不得 PASS。

---

## 7. 真实实例：MolMiner `2411.06608`

语义层已有（见 `SEMANTIC_LAYER_ARCHITECTURE.md:370-389`）：

```
Paper:2411.06608
 ├─ PROPOSES_METHOD → Algorithm:molminer
 │    ├─ HAS_MODULE → 4 个 AlgorithmModule
 │    │      └─ MODULE_IMPLEMENTED_BY → CodeFunction（12 符号全命中）
 │    ├─ EVALUATED_ON → Benchmark:zinc（155 行 model_results）
 │    └─ SUBCLASS_OF(extends) → jtnn / hiervae
 ├─ HAS_CODE → CodeRepository:raulorteg_molminer（49 CodeFunction）
 └─ RELATED_TO → JTNN / ChemicalVAE
```

**编译出的 ReproSpec（预期，可写成测试断言）**：

| SAU kind | 条数 | 来源 |
|---|---:|---|
| `method` | 4 | 4 个 AlgorithmModule |
| `code_grounding` | 12 | 12 个 code_symbols / 49 个 CodeFunction |
| `protocol` | 3 | ZINC 的 input/output_form + 3 个 benchmark 契约 |
| `numeric` | 8 | 8 条 observations / 155 行榜单 |
| `ordering` | 3 | modules 的 inputs→outputs 依赖闭包 |
| **合计** | **30** | `spec_hash` 稳定 |

- R1.5 lineage：取 `SUBCLASS_OF` 的 JTNN / HierVAE + `RELATED_TO` 的 ChemicalVAE（k=3）
- R2 有仓库 → AST 审计路径，`STATIC_CHECKS` 应命中 49 函数
- R3.5 shape probe：SMILES 字符串输入 / 分子图输出
- R5 若在 `dry` → R6 必须 BLOCKED（当前行为，**诚实但不可用**）
- R6 目标：`Symbol Recall 12/12`、`SAU_score ≥ 0.8`、`Perf Gap ≤ 0.05`、三锚一致

---

## 8. 与 SciForge-OSS 的对照

| SciForge 机制 | 位置 | 本方案落点 |
|---|---|---|
| S2 Protocol「prose 与 code 冲突时 code 赢」 | `skills/shared-references/s2-protocol.md:1-11` | 语义层 `NON_LLM` 字段（AST/表格）优先于 LLM 摘要 |
| subset→full ladder + 3 态 Critic | `s2-protocol.md:42-60`，`skills/support/experiment-ladder/SKILL.md` | R5 四步；`S2_LADDER.json`；ties fail |
| ENGINEER ≤ 2 轮 | `s2/ladder.MAX_ENGINEER_ROUNDS` | R5 预算 |
| Method Registry（方法锁定） | `skills/support/method-registry/SKILL.md` | `MethodLock` + `spec_hash` |
| Invariant check | `skills/support/invariant-check/SKILL.md` | `ordering` SAU + `code_grounding` SAU |
| result-to-claim / CLAIM_ANCHORS | `skills/support/result-to-claim/SKILL.md`、`s2-protocol.md:174-186` | R6 三哈希锚 |
| AUDIT_TRAIL / method↔code parity | `s2/audit.py` | SAU 的 method vs code_grounding 交叉判定 |
| `events.ndjson` 重放 / RUNSTATE 派生 | `REPRODUCE.md:2` | 已在 `sciforge/repro/runner.py:91-103` 实现 |
| integrity_monitor / claim_anchor_gate | `s2-protocol.md:102-115` | R6 的 `Anchor Integrity` |
| 10+ 相位完整论文生成 | `SKILL.md` / 16 相位 | **不采用**：本方案只取复现子集 |

**差异要点**：SciForge 是「skills + kernel gate」的知识层/流程层，入口是**已结构化的想法与实验规格**，
不是从 PDF 直接生成全仓库；它是**流程纪律**的参考，不是代码生成的参考。
本方案保留其门/阶梯/锚/重放，代码生成与执行侧取 AutoReproduce / PaperCoder / SA-Bench。

---

## 9. 差距清单与落地顺序

### 9.1 当前差距（按影响排序）

| # | 差距 | 证据 | 文献对应 |
|---|---|---|---|
| G1 | **R5 不真跑，R6 必然 BLOCKED** | `runner.py:3,44-46`、`gates.py:89-97` | 所有 2025+ 工作 |
| G2 | **无可验证规格（SAU）**，无法测语义漂移 | `REPRO_PLAN.json` 只有列表 | SA-Bench |
| G3 | 无执行反馈闭环（EDIT / traceback 归因） | `runner.py` 无 subprocess | AutoReproduce |
| G4 | 无 mini-batch shape/dtype 推断 | `DATA_PLAN` 无 shape | AutoReproduce |
| G5 | 无 paper lineage 消费 | `planner.py` 只读 `RELATED_TO` 作线索 | AutoReproduce |
| G6 | 无 3 态 Critic / subset→full ladder | `gates.py` 无 ladder | SciForge S2 |
| G7 | 无 mixed-level 对齐评分与 claim anchor | `REPRO_VERDICTS.json` 只有 verdict | AutoReproduce / SciForge |
| G8 | **关系名双轨**（phasegraph vs 语义层） | `phasegraph.json:18` vs `SEMANTIC_LAYER_ARCHITECTURE.md:49-59` | — |
| G9 | `application_hints.json` 的 Tool/Formula 未节点化 | `APPLICATION_TASK_LAYERS.md:241-243` | AutoP2C |
| G10 | 老 `reproflow.py` / `replicate/` 与 R0–R6 三链并存 | `sciforge/README.md:32` 标注兼容层 | — |

### 9.2 落地顺序

> **进度（2026-11-14 终版）**：P0-1 ~ P0-4、P1-5 ~ P1-7、P2-8 ~ P2-9 **全部实现**。
> 代码在 `capfactory/reprospec/`（relations/contract/compiler/application/verdict/
> executor/ladder/probe/scoring/cli）与 `sciforge/repro/runner.py`。
> 测试：`tests/Phase/test_reprospec.py`(28) + `test_repro_p03_p04.py`(22) +
> `test_repro_p1_p2.py`(26)。
> 注意 P0-3 实测为「7 类从 reserved 升级 + 1 类（EvaluationResult）应用层新增」，
> 以 `reserved_status()` 为准。
> **真实验证已完成**：`capfactory/md/REPRODUCTION_VALIDATION_REPORT.md`
> （MolMiner 2411.06608，lite，R6=PASS，overall=PARTIAL）。
> 实现设计取舍见 `REPRODUCTION_IMPLEMENTATION_BLUEPRINT.md`。

| 阶段 | 任务 | 验收 |
|---|---|---|
| **P0-1** | 统一关系名（phasegraph reads → 语义层 9 关系）；`planner.py` 去掉对 `relation_index` 的隐式依赖或显式声明 | `plan.code` 与 `MODULE_IMPLEMENTED_BY` 条数一致 |
| **P0-2** | 实现 `compile_reprospec()`：五类 SAU + `spec_hash` | MolMiner 编译出 30 条 SAU，全部带 `source_node_ids` |
| **P0-3** | 从 reserved 升级 8 类 + 4 条应用关系；只写 `app_reproduction.json` | 语义层节点/断言数不变（6001/7460） |
| **P0-4** | R6 增加逐 SAU 判定与 `SAU_score`（先不真跑，用 dry 的静态证据：method/code_grounding/protocol） | `SAU_VERDICTS.json` 可输出，stub 能被识别 |
| **P1-5** | R5 `lite` 执行器：真 subprocess + 超时 + Docker/venv + `EDIT N M` 循环 + events | Exec Rate 有实数；崩溃可 `resume_repro` |
| **P1-6** | R5 S2 ladder：toy/subset → 3 态 Critic → full 严格优于 | `S2_LADDER.json` 通过 `s2_ladder` 门 |
| **P1-7** | R1.5 lineage + R3.5 shape probe | MolMiner lineage=3；shape 与 input_form 一致 |
| **P2-8** | R4.5 mixed-level rubric + R6 三锚 + `REPRO_SCRIPT.py` | `Perf Gap` / `Align-Score` / `Anchor Integrity` 三项齐全 |
| **P2-9** | Web 增加复现任务页 + SAU 检查单视图 | 冒烟 +N |

### 9.3 不可破坏约束

1. `783 unittest OK · Phase 81 OK · 冒烟 60/60 · compile OK`（`APPLICATION_TASK_LAYERS.md:254`）
2. **抽取/回填期零应用节点**（`applayer/tasks.py:3-7` 的用户约定）
3. 语义层 6001/7460 不被复现流程写入
4. `compile_tbox().issues == 0`；domain/range 判定只走 `ontology.tbox.check_domain_range()`
5. 每个应用节点带 `derived_from` + `miner`，每条应用关系带 `layer` + `task`
6. 不在 R5/R6 编造实跑值；无值即 BLOCKED（保留现有诚实行为）

---

## 10. 反面清单

| 不要 | 原因 |
|---|---|
| 把 SAU 写进语义层 | 它是任务派生的判定单元，不是客观事实 |
| 用 LLM 生成 SAU 集合 | 必须从图确定性编译，否则 hash 不稳定、不可复核 |
| 只看 `Perf Gap` 就判 PASS | SA-Bench：最强配置 SAU 仅 0.301 |
| 整文件重生成来 debug | AutoReproduce 证明 `EDIT N M` 更省 token 且成功率更高 |
| ties 算赢 | SciForge S2 硬性规则 |
| 用 `REALIZED_BY` / `IMPLEMENTS_MODULE` 查当前语义层图 | 实际边名是 `MODULE_IMPLEMENTED_BY` / `HAS_MODULE`（G8） |
| 让 `dry` 模式的 R6 报 PASS | 当前诚实 BLOCKED 是正确行为 |
| 照搬 SciForge 的 16 相位论文生成 | 本任务只做代码复现 |
| 新增语义层类/关系 | 复现是应用任务，应走 `build_task_layer` |

---

## 11. 附录

### 11.1 文献清单

| 简称 | arXiv | 年份/会议 |
|---|---|---|
| CORE-Bench | 2409.11363 | 2024（v2 2026-06） |
| SUPER | 2409.07440 | EMNLP 2024 |
| PaperBench | 2504.01848 | ICML 2025 |
| Paper2Code / PaperCoder | 2504.17192 | ICLR 2026（v5 2026-02） |
| SciReplicate-Bench | 2504.00255 | 2025（v2 2025-08） |
| AutoP2C | 2504.20115 | 2025 |
| ResearchCodeAgent | 2504.20117 | 2025 |
| AutoReproduce / ReproduceBench | 2505.20662 | ACL 2026 Main（v4 2026-04） |
| Agent Laboratory | 2501.04227 | 2025 |
| AI Scientist-v2 | — | 2025 |
| SA-Bench | 2608.24252 | EMNLP Findings 2026 |
| PRBench | 2603.27646 | 2026 |
| Artisan | 2602.10046 | 2026 |

### 11.2 关键代码位置

| 用途 | 路径 |
|---|---|
| 架构唯一入口 | `ARCHITECTURE.md` |
| 语义层定义 | `capfactory/semantic/tbox_v4.py`；说明 `md/SEMANTIC_LAYER_ARCHITECTURE.md` |
| 应用层任务规格 | `capfactory/applayer/tasks.py:13`；说明 `md/APPLICATION_TASK_LAYERS.md` |
| legacy TBox 判定/清点 | `capfactory/ontology/tbox.py`；`md/TBOX_INVENTORY.md` |
| R0–R6 DAG | `capfactory/sciforge/repro/phasegraph.json` |
| 装配器 | `capfactory/sciforge/repro/planner.py:30` `build_plan` |
| 门 | `capfactory/sciforge/repro/gates.py` |
| 执行器 / 重放 | `capfactory/sciforge/repro/runner.py:18` `run_repro`、`:91` `resume_repro` |
| 契约 | `capfactory/sciforge/repro/contract.py` |
| 核心入口 | `capfactory/sciforge/core.py` (`plan_repro` / `run_repro` / `resume_repro`) |
| 参考框架 | `/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/shared-references/s2-protocol.md` |

### 11.3 与其他文档的关系

- 本文与 `md/APPLICATION_TASK_LAYERS.md` 互补：那篇定义**应用层怎么建**，本文定义**建好后怎么用于代码复现**。
- 本文与 `md/STAGE3_STANDARDIZATION_BLUEPRINT.md` 不冲突：那篇管抽取/装配，本文管复现消费。
- 若与 `docs/REPRODUCTION_FLOW.md`、`docs/REPRODUCTION_REPORT.md`（2026-11-09/11，10 相位旧链）冲突，**以本文 + `ARCHITECTURE.md` 为准**。
