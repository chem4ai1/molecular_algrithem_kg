# `LeaderboardEntry` · 榜单行（从 Benchmark.model_results 展开）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

榜单行（从 Benchmark.model_results 展开）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `benchmark` | must | 基准名 | — |
| `model` | must | 模型名 | — |
| `metric` | must |  | — |
| `value` | must | 数值 | — |
| `unit` | optional | 单位 | — |
| `is_sota` | optional | 是否 SOTA | — |
| `paper_id` | optional | 论文 id | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `USES_METRIC` | MetricDefinition | 该行用哪个指标 |
| `SUPPORTED_BY` | Evidence | 数值的证据 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HAS_ENTRY` | Benchmark | 基准包含榜单行 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 措辞许可（fidelity）；主/次结果区分

## 6. 示例

```json
{
  "id": "entry:<aid>:<slug>",
  "type": "LeaderboardEntry",
  "benchmark": "<benchmark>",
  "model": "<model>",
  "metric": "<metric>",
  "value": "<value>",
  "unit": "...",
  "is_sota": "..."
}
```
