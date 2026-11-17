# domain-adaptive-pipeline · 结构不变、强度按签名自适应

> 源文件：`skills/shared-references/domain-adaptive-pipeline.md`（173 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `DomainProfile` |
| **输出节点（对齐）** | `GateVerdict.threshold` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 为 `GateVerdict` 加 `intensity_override` 属性，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
在 26 节点结构不变的前提下，按 `evidence_type / paradigm` 调 Phase 5 / 6a / 11 的强度。
### 1.2 为什么需要
`One universal 26-node pipeline shape; intensity adapts per signature.`；避免硬编码分支或全阶段 MUST。
### 1.3 不做的后果
理论型论文被强制跑重实验；实验型论文图预算不足。

## 2. 输入
### 2.1 输入知识节点
`signature.evidence_type / reasoning_paradigm / mixed_evidence_types`；`user override`。
### 2.2 输入 prompt 模板 / 契约
`Structure is invariant ... only the per-phase emphasis, budget, and gate strictness adapt.`；`Missing fields → default (no override).`
### 2.3 输入产物
`domain-signature.json`、`adaptive-degradation.md` M3、`auto-pipeline/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
`intensity_override.phase_5.{intensity, budget_rounds, budget_words, human_checkpoint_scope}`；`phase_6.{intensity, engine_mode, output_mark}`；`phase_11.{intensity, figure_types, color_compliance, data_heatmap}`。
### 3.2 输出产物
`pipeline-intensity-override.json`：`schema_version / applied_at / source_signature`；`PIPELINE_STATUS.md`；delegation prompt JSON。
### 3.3 传递片段
`MUST include the intensity_override JSON so the skill adapts accordingly`。

## 4. 判定与门
REDUCED / STANDARD / INTENSIFIED / REPLACED / SKIPPED；1 round≤200 / 2 rounds≤600 / 3 rounds≤1200 / 1 round≤300 words；mixed → MOST INTENSE；REPLACED 仅 ALL；3-round cap 不变。

## 5. 上下游
`/domain-learner` + orchestrator → 本契约 → `/method-registry`、`/theory-derivation`、`/unified-plotting`、`/auto-review-loop`。

## 6. 映射
`paperapp/registry.py::DomainProfile{evidence_type, reasoning_paradigm, learning_confidence}` 是本项目对应落点。
