# `EvidenceNorm` · 领域证据规范（02/03）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

领域证据规范（02/03）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `evidence_type` | must | 六类证据类型 | — |
| `accepted_metrics` | optional | 领域认可指标[] | — |
| `min_fidelity` | optional | 最低保真度 | — |
| `sample_size_norm` | optional | 样本量惯例 | — |
| `control_design_norm` | optional | 对照设计惯例 | — |
| `effect_reporting_norm` | optional | 效应报告惯例 | — |
| `negative_result_norm` | optional | 阴性结果惯例 | — |
| `exemplar_venues` | optional | 代表性 venues[] | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `APPLIES` | FailureMode | 该规范下适用的失败模式 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CONFORMS_TO` | Paper | 论文遵循的领域证据规范 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 指标对口校验；最低保真度

## 6. 示例

```json
{
  "id": "norm:<aid>:<slug>",
  "type": "EvidenceNorm",
  "evidence_type": "<evidence_type>",
  "accepted_metrics": "...",
  "min_fidelity": "...",
  "sample_size_norm": "...",
  "control_design_norm": "...",
  "effect_reporting_norm": "..."
}
```
