# methodology-and-context-contract · 分析方法与上下文经济

> 源文件：`skills/shared-references/methodology-and-context-contract.md`（74 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | 全部阶段产物 |
| **输出节点（对齐）** | 停止规则 / 摘要（属性级） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：属上下文经济约束，不产生知识节点 |

## 1. 解决的问题
### 1.1 核心问题
规定单代理全流程中「分析何时够」「每步给多少 context」「哪些属于 pipeline 边界」。
### 1.2 为什么需要
`Consuming skills must pointer-load it by path ... rather than re-asserting their own partial copies.`
### 1.3 不做的后果
过度分析、上下文膨胀、复制规则、伪造图。

## 2. 输入
### 2.1 输入知识节点
`stopping_rule.satisfied`；`finding.raw_stat / confidence / method`；`phase.bundle.md`；prior artifact line count；`*_STATE.json / *_HASH.txt`；`deferred`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 orchestrator 与 consuming skills pointer-load。
### 2.3 输入产物
`orchestrator/auto-pipeline/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`stopping_rule.satisfied`；SHA-256 locked hash；figure 5-element contract；`missing_inputs`；phase state；`boundary=deferred`。
### 3.2 输出产物
`refine-logs/`：bundle.md / 20–40 line summary / `*_STATE.json` / `*_HASH.txt`。
### 3.3 传递片段
Every finding shipped must carry `raw_stat + confidence + method`；缺证据写 placeholder 并列入 Assumptions / missing inputs，never fabricate。

## 4. 判定与门
停止需 mandatory fields assigned + determination unchanged across two consecutive rounds + marginal return ≤0；hash mismatch refuses proceed；deterministic checks before LLM judgment。

## 5. 上下游
orchestrator + consuming skills → 本契约 → 24 个 SKILL、分析输出、reviewer 输入、figure 渲染。

## 6. 映射
每次分子假设分析写 `raw_stat/confidence/method`；>200 行先 compact；冻结 oracle/结果后 hash lock。
