# `MetricDefinition` · 指标定义（从 Benchmark.metrics 去重归一）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

指标定义（从 Benchmark.metrics 去重归一）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 名称 | — |
| `direction` | should | min/max | — |
| `unit` | optional | 单位 | — |
| `n_benchmarks` | optional | 出现基准数 | — |
| `sota_model` | optional | SOTA 模型 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `COMPUTED_BY` | CodeSymbol | 指标由哪个函数算 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `USES_METRIC` | LeaderboardEntry | 该行用哪个指标 |
| `HAS_METRIC` | Benchmark | 基准使用指标 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 指标去重；contribution_link 对口

## 6. 示例

```json
{
  "id": "metric:<aid>:<slug>",
  "type": "MetricDefinition",
  "name": "<name>",
  "direction": "...",
  "unit": "...",
  "n_benchmarks": "...",
  "sota_model": "..."
}
```
