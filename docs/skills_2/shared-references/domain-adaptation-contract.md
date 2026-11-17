# domain-adaptation-contract · TDAL 单一权威 schema

> 源文件：`skills/shared-references/domain-adaptation-contract.md`（306 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条（阶段5 落点） |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `Evidence`；`GateVerdict` |
| **输出节点（对齐）** | `TDAL.joint` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议新增的 `TDAL`；joint=T×D×A×L 必须有独立节点而非属性 |

## 1. 解决的问题
### 1.1 核心问题
防止强维度掩盖零维度：`joint is their product`；`No single dimension may be silently inflated or dropped.`
### 1.2 为什么需要
TDAL 是跨阶段唯一置信 schema，多处重算会造成维度膨胀/丢失。
### 1.3 不做的后果
某维为 0 却因平均得到高分，弱主张被误判可发表。

## 2. 输入
### 2.1 输入知识节点
`tdal.schema_version / problem_id`；`T{sympy_derivation, logic_verification, falsification_resistance, theory_data_validation}`；`D{ouroboros_report, oss_data_check, theory_only_flag}`；`A{domain_learner, seed_paper_match}`；`L{supporting_ratio, non_contradicting_ratio, non_gap_ratio}`。
### 2.2 输入 prompt 模板 / 契约
`single authoritative schema`；`joint = T × D × A × L`。
### 2.3 输入产物
`result-to-claim`（producer）、`paper-writing`（consumer）、`auto-pipeline`、`ouroboros-integration`、`domain-signature-consumer`。

## 3. 输出
### 3.1 输出知识节点
`tdal.joint / verdict / weakest_dimension / missing_inputs`。
### 3.2 输出产物
`CLAIMS_FROM_RESULTS.md` 的 tdal JSON；`PIPELINE_STATUS.md` 的 verdict/reason_code。
### 3.3 传递片段
`no rounding, no clamping`；`NEVER inflate a dimension`。

## 4. 判定与门
| 判据 | 阈值 |
|---|---|
| STRONG | joint≥0.7 |
| MODERATE | 0.5–0.7 |
| WEAK | 0.3–0.5 |
| UNSUPPORTED | <0.3 |
| 任一维=0 | 至多 WEAK |
| missing_inputs | 至多 MODERATE |

## 5. 上下游
ouroboros / guide / pipeline / contribution / result-to-claim → 本契约 → paper-writing + orchestrator。

## 6. 映射
`src/capfactory/reprospec/scoring.py::finalize` 是本项目对应的联合置信实现点。
