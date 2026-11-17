# experiment-execution · toy → full 两段实验与后台派发

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/experiment-execution/SKILL.md`（648 行）
> 类型：support · Phase 6b / 6c（MUST / ROUTED） · 代码佐证：`scripts/security_scan.py`、`scripts/detect_device.py`、`scripts/smoke_gate.py`、`scripts/s2_integrity_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `6b`/`6c` |
| **输入节点（对齐）** | `ExperimentArm`；`EnvSpec`；`DataContract` |
| **输出节点（对齐）** | `RunArtifact`；`LeaderboardEntry`；`Evidence` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `ExperimentRun`(dispatch_id/status/outputs_sha/budget_floor)：`ExperimentArm` 是计划，需区分「已派发并跑完」的运行实例 |

## 1. 解决的问题

### 1.1 核心问题
执行 toy 与 full 两段实验，完成代理/异步下载/设备检测/安全/完整/烟测门后后台派发全量实验。

### 1.2 具体场景 / 为什么需要
- `the toy experiment must validate the idea's core reasoning chain before any full-scale compute`。
- Step 5 固定顺序：`FIXED and top-to-bottom — Step 5.00 → 5.00b → 5.0 → 5.1 → 5.2`。
- 长任务不得阻塞前台；静态扫描与 1-step smoke 捕获晚发崩溃。

### 1.3 不做的后果
- 拿 toy 结果冒充 full，全文数值是假的；或前台会话超时导致实验中断。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `FinalProposal` | `core_claim` | Phase 2 | 必须 |
| `DomainSignature` | `verification_type / evidence_type / sample_size_norm` | Phase 1b | 必须 |
| `MethodRegistry` | `components` | Phase 5 | 必须 |
| `EvaluationProtocol` | `metrics / baselines` | 外部 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Job | `the toy experiment must validate the idea's core reasoning chain before any full-scale compute` | toy 前置 |
| Step 5 | `FIXED and top-to-bottom — Step 5.00 → 5.00b → 5.0 → 5.1 → 5.2` | 顺序不可乱 |
| 契约 | `background-dispatch-protocol.md`、`effort-contract.md`、`output-manifest.md` | 后台派发/深度/产物 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `refine-logs/FINAL_PROPOSAL.md` | 核心声明 |
| `refine-logs/domain-signature.json` | 协议模板 |
| `methods/METHOD_REGISTRY.md` | 最小实验矩阵 |
| `EVALUATION_PROTOCOL.json` | 公平协议 |
| `scripts/{security_scan,detect_device}.py` | 安全与设备 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Result` | `status / core_claim_validated / seeds_used / recommendation` |
| `FullExperimentDispatch` | `security_gate / integrity_gate / status_file` |
| `BudgetFloor` | `verdict / budget_floor.satisfied / completion_justification` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `experiments/toy/session_*/RESULT.json` | `status / result_summary` | toy 结果 |
| `experiments/full/FULL_EXPERIMENT_DISPATCH.json` | — | 派发凭证 |
| `experiments/full/{id}.SMOKE.json` | — | 烟测结果 |
| `.sciforge/verdicts/BUDGET_FLOOR.json` | — | 预算地板 |
| `methods/PRE_REGISTRATION.md` | — | 预注册 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `{verdict, toy_experiment, full_experiment, pipeline_continuation}` | orchestrator | 阶段推进依据 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| toy | skill 内 | `RESULT.status=PASS` | — | FAIL → PIVOT ≤2 / KILL |
| toy 重试 | skill 内 | INCONCLUSIVE / TIMEOUT / ERROR | 各 1 | 超限 BLOCKED |
| 安全门 | `scripts/security_scan.py` | exit 3 | BLOCKED | dispatch refused |
| 完整门 | `s2_integrity_gate` | D1 / D2 / D3 FAIL | → REFUSED | 拒派发 |
| 烟测门 | `smoke_gate` | 60s / 1-step / status row | — | 失败拒派发 |
| 预算门 | `BUDGET_FLOOR` | `satisfied=true` | — | IN_PROGRESS |
| 后台门 | `background-dispatch-protocol.md` | >15min / groups≥5 / data>1GB | — | 必须后台 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/verification-routing` | Phase 6b / 6c | `/leakage-audit`、`/logic-verification`、`/result-to-claim`；`/auto-review-loop` 可回退本 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `ExperimentRun / Dispatch` | `paperapp` 运行时 + `reprospec` 三哈希 | 建议新增 `ExperimentRun` |
| `DISPATCH.json + outputs_sha` | `DK-P2-12` 后台派发证据 | 否 |
| `budget_floor` | `RUN_BUDGET` | 否 |
