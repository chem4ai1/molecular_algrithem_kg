# 指导 · 图、写作与评审独立性（14 份）

> **覆盖源文件**：`color-themes.md`(103) · `figure-complexity-contract.md`(280) · `figure-layout-contract.md`(277) · `figure-quality-contract.md`(186) · `figure-quality-review.md`(115) · `writing-principles.md`(208) · `paper-voice-contract.md`(200) · `paper-modes.md`(225) · `citation-discipline.md`(57) · `venue-checklists.md`(138) · `venue-profiles.md`(121) · `reviewer-independence.md`(36) · `reviewer-routing.md`(42) · `review-tracing.md`(123)
> **一句话**：这组文件规定「成果怎么变成可发表稿件」以及「评审必须独立于执行者」。与 [03-figures-presentation/unified-plotting.md](../03-figures-presentation/unified-plotting.md) 配套：那边是 skill 契约，这边是它引用的共享契约。

---

## 1. 图的五份契约（分工别搞混）

| 文件 | 管什么 | 关键硬规则 |
|---|---|---|
| `color-themes.md` | 配色 | **Layer 1 Dopamine**（分类/语义色，与 `sciforge_style.py` 完全一致）+ **Layer 2 连续标量场**（`viridis/magma/plasma`）；§三道安全网（C* ≥30、CVD ΔE ≥15、浅色 token 只做 fill 且需深描边）；§Forbidden colors（Tailwind / Material / tab10 / Set2 / jet / rainbow / hsv）；**两层绝不混用** |
| `figure-quality-contract.md` | 输出质量底线 | 16:9 默认；§1.5 期刊栏宽预设（nature-single 89mm / nature-double 183mm）；**PDF + SVG 双输出不可协商**；Nature 可读性下限；d2 复杂架构图流程；SVG→PDF 转换工具链 |
| `figure-complexity-contract.md` | 反「小学水平方框图」 | §0 学科中立；§0.5 跨领域 Figure Role Typology（角色 × 引擎映射）；§1 组件丰富度下限（≥60% 自绘图标）；§2 视觉层级（≥2 层分组）；§3 **Edge Governance**（边密度 ≤1.6）；§4 文本纪律；§4.5 分层模型（零文本重叠）；§4.6 review |
| `figure-layout-contract.md` | 排版宪法 | §1 **五点 Figure Contract 先于代码**（claim + 证据链 + archetype + 锁定工具链 + 导出契约，缺 `claim`/`archetype` 直接拒）；§2 panel 的 10 种 inferential roles；§3 Nature 2026 语料的 locked page archetypes；§5 **A11 panel-alignment gate 1.5pt 物理容差**；§6 final-width-first sizing |
| `figure-quality-review.md` | 视觉自审 | 先做 **Capability detection**（一次/run）；class V 宿主 **Tier 1 agent-native 视觉自审 MANDATORY**（9 项清单 + `revision_log.md`）；Tier 2 外部优化顾问 OPTIONAL；text-only 宿主记 `skipped-text-only` 并按机械审计交付 |

**执行顺序**：写五点 contract → 选 archetype → 定 final width → 选配色层 → 走 `render_figure.py` 单入口 → `figure_audit.py` A1–A11（含 A11 对齐）→ 视觉自审 → `figure_style_gate.py` + `check_figure_embedding.py`。

> **唯一真相源提示**：`color-themes.md` 里的 hex 只是示意，实际渲染与审计以 `scripts/plotting/sciforge_style.py` 的 `TOKENS` 为准（`sanitize_palette` 会把引擎偷带的颜色确定性重映射）。字体 pt 下限在 SKILL.md 与代码 docstring 之间有版本残留，**以代码为准**。

---

## 2. 写作三份契约

### 2.1 `writing-principles.md`（208 行）

| 节 | 指导 |
|---|---|
| §0 Per-Discipline Style Contract (v2.2.1) | 按领域签名选风格，不是一套模板打天下 |
| **§0.5 Anti-AIGC Human-Voice (v5.2)** | 与 `leakage_scan.py` 的 **Class J** 对应：删 "delve" / "tapestry" / "It is worth noting that" 等 AIGC 痕迹词 |
| **§0.6 SCI Body Voice** | **stance-first、zero-apology、zero-defense**；正文不做预防性自我辩护，hedge 只能是精确的 regime 陈述。`deepen` 模式强制此口径 |
| Narrative principles / 篇幅预算 | 主文 vs 附录摆放与长度预算（v1.4.0） |
| Abstract | **5 句式公式** |
| Intro | 三段式（前沿基线 / delta / why-not-before，来自 `FRONTIER_GAP.md`） |

### 2.2 `paper-voice-contract.md`（200 行）

| 节 | 硬规则 |
|---|---|
| §1 Claim discipline | **CRITICAL EVALUATION RULE**：claim 强度不得超过证据（`result-to-claim` 的 3-fidelity 门） |
| §2 Section templates | bullet-locked，不得随意增删 bullet |
| §3 Citation obligation | **EXHAUSTIVE**：所有主张都要有出处 |
| §4 Caption discipline | 渲染后才写、定义误差棒、不含 "Figure" 字样、只讲科学不讲管线 |
| §4b Internal-term substitution table (v1.7.1) | **leakage class L**：把内部术语（MCTS / DAG / background dispatch / effort:lite / `derivations/` …）换成学科语言 |
| §5 Negative vocabulary list | **delete on sight** |
| §6 Reviewer-facing scoring | 反通胀打分（给 panel 与 self-review 用） |

### 2.3 `paper-modes.md`（225 行）

