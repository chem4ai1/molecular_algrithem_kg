# result-to-claim · 三档保真度 + TDAL + ClaimAnchor

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/result-to-claim/SKILL.md`（429 行）
> 类型：support · Phase 10（MUST） · 代码佐证：`scripts/tdal_compute.py`、`scripts/claim_anchor_gate.py`、`scripts/s2_ablation_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 定主张 → 阶段2 |
| **SciForge 26 节点** | `10` |
| **输入节点（对齐）** | `Evidence`；`ExperimentArm`；`Assumption`；`LeaderboardEntry` |
| **输出节点（对齐）** | `Contribution`(global)；`Evidence`(global) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `Claim`(statement/fidelity/outcome_class) 与 `ClaimAnchor`(code_sha/input_sha/output_sha)、`TDAL`(T/D/A/L/joint)；`Contribution` 缺保真度与哈希锚定 |

## 1. 解决的问题

### 1.1 核心问题
用三档 fidelity 门槛把推导/验证结果转成可写 claim，并输出 TDAL 联合置信与 ClaimAnchor。

### 1.2 具体场景 / 为什么需要
- `Be honest. Do not inflate claims beyond what the evidence supports.`
- 外部 reviewer 判定，host 只收证据路由；primary 至少 numerical。
- `proven` 需 symbolic、`supported` 需 numerical、`suggests` 只需 qualitative。

### 1.3 不做的后果
- 单点结果写成「显著提升」；primary  qualitative 也放行；措辞越级。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `DerivationStep` | `sympy_expr` | Phase 6a | 必须 |
| `Result` | `raw_stat` | Phase 6c | 必须 |
| `GateVerdict` | `state` | 各门 | 必须 |
| `EvidenceNormProfile` | `sample_size_norm` | Phase 1b | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| RESULT-TO-CLAIM EVALUATION (OSS — 3-fidelity ladder) | `Be honest. Do not inflate claims beyond what the evidence supports.` | 保真度纪律 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `derivations/{problem_id}/` | 推导 |
| `LOGIC_VERIFICATION.json` | 逻辑审计 |
| `FINAL_PROPOSAL.md` | primary outcomes |
| `docs/research_contract.md`（可选）、`findings.md`、`CLAIMS_FROM_RESULTS.md` | 契约与结果 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Claim` | `statement / polarity / fidelity` |
| `TDAL` | `joint / weakest_dimension` |
| `ClaimAnchor` | `resolved` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/CLAIMS_FROM_RESULTS.md` | `claim_supported / fidelity_level / evidence_sufficiency / parity_check / all_seeds_reported / full_grid_reported / tdal` | 主张报告 |
| `.sciforge/nodes/CLAIM_ANCHORS.json` | — | 锚点 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无（claim 由 `/paper-writing`、`/auto-review-loop` 消费） | — | — |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| primary fidelity | skill 内 | primary qualitative | → REJECT | 阻断写作 |
| no / partial | skill 内 | — | → BLOCK writing | 阻断 |
| symbolic-only | skill 内 | — | → partial | 降档 |
| UNSUPPORTED | skill 内 | — | → `BLOCKED: unsupported_claim_<weakest_dimension>` | 阻断 |
| sufficiency 失败 | skill 内 | — | → qualitative / `insufficient_evidence_as_finding` | 降档 |
| 阴性结果 | skill 内 | boundary / negative contribution | → `negative_result_as_contribution` | 改写 |
| claim 锚 | `claim_anchor_gate` | `resolved=true` / 哈希稳定 | — | FAIL |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/theory-derivation` + `/logic-verification` | Phase 10 `/result-to-claim` | `/paper-writing`、`/auto-review-loop` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `Claim / ClaimAnchor / TDAL` | `paperapp` 保留类 + `reprospec` 三哈希 | 否 |
| `fidelity_of()` 确定性计算 | `Benchmark.model_results[].fidelity` | 否（B 类） |
| `weakest_dimension 必报` | `DK-P3-14` | 否 |
