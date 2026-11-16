# `ConsultedPaper` · 本次查过但未引的论文（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**task-r（读态）** ｜ 图内实例：**0**

## 1. 定位

本次查过但未引的论文（按 run 实例化）。

查过但未引；与 `CitedPaper` 的差别是「没有 CITES 边」。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `paper_id` | must | 论文 id | — |
| `reason` | optional | 为什么查但没引 | — |
| `used_in` | optional | 在哪用 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CONSULTED` | SectionDraft | 该节查过的论文 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 回答「为什么没引它」

## 6. 示例

```json
{
  "id": "consult:<run_id>:<slug>",
  "type": "ConsultedPaper",
  "run_id": "<run_id>",
  "paper_id": "<paper_id>",
  "reason": "...",
  "used_in": "..."
}
```
