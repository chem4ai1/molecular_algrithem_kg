# 论文 / 算法 / 数据三类属性：必要性、处理方式、难度

> 基于 52 篇实际抽取 + 4 篇新字段报告 + 与原文逐字段对比。
> 三类字段分开分析，每类按「必要 / LLM / 规则 / 难度」标注。

## 0. 分类标尺

| 标记 | 含义 |
|---|---|
| **必要** | 缺了下游阶段就 BLOCKED（进了 readiness.yaml 的 critical/any_of） |
| **有用** | 缺了降级可用，不阻断 |
| **装饰** | 有更好，没有也行 |

| 处理方式 | 判据 |
|---|---|
| **规则** | 固定形态/元数据，可确定性抽取，无需理解语义 |
| **LLM** | 需要理解、归纳、改写 |
| **外部** | 应从 API/文件系统取，不从论文正文抽 |
| **混合** | 规则先抽，LLM 补/校验 |

| 难度 | 判据 |
|---|---|
| **易** | 单篇命中率 >80%，与原文吻合 |
| **中** | 40–80%，或需要归纳 |
| **难** | <40%，或原文常没有，或需跨论文比较 |

---

## 1. Paper（36 字段）

| 字段 | 必要性 | 处理方式 | 难度 | 依据与建议 |
|---|---|---|---|---|
| `arxiv_id` / `title` | **必要** | **外部**(文件名/PDF) | 易 | 不该从正文抽；文件名自带 |
| `authors` / `abstract` / `year` / `venue` | 有用 | **外部**(DBLP/S2) | 易 | 正文抽不准；venue 52 篇里 26 篇缺失，LLM 与 vLLM 都补不动——应查 DBLP |
| `doi` / `references` | 有用 | **外部** | 中 | PDF 解析只 1.2% 覆盖；应查 Semantic Scholar 引用图 |
| `research_question` | **必要** | LLM | **易** | 52/52，51–73 字精准概括；现 100% |
| `why_hard` | **必要** | LLM | **易** | 52/52，MECo 53 字抓住 SMILES 问题；现 100% |
| `problem_category` | **必要** | LLM（词表） | 易 | 92%，受控词表 12 类；规则也可兜底 |
| `paradigm` | **必要** | LLM（词表） | 易 | 92%，4 类枚举；但判定影响 P0 门，需交叉校验 |
| `evidence_type` | **必要** | LLM（词表） | 中 | 92%，但有偏（SynCraft 有 benchmark 却判 derivational）→ 需 model_results 交叉校验 |
| `evidence_norm` | 有用 | LLM | 中 | 归纳类字段，需看整节 |
| `claims` | **必要** | LLM | 中 | 92% 有值但只抽 2 条（原文 3+）；**30 字段一次出时被选择性忽略** |
| `gaps` | **必要** | LLM | 中 | 同上，1 条/篇 |
| `open_problems` | 有用 | LLM | **难** | 40%，多数论文不写"open problem" |
| `delta_claims` | 有用 | LLM | 中 | 87% |
| `negative_results` | 有用 | LLM | **难** | 12%，发表偏差导致论文很少报阴性结果 |
| `method_limits` | **必要**(P0) | LLM | **难** | 8%（新字段）——但 MECo 抽到 3 条很准；问题是 30 字段里模型选择性忽略 → **建议单独成段抽** |
| `old_forms` | **必要**(P0) | LLM | **难** | 4%，同 method_limits |
| `formal_def` | **必要**(P0,有公式时) | **规则** | 中 | 6%（3/52）——低覆盖是**合理的**（只有 edit/gflownet/retro 写公式）；规则抽得准，不该用 LLM |
| `section_map` / `figures` | 有用 | LLM/规则 | 易/中 | section_map 92%；figures 抽不到（0%）→ 应改从 md 图片语法规则抽 |
| `citation_style` / `writing_style` | 有用 | LLM | 易 | 90%，短文本 |
| `data_sources` | **必要**(P2) | **规则** | 易 | 数据库名固定词表；规则比 LLM 准 |
| `dedup_rule` | **必要**(P2) | **规则** | 易 | Tanimoto/identity 阈值固定形态 |
| `split_spec` | 有用(P2) | **规则** | 中 | 10/52，写法多样（`80/10/10`/`8:1:1`/train%），正则难穷尽 |
| `hyperparams` | **必要**(P7) | **规则** | 中 | 35/52，参数名固定但值形态多 |
| `result_tables` | **必要**(P6) | **规则** | 中 | 48/52（旧报告）/ 4 篇新报告；md 表格解析可行，但表头判定需启发式 |
| `protocol_disclosure` | 有用 | LLM | **难** | 原文常在附录，E1 切片够不到 |

