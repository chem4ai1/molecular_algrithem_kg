# `SourcePaper` · 出处论文（从 Paper-RELATED_TO->Paper 科技树）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

出处论文（从 Paper-RELATED_TO->Paper 科技树）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `title` | must | 标题 | — |
| `ref_paper` | optional | 引用论文 id | — |
| `relation` | optional | 关系类型 | — |
| `resolved` | optional | 是否解析到库内 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `SITUATED_IN` | Paper | 论文在科技树中的位置 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 科技树出处；相关工作脉络

## 6. 示例

```json
{
  "id": "sourcepaper:<aid>:<slug>",
  "type": "SourcePaper",
  "title": "<title>",
  "ref_paper": "...",
  "relation": "...",
  "resolved": "..."
}
```
