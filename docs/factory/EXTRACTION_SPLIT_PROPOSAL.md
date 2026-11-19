# 抽取分段方案：回应「53 字段一次抽太多」的质疑

## 1. 先纠正我自己的错误

我上轮文档里举的「why_hard 300 字符 → 截断到 220」是**模拟脏数据**，不是实际发生的事。
实际全量 52 篇报告的检查结果：

| 字段 | 实测最大长度 | validator 上限 | 触及上限 |
|---|---:|---:|---:|
| `abstract` | 2000 | 2000 | **2 篇** ⚠️ |
| `why_hard` | 84 | 220 | 0 |
| `research_question` | 73 | 220 | 0 |
| `claims[].statement` | 66 | 80 | 0 |
| `gaps[].statement` | 71 | 80 | 0 |

**结论**：截断机制设计成防御性上限是对的，实际几乎没触发。
唯一要修的是 `abstract` 2000 上限太紧（2 篇卡住），建议提到 4000 或改为按段落边界截断。

**但你质疑的核心不是截断，而是"53 字段一次抽太多"——这个质疑成立。**

## 2. 现状：一次抽取的实际负载

```
E1_paper   : 30 字段, prompt 11,618 字符
E2_algorithm: 13 字段, prompt 10,287 字符
E3_benchmark: 10 字段, prompt  9,431 字符
────────────────────────────────────
合计       : 53 字段, 三次调用, 每次约 10K 字符
```

E1 一个阶段让 LLM 从 8000 字符正文里**同时**输出 30 个字段，其中混杂了：
- 核心问题（research_question/why_hard）
- 元数据（authors/abstract/references）
- 贡献主张（claims/gaps/delta_claims/open_problems/negative_results）
- 写作惯例（figures/section_map/citation_style/writing_style）
- 实验做法（data_sources/dedup_rule/hyperparams/result_tables/formal_def...）

**这些属于不同的认知任务**——让模型一次全做，质量必然打折。

## 3. 实测质量：哪些字段抽得好，哪些差

用 MECo 逐字段对比原文：

| 字段组 | 实际效果 | 判断 |
|---|---|---|
| 核心问题 | `research_question` 51 字精准概括 3.1；`why_hard` 53 字抓住 SMILES 线性化问题 | ✅ 好 |
| 方法机制 | `arch_modules` 3 个（Reasoning LLM + Code LLM + 执行）；`key_challenge` 准确 | ✅ 好 |
| 形式化 | `formal_def='Mo = F(Mi,T)'`（规则补的）；`method_limits` 3 条 | ✅ 好 |
| 元数据 | `authors` 完整、`abstract` 1383 字 | ✅ 好（但可规则抽） |
| 贡献主张 | `claims` 2 条；`gaps` 1 条 51 字 | ⚠️ 中（原文有 3+ 条） |
| 实验做法 | `data_sources` 5 个（规则）；`result_tables` 3 张（规则） | ✅ 好（规则比 LLM 强） |
| 空字段 | `figures=[]` `open_problems=[]` `negative_results=[]` `references=[]` `hyperparams=[]` `split_spec=''` | ⚠️ 部分原文确实没有，部分是该切片没覆盖 |

**问题不在"抽错了"，而在"该抽的没抽全"**——30 个字段一次出，模型会选择性忽略。

## 4. 分段方案（三选一）

### 方案 A：按"论文/算法/数据"三段（你提的思路）

```
S1 论文层：问题 + 贡献 + 元数据 + 写作惯例       (12 字段)
S2 算法层：方法 + 模块 + 假设 + 形式化            (13 字段)
S3 数据/实验层：数据源 + 协议 + 指标 + 表格        (10 字段)
```

**优点**：符合认知任务分层，和你之前的语义层 6 类结构对齐。
**缺点**：要重跑全部 52 篇（但只需 S1/S3，S2 已有）。

### 方案 B：按"抽取来源"分两段（我推荐）

```
第一段 · 规则层（零 LLM，确定性）：
  abstract / authors / references / data_sources / dedup_rule /
  split_spec / hyperparams / result_tables / formal_def / figures
  → 从 md 全文 + PDF 元数据直接抽，100% 可复现

第二段 · LLM 层（语义理解）：
  research_question / why_hard / paradigm / evidence_type /
  claims / gaps / open_problems / delta_claims / negative_results /
  method_limits / old_forms / arch_modules / why_not_other /
  key_challenge / mechanism / assumptions / ...
  → 15–18 个真正需要理解的字段
```

**优点**：
1. **负载直接减半**——LLM 从 30 字段降到 15–18 字段
2. **结构化字段交给规则更准**——`formal_def`/`result_tables` 已经被规则证明比 LLM 强
3. **可复现**——规则部分不依赖模型，换模型也不变
4. **改动小**——把 E1 YAML 的 `rules:` 段扩一下即可，LLM 部分删掉已由规则覆盖的字段

**缺点**：需要重写 E1 YAML 的 `all_fields`（从 30 降到 ~18）。

### 方案 C：按阶段动态裁剪（最省 token，但复杂）

为不同 run 目的生成不同 prompt：
```
run 目的=领域学习 → 只出 paradigm/evidence_type/evidence_norm/metrics
run 目的=新颖性   → 只出 claims/gaps/delta_claims/open_problems
run 目的=实验设计 → 只出 data_sources/protocol/metrics/hyperparams
```

**优点**：每次调用只出当下需要的字段，最快。
**缺点**：每个 run 要跑多次 LLM（目的不同跑不同次），总调用数反而上升；
且报告不完整，后续换目的要重跑。

## 5. 我的建议：方案 B + 局部 A

```
规则层（扩 E1 rules:）  → 10 个结构化字段
LLM 层（E1 精简）       → 18 个语义字段
LLM 层（E2 保持）       → 13 个算法字段（已验证质量好）
LLM 层（E3 精简）       → 6 个基准字段（部分交给规则）
```

先做一次小样本（4 篇）对比：
- 原方案：E1 30 字段一次出
- 新方案：规则 10 + LLM 18

比较同一篇论文的字段质量（非空率 + 与原文吻合度）。

## 6. 立刻要修的两个小问题

1. `abstract` 上限 2000 → 提到 4000（2 篇卡住）
2. 空字段区分「原文没有」vs「没抽到」——用 readiness skill 的 NA 判定

## 7. 产物清单

```
docs/factory/EXTRACTION_SPLIT_PROPOSAL.md   本分析
storage/sciforge/semantic_extraction/*.json 用于逐字段对比的报告
```
