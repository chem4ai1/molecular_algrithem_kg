# leakage-audit · Type I 逻辑缺口与 Type IV 经验逃逸审计

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/leakage-audit/SKILL.md`（343 行）
> 类型：support · Phase 7（MUST） · 代码佐证：`scripts/leakage_scan.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `7` |
| **输入节点（对齐）** | `Assumption`；`FailureMode`；`Evidence`；`ExperimentArm` |
| **输出节点（对齐）** | `FailureCheck`(task-r) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-r 节点 `LeakageFinding`(type=I..IV/severity/path[])：`FailureCheck` 只有 status/note，无法分类四类泄露并连到证据路径 |

## 1. 解决的问题

### 1.1 核心问题
预注册后做结构泄漏审计，检查 Type I（结论不能从假设推出）与 Type IV（数值验证跑出假设成立 regime），给 `/paper-writing` 前置门。

### 1.2 具体场景 / 为什么需要
- `Does this implication follow from these assumptions?` —— 主张必须由前提支撑。
- OSS 无 benchmark，Type II / III 恒为 `NOT_APPLICABLE`（**我方有 benchmark，必须启用**）。
- Section 3 post-hoc 改动会击穿预注册。

### 1.3 不做的后果
- 「方法未测理论主张」被 desk reject；或数值跑在假设之外还宣称已验证。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `MethodRegistry` | `Section1-5` | Phase 5 | 必须 |
| `MethodBinding` | `current_method` | Phase 5 | 必须 |
| `LogicVerification` | `verdict` | Phase 8 | 可选 |
| `AgentDoc` | `DISCIPLINE_CONTEXT`（general） | 配置 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `assurance-contract.md`、`discipline-context.md` | 6 态/general |
| 审计问题 | `Does this implication follow from these assumptions?` | Type I 检查 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `methods/{METHOD_REGISTRY.md, METHOD_BINDING.md}` | 8 节链 / 方法 |
| `DERIVATION_PLAN.md` | 方法选择 |
| `results/`、`src/` | 实现 vs 声明 |
| `.sciforge/verdicts/LOGIC_VERIFICATION.json` | 交叉引用 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `LeakageAudit` | `verdict / type_i / type_ii / type_iii / type_iv` |
| `Callback` | `target / reason / iteration / max_iterations` |
| `LeakageAudit` | `blockers / recommendations` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/Type_I.md` | `CLEAN / WEAK / LEAKY` | 逻辑缺口 |
| `.sciforge/audits/Type_IV.md` | `CLOSED / ESCAPE / NO_VERIFICATION` | 经验逃逸 |
| `.sciforge/audits/LEAKAGE_AUDIT.md` | 汇总 | 人读 |
| `.sciforge/verdicts/LEAKAGE_AUDIT.json` | verdict | 机读 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（verdict 由 orchestrator 读） | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| G1 | skill 内 | Type I LEAKY on primary | → FAIL | 回调 `/method-registry` |
| G2 | skill 内 | Type IV ESCAPE | → FAIL | 同上 |
| G3 | skill 内 | 缺 `METHOD_REGISTRY.md` | → BLOCKED | — |
| G4 | skill 内 | Section3 post-hoc | → FAIL | — |
| 写作门 | skill 内 | FAIL | — | 阻 `/paper-writing`；WARN → Discussion caveat |
| 停滞门 | skill 内 | 3 轮同 gap | `3` | DRAFT + `LOGIC_GAP_FUNDAMENTAL_ISSUE` + halt |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/method-registry` | Phase 7 `/leakage-audit` | `/result-to-claim`、`/auto-review-loop`、`/paper-writing`、`/invariant-check`；FAIL 回调 Phase 5 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `LeakageFinding(type=I..IV)` | `paperapp` gate 产物 | 建议新增 `LeakageFinding` |
| Type II / III 在我方**必须启用** | `AlgorithmModule.assumptions` + `Benchmark.metrics[].contribution_link` | 否（B 类） |
| Type IV | `Benchmark.research_object / modality` | 否（B 类） |
