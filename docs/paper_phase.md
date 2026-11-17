# 结论先行

可以总结，但要先说清一件事：**这套 schema 里没有一份叫"论文写作流程"的规范**。下面这个阶段模型，是我从三类明文事实反推出来的——① 各节点的"定位/抽取来源/使用场景"字段，② 节点之间的依赖边（如 `SectionDraft -INSTANCE_OF→ SectionPlan`），③ 三种生命周期（global / task-w / task-r）。所以它是**解释**，不是原文照抄；阶段名是我起的，输入输出节点和依据都可指回具体文档。

先看整体流水线（颜色按生命周期：绿=global 可复用，橙=task 按 run 隔离）：
# 六阶段的输入与输出

下面是逐阶段对照表。**输入/输出列是解释（我按节点依赖边反推的阶段边界）**；「文档依据」列是**事实**——都能指回具体文件的字段或关系。

| 阶段 | 输入（读什么） | 输出（产出什么） | 文档依据 |
|---|---|---|---|
| **0 问题锚定** | `Paper`（research_question / problem_category / why_hard）、`Algorithm`、`Benchmark` | `ResearchQuestion`、`ProblemCategory`（聚类）、`EvidenceNorm`、`FailureMode` | README §3 写作链读取清单；Paper.md §2；ProblemCategory.md「从 Paper.problem_category 聚类」 |
| **1 选空白+定主张** | 候选 `ResearchGap`(R6)、`Contribution`(R1)、`CitedPaper` | 本次 run 的 `ResearchGap`（gap_type / priority / source_papers / **selected_at**）；边 `ANCHORS→Contribution` | ResearchGap.md「只在使用时建，mine_all 不产出」「selected_at 选定时间」；Contribution.md「生成时决定主推哪条」 |
| **2 章节规划** | `Contribution`、`ExperimentArm`(R2)、`EvidenceNorm`、`FigureAsset`(R4) | `SectionPlan`（claims / evidence_refs / word_budget）；边 `OUTLINES←Paper` | README §3「→ 章节计划 + 素材 + 措辞约束」；SectionPlan.md §2/§3 |
| **3 起草** | `SectionPlan`、`Evidence`、`CitedPaper`(R5) | `SectionDraft`（status / cited / evidence，task-w）；`ConsultedPaper`（查而未引，task-r） | SectionDraft.md `INSTANCE_OF→SectionPlan`、`USES_EVIDENCE→Evidence`、`CONSULTED→ConsultedPaper`；ConsultedPaper.md「与 CitedPaper 差别是没有 CITES 边」 |
| **4 反驳预演** | `Contribution`、`SectionDraft`、`FailureMode` | `ReviewPoint`（axis / attack / response / severity，task-w） | ReviewPoint.md「CHALLENGED_BY←Contribution」「最强反驳预演」；README §5 六维审稿轴 |
| **5 自检核验** | 全部节点 + `Evidence.char_span`、`FailureMode` | `FailureCheck`（status / note，task-r）；四类泄露 / 逻辑一致性 / 引用三层结论 | README §3 审计链「全部 + Evidence.char_span →…」；FailureCheck.md `CHECK_OF→FailureMode`、`CHECKED←Paper` |

## 三个关键点

**① 一条贯穿全程的隔离轴。** 阶段 1、3、4 产出 **task-w**（写作态），阶段 3、5 产出 **task-r**（读态），都带 `run_id`、写进 `storage/writing_runs/<run_id>.json`，**永不写回全量图**（README §4、ResearchGap.md）。阶段 0、2 的 `EvidenceNorm`/`FailureMode`/`SectionPlan` 才是 global 可复用骨架。这意味着"同一批素材写两篇论文"会生成两套 task 实例，互不污染——这是这套设计最值钱的一处边界。

**② 阶段 5 是回环，不是终点。** `FailureCheck` 的结论（pass/fail/unknown）会反馈到阶段 1 的空白优先级、阶段 3 的措辞、阶段 4 的反驳强度；`ConsultedPaper.reason` 专门回答"为什么查了却没引"。所以流程是 **0→1→2→3→4→5→（回到 1/3/4）**，不是一次性流水线。

**③ 引用的三层核验落在阶段 3、5。** `CitedPaper` 带 `existence`（真存在吗）/ `metadata_ok`（元数据对吗）/ `context_ok`（原文支撑吗）+ `context_quote`（支撑句）——这是把"引用是否可靠"做成了可判定字段，而不是靠人肉记忆。

## 三分：事实 / 解释 / 不确定

- **事实**：六类节点的定位、关系边、生命周期、抽取来源（R1–R6），以及 README §3 三条使用链路表——这些是文件里白纸黑字写的。
- **解释（我的加工）**：把"六阶段"这个划分本身、阶段编号与命名、以及"阶段 5 回环"的读法。schema 只给了节点和边，没有画出阶段;this 是我按依赖顺序重构的。
- **不确定 / 边界（文档自己承认的）**：`Evidence.char_span` 标注"待补"（阶段 5 的审计精度目前受限）；`ReviewPoint` 标注"当前仍为每条贡献固定生成 6 条，待改为按需预演"；`ResearchQuestion.md` 使用场景栏写"（待补）"。这些都说明**阶段 0 和阶段 4/5 的自动化程度还不完整**。

> 这是从 34 份 schema 文档反推的解释性总结，不是项目里现存的流程规范文件；文档本身没有明说"论文写作分几阶段"。若与实际写作流程有出入，以业务方事实为准。需要的话我可以把这张对照表落成一份 Markdown 资产（含逐阶段字段清单和依据索引）。