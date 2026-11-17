# figure-complexity-contract · 图形复杂度与视觉层级下限

> 源文件：`skills/shared-references/figure-complexity-contract.md`（280 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 + 阶段3 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `FigureAsset` |
| **输出节点（对齐）** | `FigureAsset.complexity` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | A7/A10 结果写入已建议的 `FigureAudit`，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
避免「小学课件式」图形，设定复杂度与视觉层级下限。
### 1.2 为什么需要
规则按结构角色而非学科内容定义；`Discipline determines only semantics, not rules.`；A4–A10 只查结构属性。
### 1.3 不做的后果
图过于简单，无法承载机制解释。

## 2. 输入
### 2.1 输入知识节点
`Figure.structural_role / nodes / components / edges / layer_model / icon`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；依赖 `scripts/plotting/render_figure.py`（A7/A8/A9/A10 审计）。
### 2.3 输入产物
`figure-quality-contract.md`、`figure-layout-contract.md`。

## 3. 输出
### 3.1 输出知识节点
`Figure.custom-drawn_ratio / edge_density / grouping_levels`；`Composite.panels`；`Figure.revision_log`。
### 3.2 输出产物
`figures/<name>/icons/*.svg`；`figures/<name>/revision_log.md`。
### 3.3 传递片段
≥5 nodes 禁 all plain shapes；至少 60% 主组件自定义；A9 品牌泄漏强制阻断；scoped revision 禁整图重写。

## 4. 判定与门
A7 WARN `plain_shapes_only`；edges/nodes≤1.6；arrow style family≤3；labels≤3 lines、≤4 words/line、>8 words 重构；text-text bbox >12% FAIL；≥20 labels 无层结构 WARN；complexity floor Intro≥8 / Methods≥12 / Mechanism≥8 / Composite≥3；panel cap 9，>9 RENDER FAIL。

## 5. 上下游
figure-quality-contract + figure-layout-contract → 本契约 → `/unified-plotting`、`render_figure.py`。

## 6. 映射
机制图/架构图用自定义组件、总线连线与图层模型呈现算法族与任务流。
