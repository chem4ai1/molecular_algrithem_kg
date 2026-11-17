# ouroboros-integration · 自指改进循环（仅在明确要求时）

> 源文件：`skills/shared-references/ouroboros-integration.md`（186 行） · 类型：shared-reference（协议）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检（回环，默认关闭） |
| **SciForge 26 节点** | `14`/`16` |
| **输入节点（对齐）** | `Lesson`；`TDAL` |
| **输出节点（对齐）** | `TDAL.T/D/A/L` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议的 `TDAL`；自指报告不单独建类（默认关闭） |

## 1. 解决的问题
### 1.1 核心问题
让流程用自身输出反过来改进后续迭代，同时严格 opt-in 且防止自我膨胀。
### 1.2 为什么需要
`This is not enabled by default.`；`If the user says "just give me a paper", do NOT use this skill.`
### 1.3 不做的后果
未经请求的自指循环引入无限迭代与复杂度。

## 2. 输入
### 2.1 输入知识节点
`config.enable_ouroboros=true`；`mode.1-5`；`iteration.max=3`；`T{threshold=0.75}`；`A{active_domains}`；`L{consistency_min=0.6}`；`D{oss_data_check}`。
### 2.2 输入 prompt 模板 / 契约
`O U R O B O R O S E X T E N S I O N`；`The pipeline must keep flowing. Self-improvement never stalls the main path.`
### 2.3 输入产物
`domain-adaptation-contract.md` TDAL、`universal-retrieval/SKILL.md`、`adversarial-falsification/SKILL.md`、`auto-review-loop/SKILL.md`、`experience-replay-contract.md`。

## 3. 输出
### 3.1 输出知识节点
`OUROBOROS_REPORT.md`；`T_cont / D_cont / A_cont / L_cont`；`tier1 / tier2 / tier3`；`TDAL.T.sympy_derivation`。
### 3.2 输出产物
`refine-logs/OUROBOROS_REPORT.md`：`iteration / mode / changes / tests / TDL impact`。
### 3.3 传递片段
无。

## 4. 判定与门
max_iterations=3；mode1 每 iter ≥5 queries；mode2 每 claim 2 counterexamples；mode3 全 PASS 新 tier 方 active；mode4 SkillRegistry 必含 falsification；mode5 每 claim 3 claims 支持；必须 human check。

## 5. 上下游
显式 opt-in → 本协议 → retrieval / falsification / review；report → TDAL / literature / backend。

## 6. 映射
默认关闭；仅用户明确要求多轮自我改进时启用，且必须人工检查并接入 `experience-replay-contract.md`。
