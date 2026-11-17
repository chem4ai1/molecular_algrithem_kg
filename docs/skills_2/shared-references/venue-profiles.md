# venue-profiles · 目标 venue 档位画像

> 源文件：`skills/shared-references/venue-profiles.md`（159 行） · 类型：shared-reference（配置）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 + 阶段3 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionPlan` |
| **输出节点（对齐）** | `SectionPlan.word_budget` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：页数/语气约束落在 SectionPlan 属性 |

## 1. 解决的问题
### 1.1 核心问题
定义 venue 族画像（page limit / review criteria / figure expectations / citation style），供写作与评审对齐。
### 1.2 为什么需要
`discipline-context.md` 规定只有 general pipeline，venue 画像不产生分支；同一论文按目标 venue 调格式与语气。
### 1.3 不做的后果
论文格式与 target venue 不匹配。

## 2. 输入
### 2.1 输入知识节点
`DISCIPLINE_CONTEXT.target_venue`；`VenueProfile{page_limit, review_criteria, figure_expectations, citation_style}`。
### 2.2 输入 prompt 模板 / 契约
`venue-profiles` 只作为 configuration，不作为 discipline dispatch。
### 2.3 输入产物
`venue-checklists.md`、`discipline-writing.md`、`paper-modes.md`。

## 3. 输出
### 3.1 输出知识节点
`venue_profile`；`Length.page_limit`；`Review.criteria`。
### 3.2 输出产物
无新增文件；配置注入写作与编译。
### 3.3 传递片段
无。

## 4. 判定与门
无机械门；未知 venue → general profile；不得据此创建 discipline branch。

## 5. 上下游
用户 target_venue / startup → 本画像 → venue-checklists / paper-compile / paper-writing。

## 6. 映射
`target_venue` 只调页数/语气/图预算，不创建 chemistry-only 分支。
