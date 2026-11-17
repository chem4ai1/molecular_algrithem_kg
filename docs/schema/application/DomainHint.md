# `DomainHint` · 问题文本规则抽取的领域概率签名（provisional，不是 learned）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

问题文本规则抽取的领域概率签名（provisional，不是 learned）。

hint 永不作为最终签名（sole writer 是阶段02 learner）；confidence < 0.5 时下游应回落 general。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `domain_profile` | optional |  | — |
| `methodology_profile` | optional |  | — |
| `writing_profile` | optional |  | — |
| `failure_mode_profile` | optional |  | — |
| `data_profile` | optional |  | — |
| `confidence` | must |  | — |
| `origin` | must |  | — |
| `provisional` | must |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `HINTS` | ProblemAnchor | 该签名针对哪个问题 |
| `REFINED_BY` | EvidenceNorm | 阶段02 学习后的规范覆盖 hint |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 阶段01 的 provisional 概率签名；阶段02 learned profile 才可覆盖

## 6. 示例

```json
{
  "id": "domainhint:<aid>:<slug>",
  "type": "DomainHint",
  "run_id": "<run_id>",
  "domain_profile": "...",
  "methodology_profile": "...",
  "writing_profile": "...",
  "failure_mode_profile": "...",
  "data_profile": "..."
}
```
