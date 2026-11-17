# quality-gate · 写作前最后硬门（停滞 + 质量底线 + 反自欺）

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/quality-gate/SKILL.md`（344 行）
> 类型：support · Phase 12 前置 · 代码佐证：`AGENT_DOC.md` 的 `QUALITY_GATE / RETRY_COUNTERS / MAX_RETRIES`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `12` 前置 |
| **输入节点（对齐）** | `GateVerdict`；`FailureCheck`；`Evidence` |
| **输出节点（对齐）** | `FailureCheck`(task-r)；`GateVerdict` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用 `GateVerdict` + `notes` 保留 QF/SD 结果；若需按检查组查询再加 `CheckGroup` 属性，不新增类 |

## 1. 解决的问题

### 1.1 核心问题
写作前做最后一道硬门：停滞检测、质量底线（QF-G1~G9）与反自欺（SD-G1~G5），FAIL 阻断 `/paper-writing`。

### 1.2 具体场景 / 为什么需要
- Type D（确定性）先判，Type S（语义）后判；语义判断必须引用证据位置。
- 同一 `blocked_by` 超过 `MAX_RETRIES` → `STAGNATED`，不无限重试。
- agent 对自身工作的评价是最不可靠的信号。

### 1.3 不做的后果
- 多轮失败仍静默通过；带未解质量问题的稿子进入写作。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Claim` | `fidelity` | Phase 10 | 必须 |
| `GateVerdict` | `state` | 各门 | 必须 |
| `ProblemAnchor` | `q_id` | Phase 0 | 必须 |
| `MethodLock` | `spec_hash` | Phase 5 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `AGENT_DOC.md` 的 `QUALITY_GATE / RETRY_COUNTERS / MAX_RETRIES` | 配置化阈值 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `AGENT_DOC.md` | 门配置 |
| `derivation_output.md` | 推导 |
| `LOGIC_VERIFICATION.json + LEAKAGE_AUDIT.json` | 审计 |
| `CLAIMS_FROM_RESULTS.md`、`FINAL_PROPOSAL.md` | claim / 锚 |
| `REGISTRY_HASH.txt / METHOD_REGISTRY.md` | 锁 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `GateVerdict` | `state / evidence` |
| `LoopBack` | `trigger`（可选） |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/STAGNATION_REPORT.md` | 停滞报告 | 升级 |
| `.sciforge/audits/QUALITY_FLOOR_REPORT.md` | `QF-G1~G9` | 质量底线 |
| `.sciforge/audits/SELF_DECEPTION_REPORT.md` | `SD-G1~G5` | 反自欺 |
| `.sciforge/audits/FINAL_VERDICT.md` | stagnation / quality_floor / self_deception / overall | 汇总 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `overall` verdict | orchestrator → `/paper-writing` | 放行或阻断 |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 停滞 | `RETRY_COUNTERS` | retry>max → STAGNATED FAIL；=max → WARN | — | 阻断 |
| QF-G1~G7 | skill 内 | 任一 FAIL | → BLOCKED | 阻断 |
| QF-G8/G9 | skill 内 | WARN | — | 可继续 |
| SD-G1~G5 | skill 内 | 任一 FAIL | → FAIL | 阻断 |
| overall | skill 内 | BLOCKED / FAIL / PASS / WARN | — | — |
| 关闭门 | 配置 | `enabled=false` | → NOT_APPLICABLE | — |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| 各 verdict + `/result-to-claim` | `/quality-gate` | `/paper-writing` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `GateVerdict.evidence` 必填 | `paperapp/gates.py` Type S 门 | 否 |
| QF / SD 检查组 | `Gate.script / exit_code_map / threshold` | 否 |
| 停滞检测 | `RUN_BUDGET.retry_counters`（`DK-P2-18`） | 否 |
