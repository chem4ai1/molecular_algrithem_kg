# 论文抽取方案与 Prompt 重设计（基于语义层 v4.1）

> 代码：`capfactory/semantic/extraction/`（`contracts.py` / `prompts.py` /
> `validator.py` / `runner.py`）。旧链路 `sciforge/stage_extract.py` +
> `deepdive.py` 保留为 legacy。

## 1. 为什么必须重做：当前 prompt 与语义层大面积错配

语义层只有 6 类：`Paper / Algorithm / AlgorithmModule / CodeRepository /
CodeFunction / Benchmark`。把现有 4 个 `stage_extract.PROMPTS` 的输出逐字段对照：

| 现有 prompt | 输出字段 | 语义层是否要 | 问题 |
|---|---|---|---|
| `paper` | `research_questions[]`（数组，含 problem_category） | ❌ | 语义层是**两个字符串属性** `research_question` / `problem_category`，不建 ResearchQuestion 节点 |
| | `hypotheses[]` | ❌ | Hypothesis 是 reserved 类，语义层完全没有 |
| | `sections[]` | ❌ | Section 已删 |
| | `paper_type` | ❌ | 语义层用 `domain`（D0–D10），由 CSV 校准 |
| | — | — | **没抽** `why_hard` / `relation_hints` |
| `algorithm` | `steps[]{name,mechanism,formula_ref,tools,code_symbols}` | ⚠️ | 对应 AlgorithmModule，但**缺 `inputs`/`outputs`**；`formula_ref` 应改为片段 `formula` |
| | `invariant` | ❌ | 语义层没有 |
| | — | — | **没抽** `Algorithm.problems_solved/mechanism/why_it_works/applicable_to/limitations` |
| `benchmark_profile` | `input_object/output_object/sample_budget/threshold/evaluation_tool` | ❌ | 全是已删 DataContract 的旧字段 |
| | `baselines[]` | ❌ | 语义层 Benchmark 没有（属应用层/关系层） |
| | — | — | **没抽** `n_samples/scale/modality/research_object` |
| `benchmark_values` | `observations[]` | ❌ | **Observation 已删**，数值应直接落 `Benchmark.model_results[]` |

`deepdive.related_work` 输出 8 种科技树关系（HAS_LIMITATION/COMPARES_WITH/…），
这些节点在语义层也不存在——**科技树是应用层概念**，只在复现/生成论文任务时抽。

### 上一轮追加「语义层契约」的副作用

上轮我在 `stage_extract.run_stage` 末尾追加了 712 字符的契约块，但**没有改示例 JSON**：
prompt 前半要求模型输出 `{"research_questions":[...],"hypotheses":[...],"observations":[...]}`，
后半又说「禁止输出 Observation/Section/Hypothesis」。
两者互相矛盾，比不加更容易让模型输出错结构。
**正确做法不是追加约束，而是重写输出契约本身** —— 这就是本次重设计的核心。

## 2. 新方案：5 个小契约，字段 1:1 对应语义层

```
E0 规则/AST/元数据（无 LLM）
   Paper.title/arxiv_id/doi/year/venue ← 文件名 + papers.csv
   Paper.domain/domain_code ← papers.csv（LLM 判领域不准，实测 9/10 要修）
   Paper.flow_family ← PROPOSES_METHOD → Algorithm 反查
   Paper.keywords ← TF-IDF
   CodeRepository.* ← 原文 URL + 本地 LICENSE
   CodeFunction.* ← AST（name/purpose/comment/params/returns/func_type）
   Benchmark.model_results 主路径 ← table_extract 表格解析
   Benchmark.sota_by_metric ← leaderboard.compute_sota 派生
   全部关系（除 E5 两类）← 规则/AST
        ↓
E1 Paper 核心        LLM   research_question / problem_category / why_hard / relation_hints
E2 Algorithm+Module  LLM   name/task_type/problems_solved/mechanism/why_it_works/
                           applicable_to/limitations + modules[]{name,mechanism,
                           formula,inputs,outputs,code_symbols,tools}
E3 Benchmark 结构    LLM   name/input_form/output_form/n_samples/scale/modality/
                           research_object/metrics[]（禁止数值）
E4 数值兜底          LLM   只补表格之外的显式数值 → model_results[]（主路径是表格）
E5 模块→工具/公式    LLM   唯一允许的「关系类」LLM 用途
```

