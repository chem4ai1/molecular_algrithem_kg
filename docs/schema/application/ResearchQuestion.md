# `ResearchQuestion` · 研究问题（从 Paper.research_question 提升为节点，便于聚类）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

研究问题（从 Paper.research_question 提升为节点，便于聚类）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `question` | must |  | — |
| `paper_id` | must | 论文 id | — |
| `problem_category` | optional |  | — |
| `keywords` | optional |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `IN_CATEGORY` | ProblemCategory | 问题所属类别 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `FORMULATES` | Paper | 论文提出研究问题 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- （待补）

## 6. 示例

```json
{
  "id": "researchquestion:<aid>:<slug>",
  "type": "ResearchQuestion",
  "question": "<question>",
  "paper_id": "<paper_id>",
  "problem_category": "...",
  "keywords": "..."
}
```
