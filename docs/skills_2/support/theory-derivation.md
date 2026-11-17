# theory-derivation · 冻结 Q-id + 假设 + 逐步 SymPy 验证的推导包

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/theory-derivation/SKILL.md`（308 行）
> 类型：support · Phase 6a（ROUTED） · 代码佐证：`scripts/arb_verify.py`（可选）、`schemas/PROOF_AUDIT.schema.json`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 章节规划（方法素材） |
| **SciForge 26 节点** | `6a` |
| **输入节点（对齐）** | `ResearchQuestion`；`Assumption` |
| **输出节点（对齐）** | `Evidence`(kind=derivation)；`Assumption` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `DerivationStep`(expr/verified/tool) 与 `ProofAudit`(verdict/steps)：推导链需逐步机器验证状态，`Evidence` 只记结果引文 |

## 1. 解决的问题

### 1.1 核心问题
构建诚实推导包：冻结 Q-id / 不变量对象 / 假设，并逐步用 SymPy 验证，产出 `PROOF_AUDIT.json`。

### 1.2 具体场景 / 为什么需要
- `coherence > elegance` —— 不伪造连贯推导；manual 步骤必须标 `[not machine-verified]`。
- 每个非平凡步都要机器验证，禁止 TODO / gap / hand-waved。
- Q-id 必须出现在文档头。

### 1.3 不做的后果
- 推导在第 3 步出错但看不出来；结论与前提脱钩（Type I 缺口）。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `ProblemAnchor` | `q_id` | Phase 0 | 必须 |
| `Assumption` | `statement` | 提案 | 必须 |
| `DerivationStep` | `sympy_expr` | 推导 | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `FINAL_PROPOSAL.md`、`assurance-contract.md`、`schemas/PROOF_AUDIT.schema.json` | 提案/审计/schema |
| 诚实纪律 | coherence > elegance；manual → `[not machine-verified]` | 禁止伪造 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/FINAL_PROPOSAL.md` | Q-id |
| `DERIVATION_PACKAGE.md` 或用户指定目标 | 推导目标 |
| 本地 theory notes | 材料 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `DerivationStep` | `sympy_expr / verified` |
| `StaticCheck` | `checks / n_pass / n_fail / status` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `src/derivations/{problem_id}/derivation.py` | — | 推导脚本 |
| `derivations/{problem_id}/premises.md` | — | 前提 |
| `derivations/{problem_id}/derivation_output.md` | — | 推导结果 |
| `derivations/{problem_id}/verification_report.md` | — | 验证报告 |
| `DERIVATION_PACKAGE.md` | — | 推导包 |
| `.sciforge/verdicts/PROOF_AUDIT.json` | `verdict / reason_code / details` | 审计 verdict |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（推导包由 `/logic-verification`、`/leakage-audit`、`/result-to-claim` 消费） | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| mode | skill 内 | `derive / verify / simplify` | — | — |
| engine | skill 内 | `sympy / manual` | — | manual 标注未机验 |
| 步数 | skill 内 | `max_steps` | `50` | 超限拒绝 |
| 容差 | skill 内 | `tolerance` | `1e-10` | — |
| 逐步验证 | skill 内 | 每非平凡步 SymPy-verified | — | 有 TODO/gap → FAIL |
| Q-id 头 | skill 内 | 必须存在 | — | BLOCKED |
| PROOF_AUDIT | skill 内 | COHERENT→PASS；near→WARN/FAIL；incoherent→FAIL/BLOCKED | — | — |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/idea-discovery`、`/method-registry` | Phase 6a `/theory-derivation` | `/dynamic-sandbox`、`/logic-verification`、`/leakage-audit`、`/result-to-claim` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `DerivationStep / StaticCheck` | `reprospec` 已有 `StaticCheck` 同构 | 否 |
| `sympy_expr / verified` | `PROOF_AUDIT → GateVerdict` | 否 |
| `max_steps=50, tolerance=1e-10` | gate 配置 | 否 |