### 每个阶段的产出契约（`contracts.E_CONTRACTS`）

| 阶段 | 目标类 | 必填 | 可空 | 说明 |
|---|---|---|---|---|
| E1_paper | Paper | research_question, problem_category, why_hard | relation_hints, evidence | domain/flow_family 不让 LLM 判 |
| E2_algorithm | Algorithm + AlgorithmModule | name, mechanism | 其余 + modules | code_symbols 只能从 AST 清单选 |
| E3_benchmark | Benchmark 结构 | name, input_form, output_form | n_samples/scale/modality/research_object/metrics | 禁止输出观测值 |
| E4_values | Benchmark.model_results[] | model, metric, value | unit/benchmark/source/evidence | 表格为主，LLM 只兜底 |
| E5_relations | Module→Tool / →Formula | module, kind, target | evidence | 其余关系一律规则建 |

`contracts.NON_LLM` 明确列出「由非 LLM 手段填充」的字段，prompt 里会打印
「本阶段不由 LLM 抽」——**从契约层面防止重复抽和幻觉**。

## 3. Prompt 设计要点

1. **通用规则只一份**（`COMMON`）：纯 JSON、不确定留空、≤60 字/≤6 项、evidence 逐字 ≤120 字。
2. **每个模板只给一个目标**，输出 JSON 直接是语义层字段，不出现任何已删类名。
3. **封闭词表按动态标准注入**：见 `docs/VOCAB_INJECTION_STANDARD.md` ——
   每类只给 top20（>20 用向量/字符相似度筛），词表外输出 `other` +
   `proposed_new` 自动扩表；不再全量打印，也不再清空越界值。
4. **契约文本由 `class_snapshot()` 生成**，语义层改字段时 prompt 自动跟随，不用手改。
5. **模块/工具/公式关系**是唯一允许 LLM 建的关系（用户指定）；科技树、论文→算法等全归规则。
6. **输出小**：E1 约 2.3k 字符 prompt、输出 ≤6 字段，避免历史上「一次输出过大被截断」。

## 4. 校验与失败策略（`validator.py`）

| 机制 | 实现 |
|---|---|
| 辅助字段不阻断核心 | `relation_hints` 传成字符串 → 归一为 `{...,[]}`；**只有核心字段缺失才是 fatal**（沿用 paper_core 1/10→10/10 的教训） |
| 动态词表 | 越界 → `other` + 候选收集；出现 2 次自动扩表；`other:` 不算 fatal |
| 逐字 evidence | `evidence in 原文` 且 ≤140 字，否则清空记 warn |
| 数值合法性 | value 必须数字；metric 里出现 epoch/table/year/dropout/引用编号直接丢弃 |
| 代码符号真实 | `cross_check` 比对 AST 清单，假符号记 warn（E5 的 module 名同理） |
| 重试 | 3 次，第 2 次起追加 `retry_contract(stage)` 只要求必填字段 |
| 规则校准 | `papers.csv` 的 domain 覆盖 LLM 的 domain_code；flow_family 由关系反查 |
| 表格主路径 | `table_extract` 产 120 行，LLM 兜底结果追加在其后 |

## 5. 回填语义层的路径

```
run_extraction(aid, graph=semantic_graph)
  → storage_cf/sciforge/semantic_extraction/<aid>.json（各阶段归一结果 + 报告）
  → E1/E2/E3 写节点属性；E4 追加 Benchmark.model_results
  → E5 建 AlgorithmModule→Tool/Formula 关系（应用层任务时展开）
  → graph_source.rebuild() 重建应用层图
```

## 6. 与旧链路的关系

| | 旧 `stage_extract`/`deepdive` | 新 `semantic/extraction` |
|---|---|---|
| 目标 TBox | legacy 46 类 | 语义层 6 类 |
| 输出 | research_questions/hypotheses/sections/observations | 语义层字段 |
| 契约来源 | 手写字符串 | `semantic.tbox_v4.class_snapshot()` |
| 校验 | 分散在各模块 | 统一 `validator.py` |
| 科技树 | 主流程抽 | 只在应用层任务抽 |
| 状态 | 保留（pipeline/测试依赖） | 新入口，逐步切换 |

