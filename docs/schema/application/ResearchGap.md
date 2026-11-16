# `ResearchGap` · 本次写作要填补的空白（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**task-w（写作态）** ｜ 图内实例：**0**

## 1. 定位

本次写作要填补的空白（按 run 实例化）。

任务级：只在本次写作选定后建；`mine_all` 不产出。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `gap_id` | must | 全局唯一 id | — |
| `gap_type` | must | capability/scale/data/theory/efficiency | — |
| `statement` | must | 一句话陈述 | — |
| `evidence` | optional | 逐字引文 | — |
| `priority` | optional | high/medium/low | — |
| `source_papers` | optional | 提炼来源论文 id[] | — |
| `selected_at` | optional | 选定时间 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `SEEKS_FROM` | Paper | 该空白从哪些论文的论述中提炼 |
| `GAP_SUPPORTED_BY` | CitedPaper | 该空白由哪些文献支撑 |
| `ANCHORS` | Contribution | 该空白锚定了哪条贡献 |

## 4. 抽取来源

- 二次抽取：`R6_gap`

## 5. 使用场景

- 生成时写 why-hard；检索时定位空白

## 6. 示例

```json
{
  "id": "gap:<run_id>:<slug>",
  "type": "ResearchGap",
  "run_id": "<run_id>",
  "gap_id": "<gap_id>",
  "gap_type": "<gap_type>",
  "statement": "<statement>",
  "evidence": "...",
  "priority": "..."
}
```
