# color-themes · 可发表图形配色的唯一权威

> 源文件：`skills/shared-references/color-themes.md`（104 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 章节规划 + 阶段3 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `FigureAsset` |
| **输出节点（对齐）** | `FigureAsset.palette` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `FigureAsset` 加 `palette` 属性；A3 审计由已建议的 `FigureAudit` 承载 |

## 1. 解决的问题
### 1.1 核心问题
统一 dopamine Layer1 + viridis/magma/plasma Layer2 配色，禁 jet/rainbow/hsv。
### 1.2 为什么需要
色盲可辨（ΔE≥15）、灰度可印、对比可读；`code wins`——`scripts/plotting/sciforge_style.py::TOKENS` 是唯一权威。
### 1.3 不做的后果
off-palette 图被 `figure_audit` A3 拒绝。

## 2. 输入
### 2.1 输入知识节点
`palette.TOKENS`；`color.C*≥30`；`color.ΔE≥15`；canvas visibility ≥3.0；`series_style.marker`。
### 2.2 输入 prompt 模板 / 契约
`the color tables ... take the TOKENS dictionary in scripts/plotting/sciforge_style.py as the sole authoritative definition ... If this document disagrees with the code, the code wins.`
### 2.3 输入产物
`unified-plotting/SKILL.md`、sciforge_style.py、figure_audit A3。

## 3. 输出
### 3.1 输出知识节点
dopamine 8 色（blue/orange/green/red/teal/violet/gold/crimson）；heatmap viridis/magma/plasma；forbidden jet/rainbow/hsv/coolwarm/bwr。
### 3.2 输出产物
PDF（交付主体）+ SVG（查看编辑）；`gen_*.py`；`.composite.json`（≤2 列数据 panel）。
### 3.3 传递片段
文本/坐标轴纯黑 #000000 白底；stroke_for=fill 向 ink 混 45%；每系列独立 marker；禁对文本用系列色。

## 4. 判定与门
C*≥30；28 对 ΔE≥15（protan/deutan/tritan）；canvas≥3.0；axis≥16pt / tick≥13pt / legend≥13pt / title≥18pt / annotation≥12pt / node≥14pt；线≥1.8/1.0pt；marker≥7pt。

## 5. 上下游
unified-plotting → 本契约 + sciforge_style.py → figure_audit A3 / paper-compile。

## 6. 映射
分子性质热图用 viridis/magma；方法对比折线用 dopamine 8 色 + marker；文本纯黑。
