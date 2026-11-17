# 语义层 / 应用层再划分：可复用输入 vs 阶段输出

> 核心命题：**语义层存「从别的论文解析出来、能供后续任何一次生成参考」的东西；
> 应用层存「本次生成在某个阶段实际产出的东西」。**
> 前者是读侧知识库，后者是写侧过程态。

## 1. 判断标准（一条就够）

问：**这个信息是"从论文里读出来的事实"，还是"这次生成过程中产生的决定/产物"？**

| | 语义层 | 应用层 |
|---|---|---|
| 来源 | 已有论文（PDF/md/表格/AST） | 本次 run 的各阶段 |
| 用途 | 被任意任务反复检索 | 只对本次任务有意义 |
| 生命周期 | 永久、增量 | task-w / task-r / global 派生 |
| 错误代价 | 高（改 `stable_key` 会让历史失效） | 低（可删可重建） |

**推论**：阶段 01–03 主要**读语义层**；阶段 04–12 主要**写应用层**，但会回查语义层。

## 2. 当前语义层架构解析

### 2.1 六类 / 九关系

| 类 | 实例 | 原有字段覆盖 | 新字段覆盖（本轮加的） |
|---|---:|---|---|
| `Paper` | 808 | 11/12 满；`doi` 2/808、`venue` 0/808 | `paradigm`/`evidence_type`/`evidence_norm`/`figures`/`section_map`/`gaps` **全 0** |
| `Algorithm` | 1674 | `name` 100%；`mechanism` 等约 45% | `assumptions`/`novelty_basis` **0** |
| `AlgorithmModule` | 2856 | `name`/`mechanism`/`inputs`/`outputs` 100%；`formula` 29% | `is_novel_component`/`component_role` **0** |
| `CodeRepository` | 10 | 全满 | — |
| `CodeFunction` | 49 | 全满 | — |
| `Benchmark` | 604 | `name`/`input_form`/`output_form` 100%；`model_results` 34% | `protocol`/`failure_modes` **0** |

```
PROPOSES_METHOD          Paper → Algorithm           1666
HAS_MODULE               Algorithm → AlgorithmModule 2862
MODULE_IMPLEMENTED_BY    Module → CodeFunction        758
HAS_CODE                 Paper → CodeRepository        10
HAS_FUNCTION             Repository → CodeFunction     49
BELONGS_TO_MODULE        CodeFunction → Module          0  ← 死关系
EVALUATED_ON             Paper|Algorithm → Benchmark  984
RELATED_TO               Paper → Paper|Algorithm       48  ← 引用网稀疏
SUBCLASS_OF              Algorithm → Algorithm       1083
```

### 2.2 最关键的问题

**不是字段不够，是新字段全空。**

当前 13 个新字段（paradigm / evidence_type / assumptions / protocol …）填充率 **0%**，
意味着阶段 02 的领域学习、阶段 06 的预注册、阶段 07 的证据审计都拿不到语义层输入。

**在补新字段之前，必须先重抽把这 13 个填上**——否则加更多字段只会让空字段变多。

## 3. 十二阶段：检索语义层什么 → 输出应用层什么

| 阶段 | 检索语义层（读） | 输出应用层节点（写） | 当前缺口 |
|---|---|---|---|
| **01 问题锚定** | `Paper.domain`（808/808）、`research_question`、`why_hard`；向量召回 | `ProblemAnchor`(task-w)、`DomainHint`(task-r)、`RelatedPaper`(task-r) | 已实现；领域标签只作 hint |
| **02 领域学习** | `Paper.paradigm` / `evidence_type` / `evidence_norm` / `Algorithm.assumptions` / `Benchmark.protocol` | `EvidenceNorm`(learned)、`MethodologyProfile`(新) | ⚠️ 语义层新字段 0%，学不到 |
| **03 广域检索** | `Paper.title/authors/abstract/doi/venue/arxiv_id`；BM25+向量 | `Paper`(global 回填)、`SourcePaper`、`RelatedPaper` → `CitedPaper` | ⚠️ `authors`/`abstract` 字段没有；`doi` 2/808 |
| **04 想法生成与证伪** | `Paper.gaps`、`why_hard`、`RELATED_TO`、`Algorithm.limitations`、`Benchmark.metrics` | `ResearchGap`(task-w)、`FalsificationRecord`(新)、`IdeaNode`(可选) | ⚠️ gaps 0%；证伪参考无字段 |
| **05 新颖性人择** | `Paper.problem_category`、`Algorithm.flow_family`、`SUBCLASS_OF`、`Benchmark` 三维碰撞 | `Contribution`、`Novelty`(新) | ⚠️ `flow_family` 仅 36/808；无碰撞字段 |
| **06 预注册方法** | `Algorithm.assumptions` / `mechanism`、`Module.is_novel_component`、`Benchmark.protocol` | `Assumption`、`MethodLock`、`VerificationRoute`(新) | ⚠️ 三个新字段全 0% |
| **07 素材装配** | `Paper.figures`、`Benchmark.model_results`、`Evidence` 来源句 | `Evidence`、`Claim`(新)、`FigureAsset` | ⚠️ figures 0%；`model_results` 仅 34% |
| **08 起草** | `Paper.section_map`、`Algorithm.explanation`、`Benchmark.metrics[].contribution_link` | `SectionPlan`(骨架)、`SectionDraft`(task-w)、`RunArtifact` | ⚠️ section_map 0% |
| **09 最强拒稿论证** | `FailureMode`、`Evidence`、`Algorithm.limitations` | `ReviewPoint`(task-w)、`AttackMemo`(新) | 领域知识已有；limitations 27% |
| **10 跨模型复审** | `Claim`、`FailureMode`、`DomainHint` | `ReviewPoint`(追加) | 读态多，语义层需求少 |
| **11 反驳响应** | `ExperimentArm`、`RunArtifact`、`Evidence` | `ReviewPoint.response`、`Rebuttal`(新) | 主要读应用层 |
| **12 自检核验** | `CitedPaper` → 语义层 `RELATED_TO`、`Evidence.char_span` | `CitedPaper`(最终)、`RunArtifact` | ⚠️ RELATED_TO 48 条；char_span 无 |

