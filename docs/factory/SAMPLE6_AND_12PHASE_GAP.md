# 6 篇小样本结果：模板修正后与 12 阶段流程的差距

## 1. 修了什么

| 问题 | 旧模板 | 新模板 |
|---|---|---|
| `research_question` 过短 | 「一句话研究问题」 | 「1–2 句完整研究问题（40–90 字），必须包含研究对象/目标、方法或干预、关键矛盾或限制；不要只写短标题」 |
| `arch_modules` 粒度太粗 | 只写「系统级模块名」 | 明确规则：「列出方法节明确出现的每个系统级组件，不要合并为一个框架名；reasoning LLM 与 code LLM 必须拆成两项；只有原文没有分模块时才输出一个端到端模型名」 |

配置检查：

```
config errors []
E1 包含 40-90字要求 True
E2 包含 不要合并为一个框架名 True
```

## 2. 6 篇小样本结果

范围：4 篇原分子/符号论文 + 2 篇 data3 图/本体论文；只跑 E1+E2。

| 论文 | 流派 | ok | rq 长度 | limits | old_forms | arch_modules | key_challenge |
|---|---|---:|---:|---:|---:|---:|---:|
| MECo `2510.14455` | edit_sequence | ✅ | 86 | 3 | 1 | 2 | 60 |
| SynFlowNet `2405.01155` | gflownet | ✅ | 59 | 3 | 3 | 3 | 39 |
| AgentDrug `2410.13147` | llm_agent | ✅ | 68 | 2 | 2 | 3 | 63 |
| SHACL `1911.00598` | rule_symbolic | ✅ | 75 | 2 | 2 | 2 | 127 |
| AutoSchemaKG `2505.23628` | data3_graph | ✅ | 59 | 1 | 1 | 2 | 57 |
| OntoLearner `2607.01977` | data3_ontology | ✅ | 53 | 4 | 4 | 4 | 160 |

### MECo 关键改善（对比上一轮 A/B）

| 字段 | 上轮 A/B | 本轮修正后 |
|---|---:|---:|
| `research_question` | 31 字 | **86 字** |
| `arch_modules` | 1 个「MECo Framework」 | **2 个：Reasoning LLM + Code LLM** |
| `key_challenge` | 42 字 | 60 字 |

修正后的 MECo 结果：

```
research_q: 针对LLM在SMILES表示下执行分子编辑时因模态不匹配导致的忠实度低问题，
            提出MECo框架，通过生成可执行代码将编辑意图转化为精确结构修改，
            以实现可控且可解释的分子设计。

arch_modules:
  - Reasoning LLM: 生成高层级编辑意图和理由
  - Code LLM: 将编辑意图转化为可执行代码并执行结构修改
```

这正是 MECo 3.1–3.2 的核心内容。

### data3 两篇验证

- AutoSchemaKG：抽出 Input Processing / LLM Prompts 两个模块，抓住「无预定义 schema + 动态归纳」。
- OntoLearner：抽出 4 个模块（Ontology Access Interface / Modular OL Library / AI-LLM Integration / Benchmarking Platform），粒度合理。

说明修正后的模板对图/本体方向论文也有效。

## 3. 现在可以进入全量吗？

**比上一轮更接近，但还不建议立即全量。**

小样本说明：
- E1/E2 模板稳定
- 两类新方向（图/本体）也能抽
- 6/6 ok=True

但全量前还差两个小步骤：
1. 把这 6 篇报告**应用回主图**，跑 readiness，确认 P0/P1/P7 是否 READY；
2. 把 data3 的代码节点抽取从 5 篇小样本扩展到 31 篇，并与这些论文的 Algorithm 对齐。

之后可以全量跑。

## 4. 与真实 12 阶段论文生成流程的差距

| 阶段 | 小样本后状态 | 仍缺什么 |
|---|---|---|
| **P0 问题形式化** | E1 已能稳定抽 `research_question`/`why_hard`/`method_limits`/`old_forms`；MECo 有公式规则 | 仍无 `ProblemFormulation` 节点持久化；门控「旧法至少 1 条缺陷」尚未独立 validator；52 篇主图未全量更新 |
| **P1 技术路线** | E2 `arch_modules`/`key_challenge`/`why_not_other` 改善明显；6 篇均拆出模块 | 仍无 `TechnicalRoute` 节点；无架构图绘制；`why_not_other` 门控未按流派分化 |
| **P2 数据构造** | `data_sources`/`dedup_rule`/`result_tables`/`hyperparams` 规则已做；RDKit 去泄漏能跑 | 无 `DatasetSpec` 节点持久化；无真实数据文件/划分；split 覆盖低；去泄漏未接入阶段门 |
| **P3 代码实现** | data3 代码 AST 抽取小样本已跑（4 仓库/204 CodeFunction） | 未全量；`CodeFunction → AlgorithmModule` 未对齐；无 smoke test；非 Python 仓库未解析 |
| **P4 训练调试** | 只有 schema | 无 TrainingRun 数据、超参实跑、loss 曲线、收敛门 |
| **P5 Baseline 复现** | 有 `baseline_candidates` 启发式和 schema | 无 BaselineResult 节点；无同数据/同划分/同指标自动检查；无 baseline 执行 |
| **P6 主实验** | 有 18 张 LaTeX 表可生成；ResultTable  miner 可派生 90 个 | 表来自参考论文，不是自己实验；无 seeds/significance；主图未落 MainResultTable |
| **P7 消融分析** | `hyperparams` 可抽；schema 有 AblationTable/CaseStudy | 无消融执行、case study 生成、可视化；readiness 仍缺 |
| **P8 图表制作** | FigurePlan schema + 绘图脚本 + demo PDF | 没从论文可靠抽图；生成图未绑 claim；无 architecture/main/case 图自动生成 |
| **P9 论文写作** | SectionPlan miner 可派生；有模板骨架 | 无 SectionDraft 成文生成；venue 仍不足；claim-evidence 写作门未实现 |
| **P10 引用核验** | 有 citation 解析模块 | 无 CitationVerification 节点；references 抽取低；未接 DBLP/S2；三层核验未落图 |
| **P11 复现包** | ReproductionPackage schema + deliver 门控 | 无真实 code/data/env/script 打包；verification 只是字段检查，不是执行验证 |

## 5. 结论

这轮修正主要提升的是 **P0/P1 的抽取质量**，并对 data3 图/本体方向验证了模板泛化能力。

但对 12 阶段全流程来说，当前状态仍是：

```
语义抽取：接近可用
B 类聚合：部分可用、分散
C 类决策：demo 可用，不是全流程
代码节点：小样本可用，未全量/未对齐
P3–P7 执行层：基本缺失
P8–P11 产物层：脚本和 schema 有，真实闭环缺
```

下一步建议：

1. 应用这 6 篇报告到主图，跑 readiness；
2. 全量抽 data3 31 篇论文 + 代码节点；
3. 合并 B 类图谱；
4. 再全量跑原 52 篇；
5. 建立 12 阶段 orchestrator 与 gate validator。
