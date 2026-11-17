# effort-contract · 工作量深度轴（与审计轴正交）

> 源文件：`skills/shared-references/effort-contract.md`（171 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `RunState`(运行配置) |
| **输出节点（对齐）** | 无（深度轴） |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 把 `effort`/`assurance` 作为已建议 `RunState` 的属性，不单独建类 |

## 1. 解决的问题
### 1.1 核心问题
让 `effort` 只控制广度/深度/迭代，不削弱跨模型审查与审计质量。
### 1.2 为什么需要
`This affects breadth, depth, iterations, and coverage — but never the quality of cross-model review.`；effort 是深度轴，assurance 是审计轴。
### 1.3 不做的后果
lite 档跳过强制审计，把「做更少」误当「审更松」。

## 2. 输入
### 2.1 输入知识节点
`RunConfig.effort / assurance`；`Skill.EFFORT`；`Knob.review_rounds`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；每个 skill stdout 打印 active effort / derived knobs / `reviewer reasoning effort: maximum (always)`。
### 2.3 输入产物
`assurance-contract.md`。

## 3. 输出
### 3.1 输出知识节点
`ResearchLit.papers_found`；`IdeaDiscovery.ideas_generated`；`ExperimentPlan.seeds`；`AutoReviewLoop.max_rounds`；`Audit.verdict`。
### 3.2 输出产物
无新增文件（stdout 打印配置）。
### 3.3 传递片段
reviewer reasoning effort stays at maximum（无论 effort 档位）。

## 4. 判定与门
lite≈0.4x / balanced=1x / max≈2.5x / beast≈5–8x；lite/balanced→draft，max/beast→submission；FAIL/BLOCKED/ERROR/STALE 阻断 Final Report。

## 5. 上下游
user / orchestrator → 本契约 → 每个 SciForge skill；审计门转交 `assurance-contract.md`。

## 6. 映射
按预算选档；提交前用 max/beast 触发 mandatory audits。`paperapp/config.yaml` 可承接档位。
