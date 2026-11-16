# P11 · `unified-plotting` — 单入口出版级矢量图渲染与图表预算

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/unified-plotting/SKILL.md`（v1.7.2，**447 行，8 个 skill 中最长**）
> **功能批次**：③ 图表与呈现层
> **机械对应代码**：`scripts/plotting/{render_figure,figure_audit,figure_recipes,method_recipes,sciforge_style}.py`、`scripts/figure_style_gate.py`、`scripts/check_figure_embedding.py`
> **性质判断**：**唯一一个「契约 + 完整可执行实现」双全的 meta-skill**。其余 7 个主要是散文契约，这一个有 5 个 Python 模块、A1–A11 十一项机械审计、两个独立门脚本。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `unified-plotting` / `1.7.2`（内容演进到 v3.10） |
| `type` / `role` | `meta-skill` / `figure-renderer-and-spec-generator` |
| 管线阶段 | **Phase 11**（MUST）；与 Phase 12 `/paper-writing` 可并行（orchestrator Group B） |
| 单一入口 | `python scripts/plotting/render_figure.py <spec> --out figures/<name>/ --label <name> --caption "..." --strict` |
| 输出 | `output.pdf` + `output.svg` 双输出 + 保留源码 + `figure_audit.json` + `latex_include.tex` |
| 立场 | OSS 合并了主仓库的 `figure-spec`（确定性 JSON→SVG 图）与 `paper-figure`（数据图），**学科无关** |

---

## 2. 解决什么问题

### 2.1 从真实失败反推的约束

| 观察到的失败 | 对应机制 |
|---|---|
| 图渲染了却没进正文 | `check_figure_embedding.py` 硬门 |
| 图漂在离引用很远的地方 / 正文嵌了栅格预览 / 五张一模一样柱状图 | `figure_style_gate.py` 三查 |
| 两次真实 run 只出 2 张和 5 张图，全挤在 Results | **Figure Budget Contract**（body ≥7，Methods 架构图强制） |
| 「小学水平」的方框图 | v3.6 复杂度硬约束（≥60% 自绘图标、边密度 ≤1.6、≥2 层分组） |
| 小字看不清 | Nature 可读性下限 + **final-width-first sizing**（先按期刊栏宽定 figsize，不许画大再缩） |
| 引擎偷带颜色、色盲不可分 | `sciforge_style.sanitize_palette()` 确定性重映射 + CVD ΔE 校验 |
| 「什么都在一口锅里」的超大拼图 | v3.8 composite panel **硬上限 9**，按叙事单元组合 |
| AI 直接手写数据图 → 数字是编的 | 数据图强制 Python 管道，保留 `render.py` + `input_data.json` |

### 2.2 一句话定位

把「画图」从美术问题变成**可审计的工程问题**：每张图必须带可复现源码、机器审计 verdict、LaTeX 引用片段、以及能追溯到 Q-id 的规格。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | `10(result-to-claim) → **11** → 12(paper-writing) → 13(paper-compile) → 14(review)` |
| 并行 | Group B：Phase 11 与 Phase 12 可并行（图先生成、正文随后写） |
| 前置 | Phase 10 的 `CLAIMS_FROM_RESULTS.md` / 实验 `RESULT.json`（数据图的唯一数值来源）、`FINAL_PROPOSAL.md` 的冻结 Q-id |
| 后继 | `/paper-writing`（消费 `latex_include.tex` 与 figure budget）、`/paper-compile`（嵌入 PDF）、`/auto-review-loop` |
| 门 | `figure_audit.json` 不得 FAIL（`--strict` 时 FAIL 退出码 4）；`FIGURE_AUDITS.json` 任一 FAIL 阻断图入正文；`figure_style_gate.py` 与 `check_figure_embedding.py` 在 Phase 13 边界硬查 |
| MUST 约束 | v2.2 起每篇论文**至少 1 张图**；无数据图时也要画 1 张 pipeline/concept 图 |

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | 全篇 Figure 布局 | Figure Budget（Intro 0–1 / Related Work 1 / Methods 1 / Results 5–8 / Discussion 0–1） | 决定每节配几张图、什么类型 |
| **论文层** | Methods 章节 | **架构图 MANDATORY**（d2 展示组件 + 数据流） | 无架构图 = 最强「thin paper」信号 |
| **论文层** | Figure caption | 渲染后才写、逐像素核对、定义误差棒、不含 "Figure" 字样、只讲科学不讲管线 | 防「caption 描述一张已改过的图」的视觉谎言 |
| **论文层** | Related Work | challenge-vs-ours map | 让文献综述读起来是「定位贡献」而非「文献堆砌」 |
| **算法层** | 方法结构 | 分层 / hub-and-spoke / multi-plane / 时间线 / 概念图 / 依赖图 | 把算法模块与数据流可视化 |
| **算法层** | 理论结构 | 交换图（tikz-cd）、推导树、反例图 | 支撑 Phase 6a 的推导呈现 |
| **代码层** | 渲染器 | `render_figure.py` 单一 CLI，15 引擎路由（d2/graphviz/tikz/asy/typst/diagrams/blockdiag/svg/mermaid/composite/recipe…） | 所有图必经同一入口，禁止并行裸调 d2/dot/rsvg-convert |
| **代码层** | 审计器 | `figure_audit.py` A1–A11 | 结构级机械判定，`suggested_fixes` 给出精确像素偏移 |
| **代码层** | 样式真相源 | `sciforge_style.py` 的 `TOKENS` / `sanitize_palette` / CVD 校验 | 散文里写的 hex 只是示意，代码里的值才生效 |
| **数据层** | 图的数据源 | `input_data.json`（必须来自真实实验结果） | 禁止 AI 凭记忆画数据图 |
| **数据层** | 图索引 | `FIGURE_INDEX.md` + `.sciforge/verdicts/FIGURE_AUDITS.json` | 一图一源、一图一 verdict，下游一次平读 |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  数据（JSON/矩阵/边表）或图描述 + 冻结 Q-id
  ↓
Step 1   解析 spec：chart type / data / 轴标签(含单位) / title / legend / annotations / Q-id
         → 形状校验（line=2D 坐标、heatmap=2D 矩阵、bar=categories+values、graph=nodes+edges…）
Step 2   选渲染器（auto）：data → Python；5+ 节点图 → d2；≤4 节点 → AI-direct SVG(最后手段)；
         交换图 → tikz-cd；composite → xxx.composite.json；全部经 render_figure.py
Step 3a  Python 管道：apply_matplotlib_style() → 读 input_data.json → 画 → 输出 PDF+SVG
Step 3b  d2 管道：spec.d2 → preamble 注入 → dagre/elk 布局 → 调色板净化 → 双输出 + 审计
Step 3c  AI-direct SVG（≤4 节点）→ 仍走统一 CLI，保留 source.svg
Step 3d  Premium Figure-1 配方（3–4 编号阶段 / 嵌套容器 / 图标词表 / metric glyphs / 单主干箭头）
Step 4   渲染 + 校验（文件非空与 magic bytes、viewBox ≥1200px、颜色审计、字体物理尺寸）
         + caption 纪律（后写、逐像素核对）
Step 4.5 视觉自审（v3.9）：vision-capable 宿主必须打开 output.svg 逐条走 9 项清单，
         写 revision_log.md；text-only 宿主记 skipped-text-only，按机械审计交付
Step 5   生成 latex_include.tex
Step 6   追加 FIGURE_INDEX.md
Step 6.5 upsert .sciforge/verdicts/FIGURE_AUDITS.json
输出  figures/<name>/{output.pdf, output.svg, 源码, input_data.json, figure_audit.json, latex_include.tex}
```

