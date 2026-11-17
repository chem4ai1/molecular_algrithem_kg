# competitive-analysis · OSS 竞品定位与优化路线（静态快照）

> 源文件：`skills/shared-references/competitive-analysis.md`（179 行） · 类型：shared-reference（战略文档）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·项目治理 |
| **SciForge 26 节点** | — |
| **输入节点（对齐）** | 无（战略快照） |
| **输出节点（对齐）** | 无（不进论文图） |
| **对齐状态** | 无法对齐 |
| **节点增补建议** | 不建议新增节点：属项目战略文档，不是论文生成过程的知识节点 |

## 1. 解决的问题
### 1.1 核心问题
论证 SciForge-OSS 相对竞品的差异化与优化路线。
### 1.2 为什么需要
确立「no full-loop (no experiments run)、pure theoretical validation but taken to the extreme — 80-90% landing rate」的核心定位。
### 1.3 不做的后果
差异化声明无依据，无法指导后续 v2.8 监控。

## 2. 输入
### 2.1 输入知识节点
`差异化.领域自适应 / fantasy prevention(5门) / landing confidence / graceful degradation`；`capability` 等级 A+/S。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；核心定位句为静态快照。
### 2.3 输入产物
`engineering-grounding-contract.md`（v2.9 落地置信度细节）。

## 3. 输出
### 3.1 输出知识节点
4 差异化；5 项计划（领域签名库 / 落地置信度 / 多框架输出 / 社区贡献 / Ouroboros 集成）；matrix Current v2.4 / Target v3.0；目标 50+ 领域。
### 3.2 输出产物
无新增文件；公式 `grounding_confidence = 0.6×OSS_sandbox + 0.4×engineering`；`composite = novelty×0.45 + feasibility×0.25 + relevance×0.15 + EG×0.15`。
### 3.3 传递片段
无。

## 4. 判定与门
无机械门，由 `competitive-drift-monitor.md` 用 transition rubric 季度核验。

## 5. 上下游
competitive-drift-monitor（作基线快照）/ 核心团队 → 本分析 → 4 differentiator 与 reframe 方向。

## 6. 映射
分子设计主张须 SymPy + 逻辑审计 + falsification 且给 landing confidence。
