# adversarial-falsification · Phase 2.5 强制先杀后证

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/adversarial-falsification/SKILL.md`（258 行）
> 类型：support · Phase 2.5（MUST，永不跳过） · 判定：skill 内阈值，无专用脚本。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白 + 阶段4 反驳预演 |
| **SciForge 26 节点** | `2.5` |
| **输入节点（对齐）** | `ResearchGap`(task-w)；`FailureMode`；`Assumption` |
| **输出节点（对齐）** | `ReviewPoint`(task-w)；`IdeaNode.falsifiable_claim` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 task-w 节点 `FalsificationRecord`（attempted[]/outcome/assumption_health）；`ReviewPoint` 面向论文反驳，不面向想法证伪 |

## 1. 解决的问题

### 1.1 核心问题
对每个候选想法先做证伪压力测试，输出 `SURVIVE / WEAKENED / FALSIFIED`，阻止 fake trick 进入推导阶段。

### 1.2 具体场景 / 为什么需要
- `first try to kill the idea, then try to prove it`。
- `Search the literature specifically for evidence AGAINST the idea.` —— 默认怀疑而非默认确认。
- 领域失败模式与工程落地性共同决定假设健康度。

### 1.3 不做的后果
- 假设不健康但进入 Phase 6a，做完才发现结论不成立，浪费全部预算。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `IdeaCandidates` | `idea_id` | `IDEA_CANDIDATES.md` | 必须 |
| `DomainSignature` | `failure_mode_profile.common_failures` | Phase 1b | 可选 |
| `DomainFailureModes` | 目录 | `domain-failure-modes.md` | 必须 |
| `EngineeringGrounding` | EG 轴 | `engineering-grounding-contract.md` | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Workflow | `first try to kill the idea, then try to prove it` | 证伪优先 |
| 文献反证 | `Search the literature specifically for evidence AGAINST the idea.` | 找反证据 |
| 契约 | `assurance-contract.md` | 6 态 verdict |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/IDEA_CANDIDATES.md` | 候选 |
| `refine-logs/domain-signature.json` | 失败模式 |
| `shared-references/domain-failure-modes.md` | 失败模式目录 |
| `shared-references/engineering-grounding-contract.md` | EG 轴 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Verdict` | `idea_id / assumption_health / has_counterexample / evidence_balance / prior_probability / oss_feasible / overall_verdict` |
| `EngineeringGrounding` | `engineering_grounding_tier / avg / remaining_risk` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `refine-logs/ENGINEERING_GROUNDING.md` | `8-Dimension Scores / EG Average / OVERALL TIER` | EG 估计 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `SURVIVE / WEAKENED / FALSIFIED` verdict per idea | `/novelty-check`、`/method-registry` | 筛选依据 |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| phase2.5 | skill 内 | `health ≥6` 且无反例且证据支持 | — | SURVIVE |
| WEAKENED | skill 内 | `4–6` 或有反例 | — | L1，target=2，budget=3 → Phase 2 |
| FALSIFIED | skill 内 | `<4` 或证据矛盾 | — | 记入 failed_ideas |
| DATA_BLOCKED | skill 内 | data<50% / fatal gap | `50%` | 阻塞 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/idea-discovery` | Phase 2.5 → 2.5b Engineering Grounding | `/novelty-check`、`/method-registry` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `Verdict / FalsificationRecord` | `paperapp` 动态类 + `HumanHypothesis` 失败留痕 | 建议新增 `FalsificationRecord` |
| `assumption_health ≥6` | gate 阈值 | 否 |
