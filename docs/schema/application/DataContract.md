# `DataContract` · 数据契约（从 Benchmark 输入输出/规模字段聚合）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

数据契约（从 Benchmark 输入输出/规模字段聚合）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `benchmark` | must | 基准名 | — |
| `input_form` | should | 输入形式 | — |
| `output_form` | should | 输出形式 | — |
| `n_samples` | optional | 样本量 | — |
| `scale` | optional | 规模档 | — |
| `modality` | optional | 数据模态 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HAS_CONTRACT` | Benchmark | 基准的数据契约 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 形状探针输入；数据契约核对

## 6. 示例

```json
{
  "id": "contract:<aid>:<slug>",
  "type": "DataContract",
  "benchmark": "<benchmark>",
  "input_form": "...",
  "output_form": "...",
  "n_samples": "...",
  "scale": "...",
  "modality": "..."
}
```
