# `ProblemCategory` · 问题类别（从 Paper.problem_category 聚类）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

问题类别（从 Paper.problem_category 聚类）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `code` | must | 类别编码 | — |
| `label` | must | 显示名 | — |
| `n_papers` | optional | 论文数 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `IN_CATEGORY` | ResearchQuestion | 问题所属类别 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 聚类同类问题；决定章节骨架

## 6. 示例

```json
{
  "id": "cat:<aid>:<slug>",
  "type": "ProblemCategory",
  "code": "<code>",
  "label": "<label>",
  "n_papers": "..."
}
```
