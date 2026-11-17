# paper-writing · 五模式章节集与 elsarticle 全稿组装

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/paper-writing/SKILL.md`（396 行）
> 类型：support · Phase 12（MUST） · 代码佐证：`scripts/leakage_scan.py`、`scripts/figure_style_gate.py`、`scripts/check_figure_embedding.py`、`scripts/claim_anchor_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 |
| **SciForge 26 节点** | `12` |
| **输入节点（对齐）** | `SectionPlan`；`Evidence`；`CitedPaper`；`Contribution` |
| **输出节点（对齐）** | `SectionDraft`(task-w, status/cited/evidence) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：`SectionDraft` 已定义 INSTANCE_OF→SectionPlan、USES_EVIDENCE→Evidence、CONSULTED→ConsultedPaper 三条边，完整覆盖 |

## 1. 解决的问题

### 1.1 核心问题
按 `verification_type` 选择五模式章节集，组装统一 `elsarticle` LaTeX 全稿，并保证 claim 可追溯、正文无流水线痕迹。

### 1.2 具体场景 / 为什么需要
- `If FRONTIER_GAP.md is absent, the Introduction MUST emit [needs-frontier-positioning].`
- 消费 `paper-modes.md`（哪些节）与 `paper-voice-contract.md`（怎么写）。
- 正文中的管线痕迹（内部 Q-id、schema 路径）会导致 desk reject。

### 1.3 不做的后果
- 贡献定位靠临时编造；claim 与证据脱钩；图未被引用。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Claim` | `statement / polarity` | Phase 10 | 必须 |
| `Figure` | `caption` | Phase 11 | 必须 |
| `VerifiedPaper` | `cite_key` | Phase 4 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `paper-modes.md`、`paper-voice-contract.md` | 章节集 / 语气 |
| Intro 前提 | `If FRONTIER_GAP.md is absent, the Introduction MUST emit [needs-frontier-positioning].` | 缺前沿定位不得硬写 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/FINAL_PROPOSAL.md` | Q-id |
| `refine-logs/FRONTIER_GAP.md + FRONTIER_MAP.json` | Intro |
| `literature/references.bib` | 引用 |
| `derivation_output.md` | 推导 |
| `LOGIC_VERIFICATION.md + LEAKAGE_AUDIT.md` | 审计 |
| `CLAIMS_FROM_RESULTS.md` | claim |
| `figures/FIGURE_INDEX.md` | 图索引 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `PaperSection` | `section_type / body` |
| `SectionDraft` | `section` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `paper/PAPER_PLAN.md` | `frontier_positioning_missing` | 计划 |
| `paper/main.tex` | — | 主文件 |
| `paper/sections/*.tex` | — | 章节 |
| `paper/Z_reproducibility.tex` | — | 复现声明 |
| `paper/PAPER.md` | — | Markdown 版 |
| `paper/LEAKAGE_SCRUB.json` | `status / hits_remaining` | 清洗门 |
| `paper/PAPER_CLAIM_AUDIT.json` | `aigc_scan` | claim 审计 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无 | — | — |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| leakage scrub | `leakage_scan.py` | grep A–I 且 `hits_remaining=0` | `0` | `BLOCKED: pipeline_leakage_not_scrubbed` |
| 图嵌入 | `check_figure_embedding.py` | FAIL | exit 2 | 阻塞 |
| 图样式 | `figure_style_gate.py` | 先引用 / vector / ≥3 recipe kinds | `3` | FAIL |
| 图预算 | skill 内 | `<7` WARN，`<5` FAIL | `7 / 5` | FAIL 阻断 |
| 复现声明 | skill 内 | `missing_reproducibility_statement` | — | FAIL |
| 阴性结果 | skill 内 | `negative_result_as_contribution` | — | 必写 |
| claim 锚 | `claim_anchor_gate` | `resolved=true` / 哈希稳定 | — | FAIL |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/result-to-claim` + `/unified-plotting` | Phase 12 `/paper-writing` | `/paper-compile` → `/auto-review-loop` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `PaperSection / Caption` | `applayer` 应用层节点 | 否 |
| `LeakageScrub` | `paperapp` gate 门 | 否 |
| `frontier baseline / delta / why-not-before` 三元组 | `FRONTIER_GAP.md` 已有 | 否 |
