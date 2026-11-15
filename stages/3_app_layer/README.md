# 阶段 3 · 应用层（任务驱动）

**抽取期不产生应用节点**；只有显式跑复现/生成任务时才按 TaskSpec 构建。

| 任务 | 应用类 | 产物 |
|---|---|---|
| reproduction | LeaderboardEntry / MetricDefinition / DataContract / Evidence / Limitation / SourcePaper (+ 运行时 RubricNode 等) | `storage/sciforge/app_reproduction.json` |
| generation | ResearchQuestion / ProblemCategory / 其余共享 5 类 | `storage/sciforge/app_generation.json` |

| 职责 | 文件 |
|---|---|
| 任务规格 `TASK_SPECS` | `src/capfactory/applayer/tasks.py` |
| 唯一构建入口 | `builder.py` |
| 挖掘器（8 个） | `miner.py` |
| 应用层 TBox | `tbox.py` |

```bash
python stages/3_app_layer/build_task.py reproduction
python stages/3_app_layer/build_task.py generation
python stages/3_app_layer/build_task.py status
```