### 5.1 图表类型谱系（12 大类）

Relation（line/scatter/area/step）、Comparison（bar/grouped/stacked/histogram）、Distribution（box/violin/kde/ecdf）、Composition（pie/donut/stacked-area）、Correlation（heatmap/correlation-matrix/pairplot）、3D Surface、Topology（graph/network/tree/flow）、Architecture（layered/hub-and-spoke/multi-plane）、Scientific（errorbar/filled-curve/quiver/streamplot）、Theoretical（commutative-diagram/derivation-tree/concept-map/dependency-graph/counterexample-plot）、Engineering Path / Humanities、**Composite/Group**（subfigure-grid / panel-2x2 / panel-1x3 / panel-2x3 / inset-zoom / dual-axis）。

### 5.2 管道规则（不可协商）

| 图类 | 管道 | 保留源 |
|---|---|---|
| 数据图 | **Python 强制**（matplotlib/numpy） | `render.py` + `input_data.json` |
| 图/架构（5+ 节点） | **d2 强制**（或 graphviz fallback）；两者都无 → BLOCK | `spec.d2` |
| 图（≤4 节点） | AI-direct SVG，仍走统一 CLI | `source.svg` |
| 交换图 | LaTeX `tikz-cd` → PDF | `spec.tex` |
| Composite | `render_figure.py xxx.composite.json`，panel 上限 9 | `composite.json` + 各 panel |

