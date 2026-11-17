# competitive-drift-monitor · 竞品差异化衰减季度监控

> 源文件：`skills/shared-references/competitive-drift-monitor.md`（254 行） · 类型：shared-reference（advisory 协议）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·项目治理 |
| **SciForge 26 节点** | — |
| **输入节点（对齐）** | 无（季度监控） |
| **输出节点（对齐）** | 无（不进论文图） |
| **对齐状态** | 无法对齐 |
| **节点增补建议** | 不建议新增节点：同上，属外部 advisory 协议 |

## 1. 解决的问题
### 1.1 核心问题
按季度监控竞品是否追平/反超 OSS 差异化，触发更新 PR。
### 1.2 为什么需要
竞争优势会衰减；静态「我们领先」声明而无监控本身即一种 fantasy。
### 1.3 不做的后果
差异化被无声反超，路线图失效。

## 2. 输入
### 2.1 输入知识节点
`differentiator.decay_state ∈ STILL_LEADING/CLOSING/PARITY/OVERTAKEN`；transition rubric；`competitor_activity`；`pr_triggered`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`this skill itself is not bundled in OSS (deferred/external) ... nothing in the pipeline gates on this document.`
### 2.3 输入产物
`competitive-analysis.md` v2.5 静态快照；`domain-contribution-protocol.md` PR SLA；`universal-retrieval` 竞品扫描。

## 3. 输出
### 3.1 输出知识节点
4 态 decay；4 差异化 rubric；`evidence_url`；`reframe`；tracked competitors（AI-Scientist / ChemCrow / Eureka / PaperBench 等）；6 条 fallback。
### 3.2 输出产物
`refine-logs/competitive-drift-report-<YYYYQQ>.json`：`period / previous_snapshot / differentiators[] / evidence / action / pr_triggered / strategic_risk_escalated`；同名 .md；更新 PR。
### 3.3 传递片段
无。

## 4. 判定与门
| 判据 | 动作 |
|---|---|
| off STILL_LEADING | UPDATE_PR |
| OVERTAKEN | strategic-risk issue（非 PR） |
| 4 季度无活动 | `suspicious_quiet=true` |
| PR DRAFT | 不 auto-merge |
| 2+ transition | 合 1 个 PR |

## 5. 上下游
季度 cron / manual → 本协议 → 更新 competitive-analysis.md；当前不 gate 任何流水线。

## 6. 映射
对外差异化能力应纳入 4 维 decay_state 季度监控，反超时走人工战略评审。
