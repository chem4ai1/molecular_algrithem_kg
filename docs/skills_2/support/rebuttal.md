# rebuttal · 逐点反驳信（引用 → 承认 → 证据回应 → 精确改稿）

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/rebuttal/SKILL.md`（164 行）
> 类型：support · Phase 14+（advisory，人审）。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 反驳预演（响应） |
| **SciForge 26 节点** | `14`+ |
| **输入节点（对齐）** | `ReviewPoint`；`SectionDraft`；`ExperimentArm` |
| **输出节点（对齐）** | `ReviewPoint.response`(字段回填)；`RunArtifact`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-w 节点 `RebuttalLetter`(claims[]/response_class/diff)：反驳信需逐点引用实验凭证，`ReviewPoint.response` 只是单条字段 |

## 1. 解决的问题

### 1.1 核心问题
按 review / rejection 生成逐点反驳信；rebuttal 是法律文书，**不得承诺未做的实验**。

### 1.2 具体场景 / 为什么需要
- `Quote, then answer. Every point: verbatim quote → concession → evidence-backed response → exact manuscript change.`
- `wording-only` 被视为 anti-shrinkage FAIL。
- 每轮最多 3 个 contested 点。

### 1.3 不做的后果
- 声称补充了不存在的实验 → 学术诚信红线；只改措辞被判 `round_invalid`。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `ReviewPoint` | `axis / attack` | review | 必须 |
| `Claim` | `statement` | Phase 10 | 必须 |
| `RebuttalLetter` | `claims` | 本 skill 产出 | 必须 |
| `Evidence` | `quote` | 证据层 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Letter Skeleton | `We thank the reviewers for ... . Below we respond point-by-point` | 书信骨架 |
| Key Rules | `Quote, then answer. Every point: verbatim quote → concession → evidence-backed response → exact manuscript change.` | 四段式 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `AUTO_REVIEW.md`、`REVIEW_STATE.json`、`REVIEW_LEDGER.json` | 评审 |
| `paper/main.tex + sections/*.tex` | 稿件 |
| rejection letter（可选） | 拒稿信 |
| `EXPERIMENT_MATRIX.json + EXPERIMENT_LOG.md` | 实验凭证 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `ReviewPoint` | `response` |
| `RebuttalLetter` | `claims` |
| `Evidence` | `quote` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `paper/REBUTTAL_LETTER_{YYYYMMDD_HHmmss}.md` | — | 时间戳版 |
| `paper/REBUTTAL_LETTER.md` | `response_class / old-new diff` | 当前版 |
| `.sciforge/MANIFEST.md` | one row | 产物登记 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（人审后交投稿） | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 新实验证明 | skill 内 | `EXPERIMENT_MATRIX` cell completed 或 `EXPERIMENT_LOG` run logged | — | 否则标 pending / 矩阵 ID |
| shrink 门 | skill 内 | wording-only | → FAIL `shrinkage_only_response` | 重写 |
| contested 上限 | skill 内 | `≤3 / round` | `3` | 分批 |
| 无 review points | skill 内 | — | → stop | — |
| KILL 级 | skill 内 | — | → `/kill-argument` | 换题 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/auto-review-loop` / rejection | `/rebuttal` | `/paper-writing`（应用改动）→ 用户投稿 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `RebuttalLetter.claims[]` 必链 `ExperimentRun` | `DK-P4-13` | 否 |
| `dispatch_id` 缺失不得声称新实验 | `ExperimentRun` 产物 | 否 |
| contested ≤3/round | 人工决策预算 | 否 |