**双输出 PDF+SVG 对所有管道强制**：PDF 是唯一可嵌 LaTeX 的格式，SVG 只供查看/编辑；缺一即 INCOMPLETE 需重渲染。16:9 默认，偏离须写原因。

### 5.3 两层配色

| 层 | 用途 | 规则 |
|---|---|---|
| **Layer 1** Dopamine | 分类/语义色（series / groups / annotations） | 单一真相源 `sciforge_style.TOKENS`（ink/ink-soft/canvas/surface/…/blue/sage/mauve/ochre/taupe/rose/slate/moss/clay）；C* ≥ 30、CVD pairwise ΔE ≥ 15；**禁** Tailwind/Material/tab10/Set2/jet/rainbow/hsv；浅色 token 仅作 fill 且需 `stroke_for()` 深描边 |
| **Layer 2** 连续标量场（heatmap/surface/contour） | `viridis` / `magma` / `plasma`（**禁** jet/rainbow/hsv/coolwarm/bwr） | 感知均匀、色盲安全 |

**两层绝不混用**：heatmap 用分类色是错的，折线用 viridis 也是错的。

### 5.4 v3.10 排版宪法（`figure-layout-contract.md`）

1. **五点 Figure Contract 先于代码**：核心结论（带动词的一句话）+ 证据链（每个 panel 承担 10 种 inferential role 之一）+ archetype + 锁定工具链 + 导出契约；spec 缺 `claim` / `archetype` 直接拒。
2. **Page archetypes 固定几何**：`schematic-led`（hero 45–60% 高，`height_ratios=[2.2,1.0]`）、`asymmetric-hero`、`image-plate`、`clinical-triptych`、`quantitative-grid`。
3. **A11 panel-alignment gate**：共享边/宽/高/间距 **1.5pt 物理容差**，`panel_layout.json` manifest，FAIL 阻断导出；非对称 hero 记为豁免而非放宽容差。
4. **Final-width-first sizing**：`on_page_font_pt = font_pt × W_doc / W_fig` 必须为 1；先按期刊栏宽定 figsize（nature-single 89mm / nature-double 183mm / 高上限 240mm），禁止画大再缩。
5. **人类构造顺序 + AI-slop 红名单**：base → content → 克制箭头 → 精确文字 → 图贴标签；禁纯 box+arrow、禁三色蓝橙紫默认、禁 1/2/3/4 规划标签、禁贴纸徽章。
6. **每 panel 必要性测试**：删掉它若不损失任何独有推断，就不该在主图里。

### 5.5 Figure Budget Contract（v3.4，`/paper-writing` 消费）

| Section | 最小 | 说明 |
|---|---|---|
| Introduction | 0–1 | 可选 motive / frontier-gap map |
| Related Work | **1** | challenge-vs-ours map（v1.7.1 强制） |
| Problem Formalization | 0–1 | 变量依赖图 |
| **Methods / Architecture** | **1（MANDATORY）** | d2 架构图；缺 = `reason_code: missing_architecture_diagram` |
| Theory / Derivation | 0–1 | 交换图 / 推导树 |
| **Results** | **5–8** | 主曲线 + 比较 + 消融 + 敏感性 + 机理探针；**类型多样性 ≥3 种视觉语法** |
| Discussion | 0–1 | 局限性 / 路线图 |
| Appendix | 0+ | 不计入 body |

**body 最少 7 张**：<7 → WARN `figure_budget: below_minimum`；<5 → **FAIL**，无论文字多好都撑不起 Zone-1 投稿。Composite 四面板计 1 张图但提供 4 个视觉单元。

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `FigureSpec` | `claim`, `archetype`, `chart_type`, `q_id`, `axis_labels`, `annotations`, `export_contract` | `ROUTES_TO →` `Renderer`；`COMPILES_TO →` `RenderSource` |
| `Renderer`（15 引擎枚举） | `engine`, `fallback_chain` | `SINGLE_ENTRY →` `render_figure.py` |
| `RenderSource` | `render.py` / `spec.d2` / `spec.tex` / `source.svg` / `composite.json` | `PRODUCES →` `Figure` |
| `Figure` | `output.pdf`, `output.svg`, `caption`, `latex_include.tex`, `aspect_ratio=16:9` | `INDEXED_IN →` `FIGURE_INDEX.md`；`EMBEDDED_BY →` `PaperSection` |
| `FigureAudit` | `A1..A11`, `verdict(PASS/WARN/FAIL)`, `suggested_fixes[{offset_px}]` | `GATES →` `Figure`；`MIRRORED_IN →` `FIGURE_AUDITS.json` |
| `DesignToken` | `name`, `hex`, `chroma`, `L*`, `CVD_deltaE`, `fill_only` | `ENFORCED_BY →` `sanitize_palette` / `palette_check` |
| `DataEncodingColormap` | `viridis/magma/plasma` | `APPLIES_TO →` 连续标量场 |
| `Panel` | `label(a,b,c…)`, `inferential_role`(10 值), `archetype`, `necessity_test` | `COMPOSES →` `CompositeFigure`（≤9 panel，按叙事单元） |
| `FigureBudget` | `per_section_min{}`, `architecture_diagram_present`, `type_diversity` | `CONSUMED_BY →` `paper-writing.Step1` |
| `VisualReview` | `tier1_checklist[9]`, `revision_log.md`, `skipped-text-only` | `CLOSES →` 机械审计管不到的美学 |
| `InputData` | `input_data.json`, 来自 `RESULT.json` | `NUMERIC_SOURCE_OF →` `Figure`（禁止 AI 记忆） |

