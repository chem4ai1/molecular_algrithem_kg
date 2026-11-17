# engineering-grounding-contract · 想法可实现性 8 维量化

> 源文件：`skills/shared-references/engineering-grounding-contract.md`（233 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `2.5b` |
| **输入节点（对齐）** | `IdeaNode` |
| **输出节点（对齐）** | `IdeaNode.eg_average`/`eg_tier` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `IdeaNode` 加 eg_average/tier 属性；8 维打分不拆成节点 |

## 1. 解决的问题
### 1.1 核心问题
从 AI agent 视角量化「能否实现想法」，给出风险等级与缓解路径。
### 1.2 为什么需要
`Innovation without implementability is a gamble.`；只做标签/路由/缓解，不简化想法。
### 1.3 不做的后果
极优想法因算力/依赖完全跑不了，浪费全链预算。

## 2. 输入
### 2.1 输入知识节点
`IdeaCandidate.Compute Footprint / Dependency Chain / AI Dev Cycle / Code Complexity / Regulatory Readiness`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；N/A 必须给理由；Stage 1 必须是最便宜的 falsification；HEAVY/CONSTRAINED 不消除。
### 2.3 输入产物
`support/adversarial-falsification/SKILL.md`（Phase 2.5b 生产者）。

## 3. 输出
### 3.1 输出知识节点
`EG.eg_average / tier`；`IdeaCandidate.engineering_grounding`；`NoveltyCheck.engineering_grounding`；`ResultToClaim.ai_engineering_grounding`。
### 3.2 输出产物
`refine-logs/ENGINEERING_GROUNDING.md`：8-Dimension Scores / EG Average / AI Engineering Path；`figures/engineering-path/ENGINEERING_GROUNDING_PATH.pdf`。
### 3.3 传递片段
无。

## 4. 判定与门
`eg_average ≥6.0 READY`；3.0–5.9 CONSTRAINED；<3.0 HEAVY；≥3 sub-dimensions=0 → BLOCKED；N/A=10/10；复合分 `novelty×0.45 + feasibility×0.25 + relevance×0.15 + EG×0.15`。

## 5. 上下游
idea-discovery / adversarial-falsification Phase 2.5b → 本契约 → novelty-check / result-to-claim / auto-review-loop / unified-plotting。

## 6. 映射
评估 RDKit / 数据集 / 力场 / 分子模拟依赖与代码复杂度，输出三阶段 AI 实施路径。
