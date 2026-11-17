# `RelatedPaper` · 本次检索召回的候选论文（task-r，不等于最终引用）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

本次检索召回的候选论文（task-r，不等于最终引用）。

domain_hint 只是检索线索，不参与相似度、不推导 evidence_type；与 CitedPaper（最终引用）/ ConsultedPaper（查过未引）/ SourcePaper（全库科技树）四种角色互不替代。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `paper_id` | must | 论文 id | — |
| `query` | optional |  | — |
| `score` | optional |  | — |
| `bm25` | optional |  | — |
| `vector` | optional |  | — |
| `domain_hint` | optional |  | — |
| `rank` | optional |  | — |
| `decision` | optional |  | — |
| `retrieved_at` | optional |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `ABOUT` | Paper | 候选指向库内哪篇论文 |
| `LED_TO` | CitedPaper | 该候选最终是否被引 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `RETRIEVED` | SectionDraft | 该节检索到哪些候选 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 任务级检索候选：本次召回谁、排第几、最终引没引

## 6. 示例

```json
{
  "id": "relatedpaper:<aid>:<slug>",
  "type": "RelatedPaper",
  "run_id": "<run_id>",
  "paper_id": "<paper_id>",
  "query": "...",
  "score": "...",
  "bm25": "...",
  "vector": "..."
}
```
