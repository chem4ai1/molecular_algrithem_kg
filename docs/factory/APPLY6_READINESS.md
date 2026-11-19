# 6 篇完整报告应用回主图后的 readiness 结果

## 1. 做了什么

上一轮 `sample6_*.json` 只是摘要，不能用于 `apply_one()`。
本轮重新跑了 6 篇完整 E1+E2 报告，并应用到主图：

```text
输入主图: storage/sciforge/factory_knowledge_partial.json
备份:    storage/sciforge/factory_knowledge_partial_before_apply6.json
输出主图: storage/sciforge/factory_knowledge_main.json
同步更新: storage/sciforge/factory_knowledge_partial.json
完整报告: storage/sciforge/semantic_extraction/sample6_<aid>.json
```

6 篇全部 `ok=True`：

```text
APPLIED 2510.14455 MECo/edit_sequence
APPLIED 2405.01155 SynFlowNet/gflownet
APPLIED 2410.13147 AgentDrug/llm_agent
APPLIED 1911.00598 SHACL/rule_symbolic
APPLIED 2505.23628 AutoSchemaKG/data3_graph
APPLIED 2607.01977 OntoLearner/data3_ontology
```

主图变化：

```text
nodes:      391 → 405
assertions: 450 → 463
papers:     54（52 原论文 + 2 data3）
```

## 2. 用户关心的 P0/P1/P7：全部 READY

| 论文 | P0 | P1 | P7 |
|---|---|---|---|
| MECo `2510.14455` | READY | READY | READY |
| SynFlowNet `2405.01155` | READY | READY | READY |
| AgentDrug `2410.13147` | READY | READY | READY |
| SHACL `1911.00598` | READY | READY | READY |
| AutoSchemaKG `2505.23628` | READY | READY | READY |
| OntoLearner `2607.01977` | READY | READY | READY |

**结论**：模板修正后，6 篇样本的 P0 问题形式化、P1 技术路线、P7 消融所需字段都真正落图并可被 readiness 判定为 READY。

## 3. 全阶段逐篇结果

| 论文 | P0 | P1 | P2 | P6 | P7 |
|---|---|---|---|---|---|
| MECo | READY | READY | READY | READY | READY |
| SynFlowNet | READY | READY | READY | READY | READY |
| AgentDrug | READY | READY | PARTIAL | READY | READY |
| SHACL | READY | READY | PARTIAL | READY | READY |
| AutoSchemaKG | READY | READY | PARTIAL | **BLOCKED** | READY |
| OntoLearner | READY | READY | PARTIAL | **BLOCKED** | READY |

## 4. P2/P6 的具体问题

### P2 PARTIAL

| 论文 | 缺项 |
|---|---|
| AgentDrug | `dedup_rule \| split_spec` |
| SHACL | `data_sources`, `dedup_rule \| split_spec` |
| AutoSchemaKG | `data_sources`, `dedup_rule \| split_spec` |
| OntoLearner | `data_sources`, `dedup_rule \| split_spec` |

解释：
- AgentDrug 是 zero-shot 工作流，不造训练数据，合理缺 `dedup_rule/split_spec`，应判 NA。
- SHACL 是规则/符号系统，不是分子数据论文，缺 `data_sources` 合理，应判 NA。
- AutoSchemaKG/OntoLearner 的 data3 PDF 是分页文本，表格和数据源写法与 md 不同，当前规则没命中。需要补规则或从摘要/实验节二次抽取。

### P6 BLOCKED

| 论文 | 缺项 |
|---|---|
| AutoSchemaKG | `result_tables` |
| OntoLearner | `result_tables` |

原因：两篇 data3 PDF 转出的 md 是：

```text
# Page 1
...
# Page 2
...
```

不是 markdown 表格，`md_tables` 规则无法识别 PDF 文本中的表格。

**这不是 LLM 抽取失败，而是 PDF→md 转换格式不适配。**

## 5. 主图整体 readiness（54 篇）

```text
P0: READY  6/54   PARTIAL 48
P1: READY  6/54   PARTIAL 48
P2: READY 24/54   PARTIAL 30
P6: READY 48/54   BLOCKED 6
P7: READY  6/54   PARTIAL 48
```

说明：
- 6 篇新报告全部生效；
- 其余 48 篇仍是旧抽取，所以 P0/P1/P7 仍低；
- P6 BLOCKED 从 4 篇变成 6 篇，正是两篇 data3 缺 `result_tables` 导致。

## 6. 结论

本轮达到的目标：

> **P0/P1/P7 在 6 篇样本上真的 READY，不只是 schema 上存在。**

同时暴露出两个新问题：

1. data3 PDF→md 需要保留表格结构，否则 `result_tables` 抽不到；
2. readiness 需要 NA 判定，否则把“原文不需要这项”误判为 PARTIAL。

下一步在全量前应先修：
- `pdf_to_md` 表格保留；
- readiness 的 NA 规则；
- 再全量重跑 54 篇。
