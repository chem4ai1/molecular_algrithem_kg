# dynamic-sandbox · 隔离执行代码并返回结构化结果

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/dynamic-sandbox/SKILL.md`（152 行）
> 类型：meta-skill · 横切（6a / 6b / 6c） · 代码佐证：`scripts/security_scan.py`（exit 3 = BLOCKED）、`scripts/smoke_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `6a`/`6b`/`6c` |
| **输入节点（对齐）** | `ExperimentArm`(global)；`EnvSpec`(global) |
| **输出节点（对齐）** | `RunArtifact`(task-r)；`Evidence`(global) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-r 节点 `ExecutionSession`：`RunArtifact` 只有 path/sha，无法表达 `session_id + code_hash + traceback + status` 的执行三元组，且必须按 run 隔离 |

## 1. 解决的问题

### 1.1 核心问题
在隔离沙箱中执行 agent 编写的代码，返回**结构化、可复现**的计算结果（含代码哈希、session、traceback）。

### 1.2 具体场景 / 为什么需要
- 数值、符号、模拟验证必须可复核：`Parse the Computation Request / Return Structured Result`。
- `If the request is too vague ("explore this data"), ask the caller for a concrete computation plan.`
- 沙箱只负责执行；库不足时转 `/dynamic-tooling`。

### 1.3 不做的后果
- 无 traceback 或结构化输出 → 结果不可复核，失败不可归因。
- 无唯一 session/code hash → 无法证明数值来自哪段代码。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `ComputationRequest` | `Domain context` | 调用方 | 可选 |
| `ComputationRequest` | `Computation type` | 调用方 | 必须 |
| `ComputationRequest` | `Input data` | 调用方 | 可选 |
| `ComputationRequest` | `Expected output shape` | 调用方 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Parse the Computation Request | 请求过 vague 时要求 concrete computation plan | 防模糊输入 |
| Return Structured Result | 返回 status / session_id / code_hash / error | 结构化留痕 |
| 契约 | `shared-references/effort-contract.md`、`shared-references/output-manifest.md` | 深度与产物清单 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| verification script + parameters（未给固定路径） | 执行输入 |
| `sandbox/session_*/input.json` | 脚本读取数据 |
| `scripts/security_scan.py` | 执行前静态扫描 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `SandboxResult` | `status / session_id / output / artifacts / code_hash / execution_time_ms / error` |
| `Artifacts` | `artifacts/*.svg` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `sandbox/session_{timestamp}/code.py` | 可复现脚本 | 代码留痕 |
| `sandbox/session_{timestamp}/input.json` | 输入 | 复算 |
| `sandbox/session_{timestamp}/output.json` | 结构化结果 | 下游消费 |
| `sandbox/session_{timestamp}/artifacts/*.svg` | 矢量图 | 图形产物 |
| `sandbox/MANIFEST.json` | 注册信息 | 产物清单 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `status ∈ success\|error\|partial` + session/code_hash | `/experiment-execution`、`/theory-derivation` | 结果可追溯 |
| 失败 traceback + 3 fixes | 调用方 | 修错建议 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 执行门 | `subprocess.run(timeout={timeout}s)` | 超时 | `timeout=300` | 回 traceback |
| 校验门 | skill 内 | Expected shape：Matrix 2D / Scalar number / Plot 非空 SVG | — | validation fails → structured error |
| 重试门 | skill 内 | no silent retry | — | caller decides |
| 外部门 | `scripts/security_scan.py` | exit 3 | BLOCKED | dispatch refused |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/experiment-execution` 或 `/theory-derivation` 需跑脚本 | `/dynamic-sandbox` | `/dynamic-tooling`（库不足）或 `/theory-derivation`（先符号后数值） |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `session / code_hash / input / output` | `reprospec` 的 ClaimAnchor 三哈希同构 | 建议新增 `ExecutionSession / ComputationResult` |
| `Expected output shape` | `MINIBATCH_PROBE` 形状实测 | 否 |
