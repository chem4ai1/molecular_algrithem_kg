# repro/ — 代码复现框架

参考 `SciForge-OSS-master` 的 phasegraph / gates / events 机制，
从当前图谱（属性 + 关系链）装配复现计划。设计见 `docs/REPRODUCTION_FRAMEWORK.md`。

| 文件 | 职责 |
|---|---|
| `phasegraph.json` | R0–R6 七阶段 DAG（produces / gate / next / loopback / effort_limits） |
| `contract.py` | `ReproPlan / RunState / GateResult` |
| `planner.py` | `build_plan(graph, paper_id)`：纯装配，缺什么记 `gaps` |
| `gates.py` | 7 个门 + `GATES` 映射，verdict 三档 |
| `state.py` | `EventLog`（events.ndjson 为 durable truth）/ `replay()` / 原子写快照 |
| `runner.py` | `run_repro()` / `resume_repro()` |

`dry` 模式不执行训练（R6 诚实 BLOCKED）；`lite/full` 需接真实执行器。
`core.py` 导出 `plan_repro / run_repro / resume_repro`。