**核心约束**：`Figure ⇒ PDF ∧ SVG ∧ Source ∧ Audit≠FAIL`；`DataFigure ⇒ PythonPipeline ∧ InputData`；`Composite ⇒ panels≤9 ∧ 每 panel 独立过审`；`BodyFigures ≥7`；`Methods ⇒ ArchitectureDiagram`。

---

## 7. 对应 `scripts/` 代码

### 7.1 `scripts/plotting/render_figure.py` — 单入口（v3.5 / v4.0）

docstring 明列 8+ 条源到产物的链路：

```
d2        spec.d2       -> [preamble inject] -> d2 (dagre/elk) -> svg -> pdf+svg
graphviz  spec.dot      -> dot/neato/fdp     -> svg -> pdf+svg
tikz      spec.tex      -> pdflatex -> pdfcrop -> pdf + svg view
asy/typst/diagrams/blockdiag/mermaid/pikchr/svg/composite/recipe/python …
```

主要函数：`extract_colors` / `palette_check`（L93/L108，拒绝 off-palette）、`render_d2` / `render_method` / `render_graphviz` / `render_tikz`（L128/165/188/201）、`render_python` / `render_recipe`（L231/253）、`render_diagrams` / `render_blockdiag` / `render_mermaid`（L269/306/344）、`render_composite` + `write_composite_tex`（L382/554）、`render_asymptote` / `render_typst` / `render_svg`（L707/727/746）。`--doctor` 做环境自检，`--strict` 时 audit FAIL → exit 4。

### 7.2 `scripts/plotting/figure_audit.py` — A1–A11 机械审计

grep 到 11 个编号 `A1..A11`，对应函数：`audit_outputs`(L113)、`audit_resolution`(L139)、`audit_composite_raster`(L205)、`audit_palette_svg`(L231)、`audit_source_text`(L253)、`audit_typography_svg`(L296)、`audit_layout_svg`(L324)、`audit_contract`(L373)、`audit_complexity`(L390，A7 图标数/边密度)、`audit_richness`(L437)、`audit_brand_leak`(L482)、`audit_text_occlusion`(L746，含 `_text_bbox` / `_seg_intersects_rect` 几何计算)、`audit_panel_alignment`(L954，**A11** 1.5pt 门)、`audit_figure`(L1155) 汇总。`Report` 类（L67）承载 verdict 与 `suggested_fixes`。

### 7.3 `scripts/plotting/figure_recipes.py` — 声明式数据配方

7 种基础 recipe：`line-comparison`(`_line` L179)、`bar-grouped`(`_bar` L193)、`scatter-fit`(`_scatter` L214)、`heatmap`(L234)、`hist-dist`(L271)、`forest-plot`(L283)、**`panel-grid`**(`_panel` L411) + `_render_to_ax`(L550) + `render`(L616)。还有 `_fit_xticklabels` / `_xticks_overlap`(L129/148) 解决分类轴标签碰撞，`_write_panel_manifest`(L354) 输出 `panel_layout.json` 供 A11 对齐门使用。

### 7.4 `scripts/plotting/method_recipes.py` — 方法图模板（L1–L5）

`build_d2(spec)`(L103) 从方法规格生成 d2 源，`_classes`(L70) / `_legend`(L91) 注入 token class，`_words`(L45) 做文字纪律（≤3 行 / ≤4 词），`render`(L217)。

### 7.5 `scripts/plotting/sciforge_style.py` — 配色/字体的**唯一真相源**

