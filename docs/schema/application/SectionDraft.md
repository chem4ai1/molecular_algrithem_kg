# `SectionDraft` · 本次写作的章节实例（按 run 实例化）

> 层：**应用层** ｜ 生命周期：**task-w（写作态）** ｜ 图内实例：**0**

## 1. 定位

本次写作的章节实例（按 run 实例化）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `run_id` | must | 所属写作 run | — |
| `section` | must | 章节名 | — |
| `section_plan` | optional | 对应骨架 id | — |
| `claims` | optional | 该节要论证的点[] | — |
| `word_budget` | optional | 字数预算 | — |
| `status` | optional | pass/fail/unknown | — |
| `cited` | optional | 引用[] | — |
| `evidence` | optional | 逐字引文 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `INSTANCE_OF` | SectionPlan | 实例化的骨架 |
| `USES_EVIDENCE` | Evidence | 该节用到的证据 |
| `CONSULTED` | ConsultedPaper | 该节查过的论文 |
| `RETRIEVED` | RelatedPaper | 该节检索到哪些候选 |
| `ANCHORED_BY` | ProblemAnchor | 该节回引哪个冻结问题 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `DRAFTS` | Paper | 本次写作的章节实例 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 本次每节写什么；引用与证据挂载

## 6. 示例

```json
{
  "id": "draft:<run_id>:<slug>",
  "type": "SectionDraft",
  "run_id": "<run_id>",
  "section": "<section>",
  "section_plan": "...",
  "claims": "...",
  "word_budget": "...",
  "status": "..."
}
```
