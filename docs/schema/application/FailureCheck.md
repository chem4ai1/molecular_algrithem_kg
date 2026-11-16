# `FailureCheck` · 本次自检结果（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**task-r（读态）** ｜ 图内实例：**0**

## 1. 定位

本次自检结果（按 run 实例化）。

只记本次结论，不改 `FailureMode` 本体。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `status` | must | pass/fail/unknown | — |
| `note` | optional | 备注 | — |
| `checked_at` | optional | 检查时间 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `CHECK_OF` | FailureMode | 检查的是哪条失败模式 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CHECKED` | Paper | 本次失败模式自检 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 本次自检结论（能不能回应审稿人）

## 6. 示例

```json
{
  "id": "check:<run_id>:<slug>",
  "type": "FailureCheck",
  "run_id": "<run_id>",
  "status": "<status>",
  "note": "...",
  "checked_at": "..."
}
```
