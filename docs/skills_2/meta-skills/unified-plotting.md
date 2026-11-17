# unified-plotting · PDF+SVG 双矢量可发表图与机械审计

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/unified-plotting/SKILL.md`（448 行）
> 类型：meta-skill · Phase 11（MUST） · 代码佐证：`scripts/plotting/{render_figure,figure_audit,figure_recipes,method_recipes,sciforge_style}.py`、`scripts/figure_style_gate.py`、`scripts/check_figure_embedding.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 章节规划 + 阶段3 起草 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `Contribution`；`ExperimentArm`；`Evidence`；`SectionPlan` |
| **输出节点（对齐）** | `FigureAsset`(global/task-w) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 task-w 节点 `FigureAudit`（A1–A11 verdict）与 `FigureBudget`；`FigureAsset` 只记 caption/placement，无审计与预算字段 |

## 1. 解决的问题

### 1.1 核心问题
从结构化数据或 JSON spec 经**单一渲染入口**产出 PDF+SVG 双矢量图，并生成审计、caption、LaTeX include 与 figure index。

### 1.2 具体场景 / 为什么需要
- 防止正文图稀少、栅格嵌入、字号过小、off-palette 配色。
- Python 数据图必须可复现：`render.py / input_data.json` 或 `spec.d2 / source.md` 必须留存。
- 复杂图必须走统一渲染入口，不得手改像素。

### 1.3 不做的后果
- 先写 caption 再渲染 → caption 承诺图里没有的内容。
- 正文嵌栅格、图没有审计记录 → paper-compile 阶段拒收。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Figure` | `chart_type / data` | 结果数据 | 必须 |
| `Figure` | `axis labels / title / legend / annotations` | 调用方 | 可选 |
| `Figure` | `Q-id` | `FINAL_PROPOSAL.md` | 必须 |
| `Figure` | `claim / archetype` | result-to-claim | 必须 |
| `Panel` | `inferential role / layout` | 图规划 | 必须 |
| `Audit` | `verdict / suggested_fixes` | 审计器 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无 prompt 模板 | 消费 `figure-quality-contract.md`、`figure-complexity-contract.md`、`figure-layout-contract.md`、`figure-quality-review.md`、`paper-voice-contract.md`、`artifact-registry.md`、`FIGURE_AUDITS.schema.json` | 图质量/复杂度/布局/评审/语气/产物注册法条 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| structured data（JSON coordinates / matrices / edges）或 chart description | 图输入 |
| `refine-logs/FINAL_PROPOSAL.md` | Q-id |
| `scripts/plotting/sciforge_style.py` | dopamine token 唯一权威 |
| `figure_recipes.panel-grid.layout` | archetype |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Figure` | `output.pdf / output.svg` |
| `Figure` | `render.py / spec.d2 / source.md` |
| `Figure` | `input_data.json / caption / latex_include.tex` |
| `Audit` | `verdict ∈ PASS/WARN/FAIL` |
| `Review` | `revision_log.md` |
| `Mirror` | `FIGURE_AUDITS.json` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `figures/{figure_name}/output.pdf` | — | LaTeX 唯一嵌入格式 |
| `figures/{figure_name}/output.svg` | — | 查看/编辑，禁嵌 LaTeX |
| `figures/{figure_name}/{render.py,input_data.json}` 或 `{spec.d2,source.md}` | — | 复现源 |
| `figures/{figure_name}/figure_audit.json` | `verdict / suggested_fixes` | 机械审计 |
| `figures/{figure_name}/latex_include.tex` | `includegraphics` | 写作消费 |
| `figures/FIGURE_INDEX.md` | Q-id / Type / Path / Caption | 索引 |
| `.sciforge/verdicts/FIGURE_AUDITS.json` | `figures/{figure_name}.verdict / audit_file` | 下游门 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `latex_include.tex` + `FIGURE_INDEX.md` | `/paper-writing` | 嵌入与索引 |
| `FIGURE_AUDITS.json`（FAIL 禁止嵌入） | `/paper-compile` | 图门禁 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 严格渲染 | `render_figure.py --strict` | FAIL | exit 4 | 阻断 |
| 配色门 | skill 内 | off-palette / reject | exit 2 | 阻断 |
| A11 panel-alignment | `figure_audit.py` | `1.5pt` | FAIL | blocks export |
| 图预算 | skill 内 | body minimum 7 figures | `<7` WARN；`<5` FAIL | `figure_budget:below_minimum` |
| 架构图门 | skill 内 | `architecture_diagram_present` 非 true | → FAIL | `missing_architecture_diagram` |
| 样式门 | `figure_style_gate.py` | 首次引用先于 float / body 禁 raster / ≥3 recipe kinds | — | FAIL |
| 嵌入门 | `check_figure_embedding.py --require-renderer` | 缺 `figure_audit.json + latex_include.tex` | → FAIL | 阻断编译 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/theory-derivation`、`/paper-writing` Step1 figure-budget | Phase 11 `/unified-plotting` | `/paper-writing`、`/paper-compile` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `FigureFigureSpec / FigureAudit / FigureBudget` | `paperapp` 已注册 `Figure` 保留类 | 建议新增 `FigureBudget / FigureAudit` |
| `source_result_sha` 唯一数值来源 | 本文 `DK-P4-03` | 否 |
| A1–A11 审计 | `reprospec` gate | 否 |