docstring 明确：「skill 文档（color-themes.md、unified-plotting、figure-quality-contract）里的 hex 只是示意，**这里的值才支配渲染与审计**」。关键函数：`figsize_full/wide/single/panel`(L164–181)、`palette_visibility`(L198) 区分 fill-only 与 line-eligible、`series_style`(L233)、`add_error_band`(L241)、`legend_top`(L249)、`d2_font_flags`(L339)、`chroma/contrast/lab_delta`(L399/410/456)、`simulate_cvd`(L448)、`pair_distinguishable / palette_distinguishability`(L462/478)、**`sanitize_palette`**(L490) 把引擎偷带的颜色确定性重映射为 token。

### 7.6 两个独立门脚本

| 脚本 | 三查 |
|---|---|
| `scripts/figure_style_gate.py` | ① **figures-follow-text**：每个图的首个 `\ref/\Cref` 必须出现在 figure 环境之前且同节或更早；② **vector-only**：正文只能嵌 PDF / `latex_include.tex`，任何 `.png/.jpg/.jpeg` → FAIL；③ **type diversity**：≥3 种 recipe kind（bar-grouped / line-comparison / scatter-fit / heatmap / hist-dist / forest-plot / method-d2 …）。`exit 2` |
| `scripts/check_figure_embedding.py` | ① 正文 `figure` 环境数 ≥ `--min-figures`；② 磁盘上每个 figure PDF 都被 `\includegraphics`/`\input` 引用；③ `--require-renderer` 时每张图目录必须带 `figure_audit.json` + `latex_include.tex`（防止绕过 `render_figure.py` 手写 PDF）。FAIL → exit 2，`paper-compile` 据此拒编译 |

---

## 8. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `output.pdf` / `output.svg` | `figures/<name>/` | LaTeX / 视觉自审 |
| `render.py` / `spec.d2` / `source.svg` / `composite.json` | 同上 | 复现 |
| `input_data.json` | 同上 | 数据溯源 |
| `figure_audit.json` | 同上 | `--strict` 渲染门 |
| `latex_include.tex` | 同上 | paper-writing |
| `revision_log.md` | 同上 | 视觉自审记录 |
| `FIGURE_INDEX.md` | `figures/` | figure budget 核算 |
| `FIGURE_AUDITS.json` | `.sciforge/verdicts/` | paper-writing / paper-compile 一次平读 |
| `panel_layout.json` | `figures/<name>/` | A11 对齐门 |

---

## 9. 边界、反模式与文档内部不一致

**边界**：禁手改 PNG/SVG 像素；禁在正文嵌 SVG/栅格；禁 AI 直出数据图；禁 off-palette hex；禁 5+ 节点用 AI-direct SVG；禁无 caption / caption 先于渲染；禁复合图 >9 panel；禁并行裸调引擎（必须单入口）。

**三处需要留意的版本残留**（写框架时应以代码为准）：

| 位置 | 冲突 |
|---|---|
| L130 vs L420 | L130「`theme: modern` is permitted since v3.0」，L420「`theme: modern` is prohibited. Override to academic」 |
| L221 / L386 vs `sciforge_style.py` docstring | SKILL.md 先给 axis ≥16pt / ticks ≥13pt，L386 又说 axis<12pt 才拒；代码 docstring 写 axis≥12 / ticks≥10 / title≥13 |
| frontmatter vs L16 | frontmatter 说「12 chart types」，L16 说「15 engines」—— 前者是图表类目数，后者是渲染引擎数，语义不同但易混淆 |

另：Step 4 里出现两个编号「5」与「5b」（caption 纪律），属排版编号重复，不影响语义。

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **FigureSpec 的 `claim` + `inferential_role` 是与语义层最强的接口**：每张图应显式声明它支撑哪个 `ClaimAnchor`，panel 各自承担一个推断角色 —— 这把「图」从装饰变成了 claim 的证据节点。
2. **`input_data.json ← RESULT.json` 的单向数据流**与 GGR 的「不读期望值、从原始行重算」是同一条防作弊原则，可直接把 `Benchmark.model_results` 作为图数据源。
3. **`sanitize_palette` 式的「单一真相源 + 确定性净化」**可迁移到本体关系名：散文里出现的历史别名只做解析，不回写图（与 `relations.py::resolve_relation()` 同构）。
4. **A1–A11 审计 + `FIGURE_AUDITS.json` 平读镜像**是「多产物统一 verdict」的成熟范式，可直接套到 SAU verdict / shape probe / lineage evidence 的汇总上。
5. **Figure Budget 的 per-section 最小值**可作为论文应用层本体的 `Section → REQUIRES_MIN(Figure)` 约束边，由 `paper-writing` 消费。
