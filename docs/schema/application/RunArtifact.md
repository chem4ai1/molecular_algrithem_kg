# `RunArtifact` · 运行产物（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

运行产物（按 run 实例化）。

任务级：只在本次执行后产生，带 `run_id`。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `kind` | must | 类别 | — |
| `path` | optional |  | — |
| `sha256` | optional |  | — |
| `produced_by` | optional |  | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `PRODUCES` | ExperimentArm | 实验组产出的产物 |
| `REPRODUCED_BY` | LeaderboardEntry | 数值由哪次运行产生 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 回答「这个数是怎么跑出来的」

## 6. 示例

```json
{
  "id": "runartifact:<aid>:<slug>",
  "type": "RunArtifact",
  "run_id": "<run_id>",
  "kind": "<kind>",
  "path": "...",
  "sha256": "...",
  "produced_by": "..."
}
```