## 7. 验证结果（已于 2026-11-13 完成 10 篇真跑，见 `SEMANTIC_EXTRACTION_RUN_REPORT.md`）

**Mock 全链路**（注入 `chat_fn`，不消耗 LLM，验证编排/契约/校验/校准）：

```
E1_paper      ok  attempts=1  fields=6   research_question 有值
E2_algorithm  ok  attempts=1  1 算法 / 1 模块
E3_benchmark  ok  attempts=1  ZINC
E4_values     ok  attempts=1  表格主路径 120 行 + LLM 兜底 0 行
E5_relations  ok  attempts=1  片段编码 --tool--> RDKit
domain 校准 D1（papers.csv 覆盖 LLM）
cross_check 0（无假代码符号/假模块名）
```

**容错验证**：`relation_hints` 传字符串、`problem_category` 越界、
`evidence` 非逐字 → 全部被归一/清空并记 `warn:`，`fatal=[]`，核心字段保留。
这正是旧版 1/10 成功问题的正解。

**10 篇真跑已完成**：10/10 论文 ok、46/46 阶段 ok、0 重试、946.8s，
三张图已重建并同步前端。逐篇明细与问题见 `SEMANTIC_EXTRACTION_RUN_REPORT.md`。

## 8. 切换步骤（已执行 1–5）

1. ✅ 新增 `semantic/extraction/runner.py`（新入口），清缓存后真跑 10 篇；
2. ✅ 新增 `semantic/apply.py` 回填：E1/E2/E3 写属性、E4 追加 model_results、
      E6 建真谱系边、E5 只写 `application_hints.json`；
3. ✅ 重建语义层图 / 应用层图 / 关系索引，前端重启后读到新图；
4. ✅ 统计 ok 率 / warn 分布 / 逐字 evidence 通过率（报告 §1、§7）；
5. ✅ `stage_extract.semantic_contract()` 标 deprecated 并转发，`run_stage` 不再追加矛盾契约；
      4 个旧 prompt 保留为 legacy（pipeline 与测试依赖）。

## 9. 边界与风险

- ✅ `_slices()` 已改读 `blocks.jsonl` 按 kind 聚合（10 篇全部命中），
  paper 不足 3000 字时用原文前段回退，lineage 单独聚合。
- ✅ E4 已按 `(model, metric, value)` 归一去重（表格主路径 + LLM 兜底）。
- ✅ E5 的 Tool/Formula 只写 `application_hints.json`，语义层不建节点，
  节点化留给应用层任务（复现/生成论文时按任务构建）。
- `TASK_TYPES` 与 `FORM_VOCAB` 是封闭词表，新增取值必须同步改
  `algorithm_problem.TASK_TYPES` / `contracts.FORM_VOCAB`，否则全部被判越界。
- `contract_text()` 会随 `SEMANTIC_CLASSES` 自动变化；TBox 精简后要重跑本轮验证，
  确认 prompt 里没有重新引入已删类。

## 10. 一句话总结

旧 prompt 是给 46 类 legacy TBox 写的，语义层精简到 6 类后，
**继续在原 prompt 上追加约束只会制造矛盾**；正确做法是从
`class_snapshot()` 生成契约、让每个输出字段都能在语义层找到归属，
并把「能由规则/AST/表格得到」的字段从 LLM 契约里彻底拿掉。


## 11. 后续修订（2026-11-13 第二轮）

- 删除「禁止输出已删类」提示词（语义层已无这些类，纯噪声）；
- 新增 `vocab.py` 动态词表：top20 注入、`other`/`proposed_new` 扩表、
  单元测试隔离词表文件；详见 `docs/VOCAB_INJECTION_STANDARD.md`；
- 修复前端论文库：`docs/FRONTEND_PAPER_DIAGNOSIS.md` 记录了
  「unknown / 无卡片 / 属性 unknown」的四个根因与修复。
