# invariant-check · 阶段边界结构门与 INV-G1 冻结校验

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/invariant-check/SKILL.md`（167 行）
> 类型：support · 横切（四个阶段边界） · 代码佐证：`scripts/validate_verdicts.py`、6 态 verdict。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | 四边界 |
| **输入节点（对齐）** | `ResearchQuestion`；`Paper`；`Contribution` |
| **输出节点（对齐）** | `FailureCheck`(task-r)；`GateVerdict`(paperapp) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `FailureCheck.note` 记录 INV-G1 结果即可，不必新增类；但需为 `GateVerdict` 加 `checks[]` 字段以保留逐项证据 |

## 1. 解决的问题

### 1.1 核心问题
在每个阶段边界验证产物存在、Q-id 被所有下游产物引用、`PROBLEM_HASH` 未被改动；**只验结构/verdict，不评质量**。

### 1.2 具体场景 / 为什么需要
- `Act as a structural verifier` —— 不做语义打分，避免与审计门职责重叠。
- INV-G1 内容哈希专防「Q-id 没变但题目被悄悄改写」。

### 1.3 不做的后果
- 改题漂移：前面锁的问题，后面写成另一个，最终答非所问。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `AgentDoc` | `DISCIPLINE_CONTEXT`（general） | 配置 | 必须 |
| `FinalProposal` | `Q-id / 问题段` | Phase 2 | 必须 |
| `ProblemHash` | `SHA256` | Phase 0 | 必须 |
| `LeakageAudit` | `verdict` | Phase 7 | 可选 |
| `Orchestrator` | `phase_boundary` | 编排器 | 必须 |
| `Artifact` | `Q-id` | 各阶段 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `assurance-contract.md`、`output-protocol.md` | 6 态/产物协议 |
| 角色指令 | `Act as a structural verifier` | 只验结构 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/FINAL_PROPOSAL.md` | Q-id / 问题段 |
| `refine-logs/PROBLEM_HASH.txt` | 比对 |
| 当前 working artifact | 查 Q-id |
| `.sciforge/verdicts/LEAKAGE_AUDIT.json` | PASS / WARN |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `InvariantCheck` | `overall_verdict / checks[].verdict / detail / evidence` |
| `InvariantCheck` | `phase_boundary / discipline_context` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/verdicts/INVARIANT_CHECK.json` | `overall_verdict / checks` | 机读 |
| `.sciforge/audits/INVARIANT_CHECK.md` | verdict / detail / evidence | 摘要 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `overall_verdict` | orchestrator | 放行 / halt |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| INV-G1 | skill 内 | 四边界检查 | — | 缺件 BLOCKED；Q-id 错/hash mismatch FAIL（`problem_content_rewritten`） |
| verdict 传播 | skill 内 | FAIL/BLOCKED/ERROR → halt；PASS/WARN/NOT_APPLICABLE → proceed | — | FAIL → KILL 回 Phase 2 |
| 结构校验 | `validate_verdicts.py` | 6 态词表 | — | 非法 verdict ERROR |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 1 与各 phase 产物 | `/invariant-check`（四个边界） | orchestrator 放行 / halt |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `ProblemAnchor.text_hash` | `Paper.problem_anchor`（B 类） | 否 |
| 四边界校验 | `paperapp/gates.py` | 否 |
| `overall_verdict` 取最差值 | `VERDICT_STATES` 已有 | 否 |
