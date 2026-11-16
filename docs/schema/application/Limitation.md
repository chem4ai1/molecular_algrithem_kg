# `Limitation` · 局限（从 Algorithm.limitations 文本提升）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

局限（从 Algorithm.limitations 文本提升）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `statement` | must | 一句话陈述 | — |
| `algorithm` | must | 算法 id | — |
| `kind` | optional | 类别 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HAS_LIMITATION` | Algorithm | 算法的局限 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 限制章节素材

## 6. 示例

```json
{
  "id": "limitation:<aid>:<slug>",
  "type": "Limitation",
  "statement": "<statement>",
  "algorithm": "<algorithm>",
  "kind": "..."
}
```
