# method-registry · 8 节方法注册表 + Section 3 hash lock + 人工审批

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/method-registry/SKILL.md`（417 行）
> 类型：support · Phase 5（MUST + 人工检查点） · 代码佐证：`scripts/validate_verdicts.py`（64-hex 或 `BLOCKED:<reason>`）。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 → 阶段2（预注册） |
| **SciForge 26 节点** | `5` |
| **输入节点（对齐）** | `ResearchGap`(task-w)；`IdeaNode`；`Assumption` |
| **输出节点（对齐）** | `Assumption`(global)；`ExperimentArm`(global) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 global 节点 `MethodLock`(registry_hash/section3_locked/experiment_matrix)：预注册是方法承诺，与 `Assumption` 不同；不进语义层 |

## 1. 解决的问题

### 1.1 核心问题
在推导之前建立 8 节 `METHOD_REGISTRY`，SHA256 锁住 Section 3，并要求人类审批，把「先看结果再选方法」变成可审计预注册。

### 1.2 具体场景 / 为什么需要
- `Section 3 is locked the moment the user approves the registry`；`The agent cannot self-approve.`
- 实验矩阵属于锁的一部分，缺项 → `BLOCKED: experiment_matrix_incomplete`。
- `REGISTRY_HASH.txt` 是 64 位 hex 或 `BLOCKED:<reason>`。

### 1.3 不做的后果
- 结果不好时微调方法，最后写的是「事后方法」；预注册形同虚设。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `FinalProposal` | `Q-id / ProblemAnchor` | Phase 2 | 必须 |
| `IdeaDag` | — | Phase 2 | 可选 |
| `AgentDoc` | `DISCIPLINE_CONTEXT`（general） | 配置 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `assurance-contract.md` | 6 态 verdict |
| 锁定指令 | `Section 3 is locked the moment the user approves the registry` | 人审后不可变 |
| 自审禁止 | `The agent cannot self-approve.` | 人类主权 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/FINAL_PROPOSAL.md` | Q-id / 锚点 |
| `refine-logs/IDEA_DAG.json` | 假设 / 方法 / 结果 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `MethodRegistry` | `ProblemQ-id / Frozen hash / Section3` |
| `RegistryHash` | `SHA256` 或 `BLOCKED:<reason>` |
| `ApprovalLog` | `action`（`INITIAL_APPROVAL` / `RE_APPROVAL`） |
| `MethodBinding` | `Status` |
| `OutcomeClassification` | `FidelityGate` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `methods/METHOD_REGISTRY.md` | 8 节 | 注册表 |
| `methods/REGISTRY_HASH.txt` | `SHA256(Section3)` | 锁凭证 |
| `methods/.sciforge/APPROVAL_LOG.txt` | `INITIAL_APPROVAL` | 人审留痕 |
| `methods/METHOD_BINDING.md` | Section3 verbatim | 锁定复述 |
| `methods/OUTCOME_CLASSIFICATION.md` | `PRIMARY / SECONDARY` | 主次分类 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| Section3 verbatim | `METHOD_BINDING` 及所有下游 | 逐字复述，防方法漂移 |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| SA-G1/G2/G3 | skill 内 | 注册表完整性 | — | — |
| LEAKY on primary | skill 内 | — | → BLOCKED | 回调 |
| 矩阵门 | skill 内 | 不全 | → `BLOCKED: experiment_matrix_incomplete` | 阻塞 |
| 审批门 | `APPROVAL_LOG.txt` | 无 `INITIAL_APPROVAL` | → DRAFT / 下游拒绝 | 阻塞 |
| hash 格式 | `validate_verdicts.py` | 64-hex 或 `BLOCKED:<reason>` | — | ERROR |
| 回调预算 | skill 内 | ≤3 轮 | `3` | BLOCKED |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/auto-pipeline` Phase 1 `/idea-discovery` | Phase 5 `/method-registry`（人工审批） | `/theory-derivation`、`/leakage-audit`、`/result-to-claim`、`/paper-writing`、`/invariant-check` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `MethodRegistry / RegistryHash` | `METHOD_LOCK.json` 现只有 `method_sau_hash`，需扩为段级 hash | 否 |
| `experiment_matrix` 入 hash | `Paper.experiment_matrix`（B 类，唯一应进指纹的扩展） | 否 |
| 人审不可代理 | `HumanDecision` + `ChoicePoint("5")` gate | 否 |
