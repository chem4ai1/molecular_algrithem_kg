# `FailureMode` · 领域失败模式（07）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

领域失败模式（07）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 名称 | — |
| `severity` | must | fatal/high/medium/low | — |
| `detection` | optional | 检测方法 | — |
| `domain_tags` | optional | 适用领域[] | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `APPLIES` | EvidenceNorm | 该规范下适用的失败模式 |
| `CHECK_OF` | FailureCheck | 检查的是哪条失败模式 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 审稿预演自检清单

## 6. 示例

```json
{
  "id": "failure:<aid>:<slug>",
  "type": "FailureMode",
  "name": "<name>",
  "severity": "<severity>",
  "detection": "...",
  "domain_tags": "..."
}
```
