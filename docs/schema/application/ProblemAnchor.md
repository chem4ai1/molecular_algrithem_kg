# `ProblemAnchor` · 本次生成任务冻结的问题锚点（INV-G1，全链回引）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

本次生成任务冻结的问题锚点（INV-G1，全链回引）。

问题文本改一个字，content_hash 就变并记 redirected_from；同一 run 重复冻结返回同一节点。与 global 的 ResearchQuestion 不同：后者是「论文问了什么」，前者是「本次要解什么」。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `qid` | must |  | — |
| `question` | must |  | — |
| `content_hash` | must |  | — |
| `frozen_at` | optional |  | — |
| `source_span` | optional |  | — |
| `status` | optional | pass/fail/unknown | — |
| `redirected_from` | optional |  | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HINTS` | DomainHint | 该签名针对哪个问题 |
| `ANCHORED_BY` | SectionDraft | 该节回引哪个冻结问题 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 阶段01 冻结的 Q-id，下游每个任务节点都要回引（INV-G1）

## 6. 示例

```json
{
  "id": "problemanchor:<aid>:<slug>",
  "type": "ProblemAnchor",
  "run_id": "<run_id>",
  "qid": "<qid>",
  "question": "<question>",
  "content_hash": "<content_hash>",
  "frozen_at": "...",
  "source_span": "..."
}
```
