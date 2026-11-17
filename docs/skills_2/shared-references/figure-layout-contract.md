# figure-layout-contract · 图形排版即科学论证结构

> 源文件：`skills/shared-references/figure-layout-contract.md`（277 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 + 阶段3 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `FigureAsset.archetype` |
| **输出节点（对齐）** | `FigureAsset.geometry` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | A11 对齐结果写入已建议的 `FigureAudit` |

## 1. 解决的问题
### 1.1 核心问题
把图排版变成可审计的科学论证结构：claim、panel 推断角色、原型与最终尺寸先于代码。
### 1.2 为什么需要
`The chart serves the scientific logic.`
### 1.3 不做的后果
为了对齐网格扭曲科学事实；图有元素但无论证角色。

## 2. 输入
### 2.1 输入知识节点
`Figure.claim / evidence_chain / archetype / export_contract`；`Panel.inferential_role`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；依赖 `figure_audit.py` A11 panel-alignment。
### 2.3 输入产物
figure-quality-contract + figure-complexity-contract。

## 3. 输出
### 3.1 输出知识节点
`Figure.geometry_ratios / visual_weight`；`FigureComparableGroups`；`Sizing.on_page_font_pt`；`AlignmentGate.verdict`。
### 3.2 输出产物
`figures/<name>/<name>.figure.json`：`claim / archetype / panels`；`figures/<name>/figure_audit.json`：`bbox_pt / row_groups / exemption`。
### 3.3 传递片段
specs missing `claim` and `archetype` rejected；A11 exemption 必须记录原因；禁为等宽网格扭曲科学事实。

## 4. 判定与门
renderer 拒缺 claim/archetype；A11 1.5pt tolerance；FIX BEFORE DELIVERY / exit 1 blocks export；NOT AUDITABLE / exit 2 阻断 alignment passed；6pt tick / 7pt body / 8pt axis labels，5pt hard floor；panel cap 9。

## 5. 上下游
figure-quality + figure-complexity → 本契约 → `figure_audit.py`、`method_recipes.py`、`figure_recipes.py`、`/unified-plotting`。

## 6. 映射
先写「算法设计主张」，再分配 mechanism / decisive comparison / boundary panel 并锁原型几何。
