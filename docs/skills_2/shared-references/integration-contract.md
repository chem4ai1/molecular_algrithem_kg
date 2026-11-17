# integration-contract · 跨技能调用必须有机器证据

> 源文件：`skills/shared-references/integration-contract.md`（248 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `GateVerdict`；产物 |
| **输出节点（对齐）** | `GateVerdict.state` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：5 个机器证据组件可由 verdict/artifact 属性表达 |

## 1. 解决的问题
### 1.1 核心问题
避免只在 prose 里写 MUST 却静默不执行：跨技能委托必须有 5 个组件。
### 1.2 为什么需要
`SKILL.md prose can describe an integration; it cannot guarantee one.`；prose-only 在上下文压力下必失败。
### 1.3 不做的后果
audit gate bypass 与 wiki ingest no-op 同源：缺 artifact、verifier、activation predicate。

## 2. 输入
### 2.1 输入知识节点
`activation.predicate / concrete.artifact / phase.checklist / backfill.command / verifier.exit_code`；`assurance=submission`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；5 组件必须齐全；verifiers must be external processes。
### 2.3 输入产物
`artifact-registry.md`（canonical filename / producer / consumer / schema）。

## 3. 输出
### 3.1 输出知识节点
NOT_APPLICABLE / BLOCKED；`INVARIANT_CHECK.json`；`PROOF_AUDIT.json / PAPER_CLAIM_AUDIT.json / CITATION_AUDIT.json`；live integration registry。
### 3.2 输出产物
`.sciforge/verdicts/INVARIANT_CHECK.json`（6-state verdict）。
### 3.3 传递片段
无。

## 4. 判定与门
predicate false → NOT_APPLICABLE；true 但缺 input → BLOCKED + backfill hint；REGISTRY_HASH mismatch → BLOCK；LEAKAGE_AUDIT verdict ∈ {PASS, WARN}；exit 1 blocks Final Report。

## 5. 上下游
orchestrator / caller skill → 本契约 → callee skills、invariant-check、submission verifier、artifact-registry。

## 6. 映射
「检索→分子生成→性质评估→成文」每步都要有触发谓词、JSON 回执、回填命令与退出码校验。

## 7. 边界
本项目 `sciforge/contracts.py::VERDICT_STATES` 是 6 态唯一实现点。
