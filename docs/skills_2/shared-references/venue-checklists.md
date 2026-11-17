# venue-checklists · 投稿前按 venue 族核对清单

> 源文件：`skills/shared-references/venue-checklists.md`（96 行） · 类型：shared-reference（清单）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `15.5` |
| **输入节点（对齐）** | `SectionDraft`；`FigureAsset` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用 `FailureCheck` 记录格式核对结果 |

## 1. 解决的问题
### 1.1 核心问题
把目标 venue 的硬格式要求变成可勾选清单（页数 / 匿名 / 补充材料 / 引用格式）。
### 1.2 为什么需要
`venue-profiles.md` 定义档位，本文件定义检查项；desk reject 常由格式而非科学问题造成。
### 1.3 不做的后果
因格式/匿名/页数被直接拒稿。

## 2. 输入
### 2.1 输入知识节点
`venue.family / target_venue`；`checklist.item / required / satisfied`；`paper/main.pdf`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `/publishability-score`、`/paper-compile` 消费。
### 2.3 输入产物
`venue-profiles.md`、`style_demands`（intake-triage）。

## 3. 输出
### 3.1 输出知识节点
`VenueChecklist` 完成状态；`format_violations`。
### 3.2 输出产物
`paper/VENUE_CHECKLIST.md`（勾选表）。
### 3.3 传递片段
无。

## 4. 判定与门
required 项未 satisfied → 不得标 SUBMISSION_READY；无 venue 时用 general checklist。

## 5. 上下游
`style_demands` / venue-profiles → 本清单 → publishability-score / 投稿准备。

## 6. 映射
按目标期刊/会议核对页数、匿名、补充材料与引用格式，作为提交门一部分。
