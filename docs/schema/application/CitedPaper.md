# `CitedPaper` · 本次写作实际引用的论文（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**task-w（写作态）** ｜ 图内实例：**0**

## 1. 定位

本次写作实际引用的论文（按 run 实例化）。

任务级：`cited_in[]` 记录被哪几节引用；与 `SourcePaper`（全局科技树）不同。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `cite_key` | must | 引用键 | — |
| `title` | must | 标题 | — |
| `doi` | optional | DOI | — |
| `authors` | optional | 作者 | — |
| `year` | optional | 年份 | — |
| `venue` | optional | 发表场所 | — |
| `layers` | optional | 三层核验状态[3] | — |
| `existence` | optional | 存在性 unknown/yes/no | — |
| `metadata_ok` | optional | 元数据一致 | — |
| `context_ok` | optional | 上下文是否支撑 | — |
| `context_quote` | optional | 支撑句 | — |
| `cited_in` | optional | 被哪几节引用[] | — |
| `recency_ratio` | optional | 近两年占比 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CITES` | SectionPlan | 该节实际引用了哪篇 |
| `GAP_SUPPORTED_BY` | ResearchGap | 该空白由哪些文献支撑 |
| `LED_TO` | RelatedPaper | 该候选最终是否被引 |

## 4. 抽取来源

- 二次抽取：`R5_citation`

## 5. 使用场景

- 引用网络；三层核验

## 6. 示例

```json
{
  "id": "cited:<run_id>:<slug>",
  "type": "CitedPaper",
  "run_id": "<run_id>",
  "cite_key": "<cite_key>",
  "title": "<title>",
  "doi": "...",
  "authors": "...",
  "year": "..."
}
```
