# figure-quality-contract · 图形质量地板与双输出

> 源文件：`skills/shared-references/figure-quality-contract.md`（187 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 + 阶段3 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `FigureAsset` |
| **输出节点（对齐）** | `FigureAsset.output_pdf`/`output_svg` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `FigureAsset` 加 output_pdf/output_svg 属性即可，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
统一图形质量、双产出（PDF+SVG）和工具链入口。
### 1.2 为什么需要
修复 SVG-only、无比例/可读性底线、复杂架构图质量差；`Dual output is non-negotiable.`
### 1.3 不做的后果
正文嵌栅格或只有 SVG，paper-compile 拒收。

## 2. 输入
### 2.1 输入知识节点
`Figure.aspect_ratio / width_preset / output_format / font_size`；`Diagram.nodes`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；依赖 `scripts/plotting/render_figure.py` 单一渲染入口。
### 2.3 输入产物
unified-plotting SKILL.md。

## 3. 输出
### 3.1 输出知识节点
`Render.figure_audit`；`WidthPreset.width_mm`；`Toolchain.engine`；`Figure.output_pdf / output_svg`。
### 3.2 输出产物
`figures/<name>/output.pdf`（LaTeX 唯一嵌入格式）、`output.svg`（查看/编辑 master）。
### 3.3 传递片段
16:9 default；PDF+SVG 必产；5+ node diagrams 用 d2 或 graphviz fallback；AI-direct SVG 仅限 ≤4 nodes。

## 4. 判定与门
figsize 偏离 16:9 >10% 且无 override+reason → 拒绝；仅 PDF 或仅 SVG → INCOMPLETE / re-render；font below floor rejected；rsvg-convert / inkscape 均无 → BLOCK figure。

## 5. 上下游
`/unified-plotting` 消费 → `render_figure.py` 审计 → `/paper-compile` 用 PDF、`/paper-writing` 用 SVG。

## 6. 映射
算法流程/分子机制图统一 PDF+SVG 与 d2 渲染，保证论文编译与视觉复核一致。