**Paper 层结论**：
- **必须 LLM 的只有 8 个**：research_question / why_hard / category / paradigm / evidence_type / claims / gaps / method_limits+old_forms（建议合并成一个"问题形式化"子任务）
- **必须规则/外部的 8 个**：arxiv_id/title/authors/abstract/venue + data_sources/dedup_rule/formal_def/result_tables
- **难的 6 个**：negative_results / open_problems / protocol_disclosure / method_limits / old_forms / split_spec——共性是「原文少写」或「写法不固定」

---

## 2. Algorithm（10–13 字段）

| 字段 | 必要性 | 处理方式 | 难度 | 依据与建议 |
|---|---|---|---|---|
| `name` | **必要** | LLM→规则归一 | 易 | 算法名自由文本，需 `_slug()` 归一 |
| `task_type` | **必要** | LLM（词表） | 易 | 12 类受控词表；用于 P5 baseline 池 |
| `mechanism` | **必要** | LLM | 中 | 62 字，MECo 抽得很准；需理解方法描述 |
| `modules[]` | **必要`(P1/P3)`** | LLM | 中 | 内部机理模块（name/mechanism/inputs/outputs） |
| `arch_modules` | **必要`(P1)`** | LLM | 中 | 4 篇实测：MECo 3 个、AgentDrug 3、SHACL 2——抽得准；需与 modules 区分开（系统级 vs 内部机理） |
| `why_not_other` | **必要`(P1)`** | LLM | **难** | 原文常不明说"为什么不用 X"；需要从对比段推断，推断错就编造 |
| `key_challenge` | **必要`(P1)`** | LLM | 中 | SynFlowNet 抽到"反向轨迹无法回到 s0"（正是 3.2 节标题） |
| `assumptions` | **必要`(P7)`** | LLM | **难** | 0%——原文很少明说前提；但它是 Type II 泄露审计的关键，值得二次抽取专门问 |
| `novelty_basis` | 有用 | LLM | **难** | 0%；作者很少直接声明"我的新颖性依据是什么"，需从对比段推理 |
| `limitations` | **必要`(P7)`** | LLM | 中 | 34.5%（老数据）；FailureModeLibrary 靠它聚合 |
| `flow_family` | 有用 | LLM（词表） | 中 | 18 类；覆盖率低（2%）因多数论文不写流派名 |
| `problems_solved` / `why_it_works` / `applicable_to` | 有用 | LLM | 中 | 描述性字段，缺了不影响门控 |

**Algorithm 层结论**：
- **LLM 是主力**——算法本质是语义理解，规则做不了
- **三个真难点**：`assumptions`（原文没有但必须知道）、`novelty_basis`（需推理）、`why_not_other`（原文不明说）
- **建议**：这三个难点不要塞进 E2 的 13 字段一次抽，改用**专门的 refine**（带定位段落的二次抽取）

---

## 3. Benchmark / Data（13 字段）

