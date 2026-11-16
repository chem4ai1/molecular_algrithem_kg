# `SectionPlan` · 章节计划（06）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

章节计划（06）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `section` | must | 章节名 | — |
| `claims` | optional | 该节要论证的点[] | — |
| `evidence_refs` | optional | 证据 id[] | — |
| `word_budget` | optional | 字数预算 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `CITES` | CitedPaper | 该节实际引用了哪篇 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `OUTLINES` | Paper | 论文的章节计划 |
| `INSTANCE_OF` | SectionDraft | 实例化的骨架 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 章节骨架；字数预算

## 6. 示例

```json
{
  "id": "sectionplan:<aid>:<slug>",
  "type": "SectionPlan",
  "section": "<section>",
  "claims": "...",
  "evidence_refs": "...",
  "word_budget": "..."
}
```
