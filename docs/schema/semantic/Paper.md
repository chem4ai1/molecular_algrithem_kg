# `Paper` · 论文（客观实体）

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**808**

## 1. 定位

论文（客观实体）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `title` | must | 标题 | ✅ |
| `arxiv_id` | should | arXiv 标识 | ✅ |
| `doi` | optional | DOI | ❌ 0% |
| `year` | optional | 年份 | ✅ |
| `venue` | optional | 发表场所 | ❌ 0% |
| `research_question` | should | 研究什么问题（吸收 ResearchQuestion 节点） | ✅ |
| `problem_category` | should | 问题类别（吸收 ProblemCategory 节点） | ✅ |
| `domain` | should | 所属领域 | ✅ |
| `flow_family` | should | 算法族（和什么方向的方法比较） | ✅ |
| `why_hard` | optional | 现有方法瓶颈 | ✅ |
| `keywords` | optional | 关键词 | ✅ |
| `relation_hints` | optional | 关系线索 | ✅ |
| `paradigm` | should | 研究范式 formal/empirical/design/interpretive | ❌ 0% |
| `evidence_type` | should | 证据类型 causal_inference/derivational/experimental/simulational/correlational/interpretive | ❌ 0% |
| `evidence_norm` | optional | 该领域认可的指标与证据规范 | ❌ 0% |
| `figures` | optional | 图表清单[{label,caption,kind,for_contribution}] | ❌ 0% |
| `section_map` | optional | 章节→论断映射[{section,claims[]}] | ❌ 0% |
| `gaps` | optional | 论文指出的研究空白[{gap_type,statement,evidence}] | ❌ 0% |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `PROPOSES_METHOD` | Algorithm | 论文提出算法 |
| `HAS_CODE` | CodeRepository | 论文关联代码仓库 |
| `EVALUATED_ON` | Benchmark | 在哪个基准上评测 |
| `RELATED_TO` | Paper|Algorithm | 相关文献/方法 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `RELATED_TO` | Paper | 相关文献/方法 |

## 4. 抽取来源

- 一次抽取：`E1_paper`

## 5. 使用场景

- 复现锁定问题锚点；生成时决定范式与证据类型

## 6. 示例

```json
{
  "id": "paper:<aid>:<slug>",
  "type": "Paper",
  "title": "<title>",
  "arxiv_id": "...",
  "doi": "...",
  "year": "...",
  "venue": "...",
  "research_question": "..."
}
```
