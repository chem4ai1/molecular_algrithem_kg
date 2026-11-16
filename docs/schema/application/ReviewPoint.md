# `ReviewPoint` · 审稿关注点（09）

> 层：**应用层** ｜ 生命周期：**task-w（写作态）** ｜ 图内实例：**0**

## 1. 定位

审稿关注点（09）。

当前仍为每条贡献固定生成 6 条，待改为按需预演。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `axis` | must | 6 维之一 | — |
| `attack` | must | 最强反驳 | — |
| `response` | optional | 回应 | — |
| `severity` | optional | fatal/high/medium/low | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CHALLENGED_BY` | Contribution | 该贡献可能被如何质疑 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 最强反驳预演

## 6. 示例

```json
{
  "id": "review:<run_id>:<slug>",
  "type": "ReviewPoint",
  "axis": "<axis>",
  "attack": "<attack>",
  "response": "...",
  "severity": "..."
}
```