**规律**：
- 阶段 01–03 是**语义层重读**阶段——语义层缺字段直接卡住
- 阶段 04–08 是**语义层 + 应用层混合**——先读别人，再写自己
- 阶段 09–12 是**应用层自洽**阶段——主要读本次产物，语义层只做校验

## 4. 语义层扩建建议

### 4.1 P0：先填已有字段（不新增）

| 字段 | 现状 | 解锁阶段 |
|---|---|---|
| `Paper.paradigm` / `evidence_type` / `evidence_norm` | 0% | 02 领域学习、06 预注册 |
| `Paper.figures` / `section_map` / `gaps` | 0% | 04 想法、07 素材、08 起草 |
| `Algorithm.assumptions` / `novelty_basis` | 0% | 04、06 |
| `Module.is_novel_component` / `component_role` | 0% | 06 消融规划 |
| `Benchmark.protocol` / `failure_modes` | 0% | 02、06、09 |
| `Paper.doi` / `venue` | 0.2% / 0% | 03 检索、12 引用校验 |

**这是唯一阻塞项**：不重抽，后面所有"语义层检索"都是空转。

### 4.2 P1：真正缺的字段（按「≥2 阶段用 + 可从论文解析」筛）

| 字段 | 类型 | 服务阶段 | 为什么该进语义层 |
|---|---|---|---|
| `Paper.authors` | list[str] | 03 检索、12 引用 | 检索元数据必需；当前完全没有 |
| `Paper.abstract` | str | 03 检索、向量索引 | 向量索引目前靠 `node_text()` 拼字段，摘要缺失拉低召回 |
| `Paper.claims[]` | list[dict] | 07 素材、09 拒稿、10 复审 | 「别人怎么主张」是写作参考，不是本次产物 |
| `Paper.references[]` | list[str] | 03 检索、12 自检 | `RELATED_TO` 仅 48 条，引用网几乎为空 |

### 4.3 P2：可选（单阶段用，价值中）

`Paper.citation_style` / `Paper.writing_style`（02、08）——可以从 PDF 的参考文献格式与章节结构解析，但收益低于前四项。

### 4.4 明确不加

| 候选 | 理由 |
|---|---|
| `Paper.frontier_signals` | 只服务阶段 05，且「前沿定位」是**本次判断**，属应用层 |
| `Paper.falsified_hypotheses` | 只服务阶段 04，且反例是**本次证伪记录**，属应用层 |
| `Paper.pre_registration` | 别人的预注册文本对本次帮助有限 |

**这是分层纪律**：「从别的论文解析出的、被多次复用」才进语义层；「本次的判断/决定」一律留应用层。

## 5. 应用层待补的阶段输出节点

| 阶段 | 应输出 | 状态 | 定位 |
|---|---|---|---|
| 04 | `FalsificationRecord` | ❌ 缺 | task-w：本次试过的反例 |
| 05 | `Novelty` | ❌ 缺 | task-w：本次新颖性判定 |
| 06 | `VerificationRoute` | ❌ 缺 | task-w：本次验证路由（experiment-first / theory-only / hybrid） |
| 07 | `Claim` | ❌ 缺 | task-w：本次主张（区别于 `numeric` SAU 的验证声明） |
| 09 | `AttackMemo` | ❌ 缺 | task-w：本次最强拒稿论证 |
| 11 | `Rebuttal` | ❌ 缺 | task-w：本次反驳信 |

**已有的**：`ProblemAnchor` / `DomainHint` / `RelatedPaper`(01-03)、`ResearchGap`(04)、`Contribution`(05)、`Assumption`/`MethodLock`(06)、`Evidence`/`FigureAsset`(07)、`SectionPlan`/`SectionDraft`(08)、`ReviewPoint`/`FailureCheck`(09-12)。

## 6. 落地顺序

```
P0  重抽 4 篇 → 13 个新字段从 0% 变非 0       【阻塞一切】
P1  加 authors/abstract/claims/references → 重抽
P2  补 6 个应用层阶段输出节点（FalsificationRecord 优先）
P3  每阶段串成 CLI（freeze → retrieve → hint → ...）
```

**为什么 P2 在 P1 之后**：阶段 04/07 的输出节点要引用语义层输入（`Paper.gaps` / `Paper.claims`），输入为空时节点只能产空壳。

## 7. 一句话

语义层是**图书馆**（别的论文沉淀的可复用输入），应用层是**工作台**（本次生成的逐步产物）。
现在的问题不是工作台不够，是图书馆里 13 本新书还没上架——**先重抽，再扩建**。
