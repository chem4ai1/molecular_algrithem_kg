# publishability-score · Phase 15.5 六维投稿评分与主逻辑一票否决

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/publishability-score/SKILL.md`（180 行）
> 类型：support · Phase 15.5（MUST） · 代码佐证：`scripts/fairness_gate.py`、`PUBLISHABILITY_SCORE.schema.json`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `15.5` |
| **输入节点（对齐）** | `Contribution`；`ExperimentArm`；`FailureCheck`；`ReviewPoint` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-r 节点 `PublishabilityScore`(dimensions/total/main_logic_gating)：需要六维评分与主逻辑一票否决，`FailureCheck` 无法表达维度结构 |

## 1. 解决的问题

### 1.1 核心问题
六维评分给出投稿 go/no-go，**主实验逻辑轴为主轴**，区分 `SUPPLEMENTARY_GAPS` 与 `NOT_PUBLISHABLE_NO_MEAN`。

### 1.2 具体场景 / 为什么需要
- 好文笔不能掩盖主逻辑失败：`dim1<0.5 → cap 0.4 / NOT_PUBLISHABLE_NO_MEAN`。
- `benchmark_ready` 只在 `SUBMISSION_READY ∧ dim1=1.0 ∧ dim3≥0.8` 时成立。

### 1.3 不做的后果
- 证据虚但写作好的论文被误判可投，浪费投稿周期。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Claim` | `fidelity / evidence_sufficiency` | Phase 10 | 必须 |
| `GateVerdict` | `state` | 各门 | 必须 |
| `ExperimentNode` | `stage` | Phase 6c | 必须 |
| `EvidenceNormProfile` | `sample_size_norm` | Phase 1b | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `PUBLISHABILITY_SCORE.schema.json`、`output-protocol.md` | schema / 产物 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `paper/main.pdf / main.tex`、`COMPILE_REPORT.json` | 稿件与编译 |
| `experiments/toy/RESULT.json`、`full/STATUS.json`、`EXPERIMENT_RESULTS.json` | 实验 |
| `CLAIMS_FROM_RESULTS.md`、`LOGIC_VERIFICATION.json`、`LEAKAGE_AUDIT.json` | claim 与审计 |
| `REVIEW_REPORT.md / KILL_ARGUMENT.md`、`FINAL_PROPOSAL.md`、`PIPELINE_STATUS.md` | 评审与状态 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `PublishabilityScore` | `total_score / verdict / dimensions / main_logic_gating` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/verdicts/PUBLISHABILITY_SCORE.json` | `q_id / scored_at / verdict / total_score / dimensions / main_logic_gating / missing_experiments / benchmark_ready` | 机读 |
| `.sciforge/audits/PUBLISHABILITY_SCORE.md` | 人读报告 | — |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（供 orchestrator 终门读） | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 总分 | skill 内 | `total = 0.25×dim1 + 0.15×(dim2+dim3+dim4+dim5+dim6)` | — | — |
| 主逻辑封顶 | skill 内 | `dim1<0.5` | cap 0.4 | `NOT_PUBLISHABLE_NO_MEAN` |
| SUBMISSION_READY | skill 内 | total≥0.80 且 dim1≥0.8 | `0.80 / 0.8` | — |
| SUPPLEMENTARY_GAPS | skill 内 | 0.55–0.79 且 dim1≥0.7 | — | 补实验 |
| NEEDS_MAJOR_REVISION | skill 内 | 0.40–0.54 且 dim1≥0.5 | — | 大修 |
| benchmark_ready | skill 内 | SUBMISSION_READY ∧ dim1=1.0 ∧ dim3≥0.8 | — | — |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/citation-audit` | Phase 15.5 `/publishability-score` | orchestrator 终门 / 用户 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `PublishabilityScore` | `paperapp` gate 产物 | 否 |
| 主逻辑轴一票否决 | `DK-P4-18` | 否 |
| `fairness_gate PASS` | 与 `s1` 硬门对齐 | 否 |
