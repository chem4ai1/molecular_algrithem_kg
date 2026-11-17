# novelty-check · 复合分筛选 + 碰撞审计 + 前沿定位收敛

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/novelty-check/SKILL.md`（212 行）
> 类型：meta-skill · Phase 3（MUST + 人工检查点） · 代码佐证：`scripts/doi_gate.py`、`scripts/citation_support.py`、`scripts/fantasy_gate.py`、`scripts/claim_anchor_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `3`/`4targeted` |
| **输入节点（对齐）** | `IdeaNode`；`ResearchGap`(task-w)；`SourcePaper` |
| **输出节点（对齐）** | `Contribution`(global 候选)；`ResearchGap.selected_at`(task-w) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 global 节点 `FrontierGap`（frontier baseline / delta / why-not-before 三元组）与 `CollisionAudit`（same_problem/method/data 三维）；三者是选择依据，现有 `Contribution` 无法承载 |

## 1. 解决的问题

### 1.1 核心问题
对想法 DAG 做 novelty / feasibility / relevance / engineering grounding 四维评估与碰撞审计，定位 frontier baseline / delta / why-not-before，收敛到**至多 1 个 survivor**。

### 1.2 具体场景 / 为什么需要
- Q1 Introduction 必须有可追溯的 frontier baseline、delta claim、why-not-before，否则 paper-writing 只能临时编造贡献定位。
- 碰撞审计避免「别人已经做过」：`at most 1 idea survives to the derivation phase`。
- Phase 3→4 是强制人择检查点，agent 不能自己选。

### 1.3 不做的后果
- 相对过时基线的新意，被审稿人一句「已被 X 超越」打掉。
- 多个 survivor 并存导致下游方法锁定无法收敛。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Idea` | `id / title / hypothesis / methodology / perspective` | `IDEA_DAG.json` | 必须 |
| `EngineeringGrounding` | `eg_average` | Phase 2.5b | 必须 |
| `Idea` | `gap_anchor` | `GAP_ANCHOR_LOG.md` | 必须 |
| `GapReport` | `gap-id` | `GAP_REPORT.md` | 必须 |
| `FrontierMap` | `unsolved node` | `landscape_report.md` | 必须 |
| `Collision` | `same_problem / same_method / same_data` | targeted wave | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无 prompt 模板 | 消费 `assurance-contract.md`、`citation-discipline.md`、`output-manifest.md` | 6 态 verdict / 引用纪律 / 产物清单 |
| 收敛约束 | `at most 1 idea survives to the derivation phase` | 唯一 survivor |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/IDEA_DAG.json` | 候选 |
| `literature/references.bib` | previous work |
| `literature/landscape_report.md` | frontier map |
| `literature/GAP_REPORT.md` | gap 校验 |
| `refine-logs/GAP_ANCHOR_LOG.md` | gap_anchor |
| `literature/TARGETED_WAVE_LOG.md` | collision pre-check |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Novelty` | `binary_novelty / frontier_advance / novelty_final` |
| `Feasibility` | `verdict` |
| `Relevance` | `verdict` |
| `Composite` | `score` |
| `Collision` | `collision_matrix / differentiation` |
| `FrontierGap` | `frontier baseline / delta claim / why-not-before` |
| `Survivor` | `id` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `refine-logs/FRONTIER_GAP.md` | frontier baseline / delta claim / why-not-before | Intro 定位 |
| `refine-logs/FRONTIER_MAP.json` | frontier node graph / unsolved node / gap-id | 前沿图 |
| `refine-logs/novelty_report.json` | collision_matrix / scores / verdicts | 完整评估 |
| `refine-logs/novelty_{idea_id}.md` | 逐想法评估 | 审计 |
| `refine-logs/survivor.md` | selected idea + EG tag | 人择依据 |
| `refine-logs/differentiation.md` | mechanism-level difference | 机理差异 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| survivor | `/theory-derivation` | 唯一候选进入推导 |
| elimination records / selection rationale / FRONTIER_GAP 三元组 | `/paper-writing` Introduction | 可追溯贡献定位 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 复合分 | skill 内 | `score = novelty×0.45 + feasibility×0.25 + relevance×0.15 + engineering_grounding×0.15` | `<0.6` eliminated | 淘汰 |
| novelty 合成 | skill 内 | `novelty_final = 0.5×binary_novelty + 0.5×frontier_advance` | — | — |
| 三元组门 | skill 内 | FRONTIER_GAP 缺 1 项 | → WARN | 不能进 Phase 3→4 checkpoint |
| gap 锚门 | `gap_gate` | `gap_anchor_invalid` | → FAIL | 回 Phase 4broad |
| 碰撞门 | skill 内 | 3 个 collision 维全 =1 | `collision_fatal FAIL` | 回 Phase 2 |
| 复审门 | skill 内 | REVISE | `≤2` | 超限 BLOCKED |
| 无 survivor | skill 内 | relax strictness 一次，仍无 | — | BLOCKED |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/idea-discovery` | Phase 3 `/novelty-check`（人工检查点） | targeted retrieval waves → `/theory-derivation`、`/paper-writing`；REVISE 回 `/idea-discovery` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `FrontierGap / Collision / Survivor` | `paperapp` 已有 `ResearchGap`，可扩 `FrontierGap / CollisionAudit` | 建议新增 `CollisionAudit` |
| 复合分 0.45/0.25/0.15/0.15 | gate 阈值 | 否 |
| `gap_anchor_invalid → FAIL` | `DK-P1-06` 的判据来源 | 否 |
