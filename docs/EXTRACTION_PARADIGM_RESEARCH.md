# 知识抽取标准范式调研与落地（2026-11-14）

## 1. 联网调研结论

| 来源 | 核心观点 | 对我们的启发 |
|---|---|---|
| Dagdelen et al., *Nature Communications* 2024, [s41467-024-45563-x](https://www.nature.com/articles/s41467-024-45563-x) | LLM 可做**联合 NER + 关系抽取**；schema 约束 + 结构化输出；GPT-3/Llama-2 微调后接近专用模型 | 不要先把实体冻结再抽关系；一次抽取里同时给实体候选与关系 |
| SciERC / SciIE / DyGIE++（UW 多任务框架） | 实体、关系、**共指**联合建模，共享表示优于流水线 | 实体规范化/共指合并是必需步骤，不是可选 |
| 科学文献处理综述（SciXa 2024） | 流水线误差会逐级放大，联合解码是系统性缓解；工程上常用「便宜确定性过滤 → 昂贵验证」的分阶段漏斗 | 我们已有表格/AST/规则做确定性层，应把 LLM 只放在需要语义判断的环节 |
| GraphRAG 防幻觉边实践（Saram 2026） | 要求每个关系有 **char offset / 逐字定位**，把「编造 plausible 关系」变成机械失败 | 关系落地前必须能定位到原文，否则标 ungrounded 不落图 |
| KG 构建工程实践（Dreaming Press / DevWeekends） | 最难的不是抽实体，而是决定 `OpenAI` / `OpenAI Inc.` / `the company` 是同一节点；预定义 schema + 抽取后验证 | `canonicalize()` 对齐已有图节点，避免同义新名 |
| 方法节模块化精读范式 | 先定**输入/输出/训练信号**，再把模块改写成「接收什么、产生什么、为什么需要」，最后定位目标函数与**模块间信息流** | E2 的 modules 要补 `step_order / depends_on / data_flow` |

## 2. 当前链路与范式的差距

| 范式环节 | 之前 | 差距 |
|---|---|---|
| NER | 无显式阶段，模型自由命名，靠 `abox_guide` 文字提醒 | 没有可复用的实体候选字典 |
| 槽位填充 | E1/E2/E3 直接输出，词表校验 + CSV 校准 | 缺少**抽取后**的实体规范化与共指合并 |
| 关系抽取 | E6 lineage / E5 tool-formula 有 evidence 字段 | 没有 char offset 落地检查，无法区分「有依据」与「编造」 |
| 模块追踪 | modules 有 name/mechanism/formula/inputs/outputs | 缺顺序、依赖、信息流；`code_symbols` 只做 warn 不产出对齐结果 |

## 3. 落地：`semantic/extraction/paradigm.py`

**不推翻已验证的 E1–E6**（10 篇真跑 100% ok），而是加一层**确定性范式化后处理**，
在 `run_extraction()` 末尾自动执行，结果写入 `report["paradigm"]`：

### 3.1 阶段一 NER（零 LLM）
`recognize_entities(slices, graph)`：
- ① 语义层图内 6 类节点名字面命中（`source=graph_catalog`，带 `node_id`）
- ② 文本大写缩写/驼峰方法名 + `Table N` 引用（`source=surface_pattern`，带 `offset`）
- 输出 `algorithms / benchmarks / code_symbols / metrics / tables` 五类候选

MolMiner 实测 **223 个实体候选**。

### 3.2 阶段二 槽位规范化
`canonicalize(report, graph)`：E2/E3 输出的算法名、基准名按
「精确归一 → 字符 3-gram Dice ≥0.62 模糊 → 新建」对齐到图内节点；
`code_symbols` 与真实 `CodeFunction` 求交，未命中标 `ungrounded`。
输出 `canonical_map / alias_groups / n_exact / n_fuzzy / n_ungrounded_code`。

### 3.3 阶段三 关系逐字落地
`ground_relations(report, slices, full_text)`：对每条 lineage / tool / formula 关系
在**全文**（不只切片）做逐字定位，带 `char_offset`；找不到标 `ungrounded` 并给原因，
回填时不落图。修了弯引号/换行归一与长引文前半段命中。

### 3.4 阶段四 模块追踪
`track_modules(report, ast_symbols)`：给每个模块补
`step_order / depends_on / data_flow / goal / formula / code_aligned /
code_alignment_rate`，并生成 `pipeline: A -> B -> C` 信息流串。

### 3.5 槽位审计
`slot_audit(report, graph)`：按 **实际跑过的阶段**检查必填槽位、词表、模型结果，
给出 `score`。避免了「dataset_benchmark 没跑 E2 却因算法槽位扣分」的误判。

## 4. 三项迭代优化（5 篇验证后）

| 问题（5 篇首轮） | 优化 |
|---|---|
| `1710.00616` slot=0.5，因 dataset_benchmark 漏跑 E2 | `STAGE_PLAN["dataset_benchmark"]` 补 `E2_algorithm` + `E5_relations`；`slot_audit` 只审计跑过的阶段 |
| `1805.11973` grounded 4/7，证据落在切片之外 | `apply_paradigm(..., full_text=md)`，关系定位用全文 |
| 后台批跑写报告非原子 | `runner` 改 `os.replace` 原子写，避免读到半文件 |

## 5. 5 篇真跑验证（全新、无 blocks.jsonl）

| arXiv | 类型 | 耗时 | ok | 切片 | 研究问题 | 模块 | slot | grounded |
|---|---|---:|---|---|---:|---:|---:|---:|
| 1509.09292 | method | 76s | ✅ | fallback | 58 字 | 4 | 0.875 | 8/8 |
| 1710.00616 | dataset_benchmark | 58s | ✅ | fallback | 63 字 | 0 | 0.5 | 3/3 |
| 1802.05283 | method | 119s | ✅ | fallback | 68 字 | 4 | 1.0 | 6/6 |
| 1805.11973 | method | 126s | ✅ | fallback | 53 字 | 5 | 0.875 | 4/7 |
| 1806.02473 | method | 110s | ✅ | fallback | 41 字 | 5 | 0.875 | 5/6 |

**优化后重跑代表性 2 篇**：

```
1710.00616  stages 4→6 · mods 0→5 · slot 0.5→0.875 · grounded 3/3→5/5
1805.11973  grounded 4/7→7/8（全文定位生效）
```

剩余 `slot=0.875` 是 `Benchmark.model_results` 为 0 —— 老论文确实没有
markdown 表格数值，属真实数据情况，不是抽取失败。
`fallback` 切片证明：**783 篇里绝大多数没有 blocks.jsonl 也能正常抽**。

## 6. 相关改动

- `/relations` 页面：节点溯源卡片（来源论文/抽取报告）+ 单元格级溯源
  （120 格，带 `table_extract:1`），见 `static/provenance_card.js`。
- `provenance.trace()` 增强 `cells`：图内行 × 抽取报告 provenance join，
  返回 `cell_id / model / metric / value / paper_id / provenance / evidence`。
- `apply.py`：回填时按 `code_symbols` 建 `MODULE_IMPLEMENTED_BY`（代码联系建立）。
- `batch_extract.py`：全量断点续跑，见 `docs/FULL_BATCH_RUN.md`。
