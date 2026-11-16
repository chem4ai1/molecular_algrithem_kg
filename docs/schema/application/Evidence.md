# `Evidence` · 证据（从 Observation 溯源字段提升）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

证据（从 Observation 溯源字段提升）。

`used_in[]` 记录本次被哪句话使用；`char_span` 待补。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `quote` | must | 逐字引文 | — |
| `kind` | should | 类别 | — |
| `paper_id` | optional | 论文 id | — |
| `source` | optional | 出处 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `GROUNDED_IN` | CodeUnit | 证据来自代码哪处 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `SUPPORTED_BY` | LeaderboardEntry | 数值的证据 |
| `USES_EVIDENCE` | SectionDraft | 该节用到的证据 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 主张锚定；引用支撑

## 6. 示例

```json
{
  "id": "evidence:<aid>:<slug>",
  "type": "Evidence",
  "quote": "<quote>",
  "kind": "...",
  "paper_id": "...",
  "source": "..."
}
```