| 字段 | 必要性 | 处理方式 | 难度 | 依据与建议 |
|---|---|---|---|---|
| `name` / `input_form` / `output_form` | **必要** | LLM（词表） | 易 | 8 类 form 词表；MECo 这类"用别人基准"的论文该字段为空是正常的 |
| `n_samples` / `scale` / `modality` / `research_object` | 有用 | LLM | 中 | 描述性，覆盖率 44% |
| `metrics[]` | **必要`(P6)`** | LLM+词表 | 中 | 指标名自由，但方向(min/max)可规则判 |
| `model_results[]` | **必要`(P6)`** | **规则**(表格解析) | **难** | 19.9%——表格在 pdf 里常错乱；md 表格解析是更优路径 |
| `sota_by_metric` | 有用 | 规则(聚合) | 中 | 应从多篇 model_results 统计，单篇抽不出 |
| `protocol` | **必要`(P5)`** | LLM | 中 | 81.3% 老数据；seeds/split/eval_script 需看 Methods |
| `failure_modes` | 有用 | 规则(聚合) | **难** | 0.1%——单篇填不出来，应从 FailureModeLibrary 反向关联 |
| `is_evaluation` | 有用 | 规则 | 易 | 论文类型可规则判 |

**Benchmark 层结论**：
- **最少字段、最依赖"数据/表格"而非"文本"**——`model_results` 应该走表格解析，不该让 LLM 从正文猜
- **两个字段天然是聚合产物**：`sota_by_metric`/`failure_modes` 不该单篇抽，应该由 B 类图谱反向填
- **`name/input/output_form` 用 LLM+词表即可**，覆盖率高

---

## 4. 跨三类的总体判断

### 4.1 「必要」字段统计

| 层 | 必要字段数 | 其中 LLM | 其中规则/外部 |
|---|---:|---:|---:|
| Paper | 13 | 8 | 5 |
| Algorithm | 8 | 8 | 0 |
| Benchmark | 5 | 3 | 2 |
| **合计** | **26** | **19** | **7** |

**26 个必要字段里 19 个需要 LLM**——这是合理的，因为核心是语义理解。
但关键是把 **7 个结构化字段从 LLM 负担里拿走**。

### 4.2 「难」字段的共性

| 字段 | 难的原因 | 更好的做法 |
|---|---|---|
| `negative_results` / `open_problems` | 原文少写（发表偏差） | 不强行抽；用 readiness 判 NA |
| `assumptions` / `novelty_basis` / `why_not_other` | 原文不明说，需推理 | 专门 refine 带定位段落，允许"原文未明确" |
| `formal_def` / `result_tables` | 形态固定但 LLM 抽不准 | 规则抽（已验证） |
| `venue` / `references` | PDF 正文不含 | 外部 API（DBLP/S2） |

### 4.3 我推荐的分工（回答你的问题）

```
① 外部元数据（不调 LLM）：
   arxiv_id / title / authors / abstract / year / venue / doi / references
   → DBLP/S2 + PDF 文件名

② 规则抽取（不调 LLM）：
   data_sources / dedup_rule / formal_def / result_tables /
   hyperparams / split_spec / figures(md语法)
   → 从 md 全文，声明在 E1 YAML 的 rules: 段

③ LLM 一次抽（语义，18 字段）：
   research_question / why_hard / problem_category / paradigm /
   evidence_type / claims / gaps / delta_claims /
   section_map / citation_style / writing_style /
   name / task_type / mechanism / modules / arch_modules /
   key_challenge / limitations
   → E1+E2，每个 prompt 15-18 字段

④ LLM 二次抽（难点，专门 refine）：
   method_limits / old_forms / assumptions / novelty_basis / why_not_other
   → R7/R8，带原文段落定位，允许"未明确"

⑤ 聚合生成（不抽取）：
   sota_by_metric / failure_modes / BaselinePool / EvaluationNorm
   → B 类图谱，离线一次建
```

## 5. 下一步建议

1. 按上面 ①②③④⑤ 重组 E1/E2 YAML 的字段归属
2. 跑 4 篇 A/B 对比（原 30 字段一次 vs 新 18 字段 + 规则）
3. 把 5 个难点字段做成 R7/R8 refine 配置

要我开始做 1 和 3 吗？
