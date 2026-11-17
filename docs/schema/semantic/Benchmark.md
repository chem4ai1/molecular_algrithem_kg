# `Benchmark` · 评测基准/数据集

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**607**

## 1. 定位

评测基准/数据集。

`table_extract:N` 与 md 的 `Table N` 不对应，回溯需靠三元组搜索。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 基准名 | ✅ |
| `input_form` | should | 输入数据形式 | ✅ |
| `output_form` | should | 输出数据形式 | ✅ |
| `n_samples` | should | 样本量 | ✅ |
| `scale` | optional | 规模档位 | ✅ |
| `modality` | optional | 数据模态 | ✅ |
| `research_object` | optional | 研究对象 | ✅ |
| `metrics` | should | 指标列表[{name,unit,direction,sota_model,sota_value}] | ✅ |
| `model_results` | should | 各模型结果[{model,metric,value,unit,is_sota}] | ✅ |
| `sota_by_metric` | optional | 动态 SOTA | ✅ |
| `is_evaluation` | should | 是否评测基准 | ✅ |
| `protocol` | optional | 实验协议{seeds,split,eval_script,epochs,hardware} | ✅ |
| `failure_modes` | optional | 适用本基准的失败模式 id[] | ❌ 0% |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `EVALUATED_ON` | Paper|Algorithm | 在哪个基准上评测 |

## 4. 抽取来源

- 一次抽取：`E3_benchmark`、`E4_values`

## 5. 使用场景

- protocol 决定证据门槛；数值行决定 fidelity

## 6. 示例

```json
{
  "id": "benchmark:<aid>:<slug>",
  "type": "Benchmark",
  "name": "<name>",
  "input_form": "...",
  "output_form": "...",
  "n_samples": "...",
  "scale": "...",
  "modality": "..."
}
```
