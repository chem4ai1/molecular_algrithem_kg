# ablation-planner · 5–6 个组件消融计划与 AblCritic 账本

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/ablation-planner/SKILL.md`（82 行）
> 类型：support · Phase 10 前 · 代码佐证：`scripts/s2_ablation_gate.py`、`kernel/sciforge/s2/ablation.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 章节规划（主结果） |
| **SciForge 26 节点** | `10` |
| **输入节点（对齐）** | `ExperimentArm`(kind=main/baseline)；`Contribution` |
| **输出节点（对齐）** | `ExperimentArm`(kind=ablation) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-r 节点 `AblationLedger`：`ExperimentArm` 只能表达单臂，缺 5–6 计划 / decision / current_best 单调账本 |

## 1. 解决的问题

### 1.1 核心问题
在 Phase 10 前生成 5–6 个「一次删一个组件」的消融计划，并用 AblCritic 逐条决策，形成单调的 `current_best` 账本。

### 1.2 具体场景 / 为什么需要
- 有实验但无 `ABLATION_LEDGER` ⇒ gate FAIL，claim 过不了 `/result-to-claim`。
- decision 必须等于 AblCritic 判定，禁止手填 GOOD。

### 1.3 不做的后果
- 消融组漏掉核心创新组件，增益归因不可信。
- 账本不单调 → `s2_ablation_gate` 拒绝进入 claim 阶段。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `MethodRegistry` | `components` | `methods/METHOD_REGISTRY.md` | 必须 |
| `Experiment` | `experiments/full.**.arm_results` | full 实验 | 必须 |
| Run | `problem_id / run_id` | 编排器 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Job | `Plan 5–6 ablations, one component each` | 组件枚举 |
| Execute | `Execute each plan on the full set under the same protocol/budget as the main arm.` | 同条件比较 |
| 契约 | `s2-protocol.md` §3 | S2 消融协议 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `methods/METHOD_REGISTRY.md` | 组件清单 |
| `experiments/full/**` | 臂结果 |
| `scripts/s2_ablation_gate.py` | 门 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `AblationLedger` | `schema_version / problem_id / metric` |
| `AblationPlan` | `id / component / hypothesis / metric` |
| `AblationResult` | `plan / prev_value / new_value / decision` |
| `AblationLedger` | `current_best`（可选） |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/ABLATION_LEDGER.json` | `schema_version / plans / results / current_best` | gate 账本 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无 | — | — |

## 4. 判定与门

| 门 | 脚本 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| `s2_ablation` | `scripts/s2_ablation_gate.py` | 有实验缺 ledger ⇒ FAIL | exit 2 | 阻断 |
| 计划数 | skill 内 | 5–6 | 环境变量 `SCIFORGE_ABLATION_MIN/MAX` | 不合规 FAIL |
| decision | AblCritic | 必须等于 critic 判定 | — | 手填 FAIL |
| 单调性 | skill 内 | `current_best` 单调 | — | 非单调 FAIL |
| 无实验 | gate | SKIP | exit 0 | — |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 9 → Phase 10 | `/ablation-planner` | `/result-to-claim` → `/paper-writing` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `AblationPlan / AblationLedger` | `paperapp` 动态类 + `AlgorithmModule.is_novel_component` 提供组件枚举 | 建议新增 `AblationRun` |
| `current_best 单调` | gate 判据 | 否 |
