# background-dispatch-protocol · 长任务后台派发协议

> 源文件：`skills/shared-references/background-dispatch-protocol.md`（193 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `6c` |
| **输入节点（对齐）** | `ExperimentArm`；`EnvSpec` |
| **输出节点（对齐）** | `RunArtifact`(task-r) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议新增的 `ExperimentRun.dispatch_id`，不额外新增 |

## 1. 解决的问题
### 1.1 核心问题
把长任务（实验、编译、下载）派发后台，避免前端会话超时阻塞。
### 1.2 为什么需要
- `The agent must NEVER block the foreground on a task whose wall-clock time may exceed the tool's session timeout.`
- v2.2：下载失败永不 SKIP。
### 1.3 不做的后果
前台会话超时导致实验中断、结果丢失。

## 2. 输入
### 2.1 输入知识节点
`任务.预估时长`；`dispatch.方法`；`STATUS.json.status`；`checkpoint.ckpt_latest.pkl`；`download.STATUS.json`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；被 `experiment-execution/SKILL.md`、`paper-compile/SKILL.md`、`auto-pipeline/SKILL.md` 消费。
### 2.3 输入产物
实验命令、下载 URL、`scripts/detect_device.py` 结果。

## 3. 输出
### 3.1 输出知识节点
`dispatch` 阈值（>5min MUST；2–5min SHOULD；<2min 前台；下载 >2min 或 >100MB MUST）；`STATUS.json`；download registry。
### 3.2 输出产物
`DISPATCH.json`：`session_name / PID / log 路径 / monitor / kill`；`STATUS.json`：`running|completed|failed`；`experiments/.downloads.json`：`name/source/url/sha256/via_proxy/method`。
### 3.3 传递片段
无（协议被阶段 skill 消费）。

## 4. 判定与门
| 门 | 判据 | 失败去向 |
|---|---|---|
| 方法选择 | tmux → nohup → systemd → else | BLOCKED |
| 重试 | bounded 2 retries | 超限失败 |
| 网络失败 | 只降 WARN 不 SKIP | — |
| Phase10 | 读 `STATUS.json` | 未 completed 不得进 |

## 5. 上下游
experiment-execution / auto-pipeline / paper-compile → 本协议。

## 6. 映射
分子仿真/构象搜索 >5min 必须后台 + 写 STATUS.json，Phase 10 再收结果。