单一骨架不变，**5 种模式**选章节集与强调矩阵：§3 Per-Mode Section Layouts、§4 Emphasis Matrix、§5 Page Target Bands。`discipline-writing.md` 的章节集是 mode-selected（引用本文件 §3），`venue-profiles.md` 的页数也是 mode-aware。**先选 mode，再定章节与页数**。

---

## 3. 引用与投稿模板

### 3.1 `citation-discipline.md`（57 行）

**3 层反幻觉验证**（与 `/universal-retrieval` 一致）：arXiv 批查 → CrossRef DOI → S2 fuzzy ≥0.6；Final Verification Checklist；BibTeX 管理规则（唯一 `references.bib`、禁 `\cite{TODO}` / `forthcoming` / 手写条目）；Common Template；Quick Reference。

下游更严的两道：`scripts/doi_gate.py`（每条 `@entry` 必须有 DOI，且解析出的标题与 bib 标题 token-overlap ≥0.8）、`scripts/citation_support.py`（含数字/比较级的句子必须同句有 `\cite{}`，每个 bib key 至少被引用一次）。

### 3.2 `venue-profiles.md` + `venue-checklists.md`

| 文件 | 内容 |
|---|---|
| `venue-profiles.md`(121) | **单一模板 `elsarticle`（preprint）** + 统一骨架 + mode-aware 页数 + 引用风格；§4 Submission-Time Venue Adaptation 是 **deferred / optional**；§6 加新问题专属惯例的通道 |
| `venue-checklists.md`(138) | §1 何时读；§2 所有问题通用要求；§3 **单一统一清单**（不按 venue 分叉）；§4 投稿时适配（延迟、可选）；§5 边界 |

**指导**：默认按单模板写，不要为「投某个会」在生成阶段分叉；venue 适配留到投稿时做，且是可选的。

---

## 4. 评审独立性三件套

| 文件 | 核心 |
|---|---|
| `reviewer-independence.md`(36) | §Core Principles；§What the Reviewer **MAY** Access；§What the Reviewer **MUST NOT** Access；Implementation。核心是 **reviewer-only-raw-artifacts**：只给路径与原始产物，**不给执行者的解释/引导性结论**（与 `methodology-and-context-contract.md` §5、`auto-pipeline` §Context Economy 第 6 条同源） |
| `reviewer-routing.md`(42) | §Role Definitions + §Role-Switching Flow：单 agent 下 **researcher → reviewer → adjudicator** 三轮角色轮换；§Integration with OSS 说明如何与 `/auto-review-loop` 对接 |
| `review-tracing.md`(123) | §When to Trace / §Trace Directory / §How to Trace / §File Schemas / §Configuration / §Integration with Event Log / §Privacy。给每轮评审留可复核轨迹，并与事件日志联动 |

**与 persona 的关系**：`reviewer-prompts/README.md` + `economics.md` 提供「评审人格内容」，这三份提供「评审过程约束」。两者都要满足：pointer-load persona（不 inline）+ 只喂原始产物（不喂结论）+ 角色轮换 + 留 trace。详见 [reviewer-prompts-guide.md](reviewer-prompts-guide.md)。

---

## 5. 图 / 写作 / 评审的接线检查清单

**图（Phase 11）**
- [ ] 五点 Figure Contract 写在代码之前，含 `claim` 与 `archetype`
- [ ] 按期刊栏宽定 figsize（final-width-first），`on_page_font_pt` 校验通过
- [ ] Layer 1 / Layer 2 配色选对且未混用；无 forbidden colors
- [ ] 组件丰富度 ≥60% 自绘图标、边密度 ≤1.6、≥2 层分组
- [ ] PDF + SVG 双输出；A1–A11 通过（含 A11 1.5pt 对齐）
- [ ] 视觉自审 9 项已走并写 `revision_log.md`（text-only 已标 `skipped-text-only`）
- [ ] Figure Budget：Methods 架构图存在、body ≥7、类型多样性 ≥3

**写作（Phase 12）**
- [ ] mode 已选，章节集 / 页数 / 强调矩阵与之一致
- [ ] `paper-voice-contract.md` §4b 的内部术语替换已做（`leakage_scan.py` Class A–J 通过）
- [ ] Anti-AIGC 词表清理完成；正文 stance-first、无道歉/防御
- [ ] caption 渲染后写、定义了误差棒、不含 "Figure"
- [ ] 每个数字来自 `RESULT.json` / `input_data.json`，无凭记忆填数
- [ ] claim 强度 ≤ evidence fidelity；阴性结果进 Limitations

**引用（Phase 15）**
- [ ] 3 层验证 + `doi_gate` + `citation_support` 全过
- [ ] 无 orphan reference、无 `\cite{TODO}`、无手写 BibTeX
- [ ] 正文引用顺序符合 `figure_style_gate.py` 的 figures-follow-text

**评审（Phase 14）**
- [ ] persona 用 canonical 路径加载，未 inline 副本
- [ ] reviewer 只收到路径 + raw artifacts
- [ ] 角色轮换三轮已走；`review-tracing` 已留痕
- [ ] 分数阈值按 6.0 / 8.0 分开处理（见 [03-ideation-and-evaluation.md](03-ideation-and-evaluation.md) §4.4）

---

## 6. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中：`DesignToken` / `Panel` / `FigureBudget` / `FigureAudit` / `VisualReview` / `PaperSection` / `Caption` 类来自本组前五份与 `writing-principles`；`reviewer independence` 对应元原则 P3「机械判定先于 LLM 判断」在评审侧的镜像（reviewer 不被执行者结论污染）。
`paper-voice-contract.md` §4b 的内部术语替换表，正是 GGR 报告「**不得把管线痕迹写进正文**」的同一条要求。
