# 03 · Prompt 改造对照表（核心）

> 现有 prompt 的拼装（`semantic/extraction/prompts.py::render`）：

```
prompt = COMMON.replace("{catalogs}", cat) + PROMPTS[stage]
         cat = vocab.render(stage) + contract_text(stage)
```

即四段：**通用规则 / 动态词表 / 语义层契约 / 阶段模板**。
下文所有改造都落在这四段里，**不新增 LLM 阶段**（避免多一次调用）。

## 3.1 改造后的目标结构（五段）

```
① 通用规则（COMMON）       ← 加「证据纪律」两句
② 动态词表（vocab）        ← 不变
③ 语义层契约（contract）   ← 加「新增可选字段」声明（按阶段）
④ 【任务约束】NEW          ← 问题锚定 / 实验条件 / 主次结果 / 保真度
⑤ 阶段模板（PROMPTS）      ← 每个阶段加 1–2 个字段与 1 条禁令
```

第 ④ 段是**唯一新增段**，由 `contract_text(stage)` 之后的
`task_constraints(stage, ctx)` 注入，长度控制在 120–200 字符（实测当前
E1 约 1988 字符，加 200 仍在预算内）。

## 3.2 主表（12 条改造）

| # | 阶段 | 现有段落 | 新增/修改 | 知识点 | 改后落库字段 | 验收 |
|---|---|---|---|---|---|---|
| P1 | E1 | `research_question` 一句话 | 加 `problem_anchor_id`（`Q-<aid>`）与 `anchor_hash` | K1 | `Paper.problem_anchor` | 与 `METHOD_LOCK.problem_anchor` 一致 |
| P2 | E1 | `domain_code` 11 码 | 加 `evidence_norm`（该领域认什么证据） | K15 | `Paper.evidence_norm` | 枚举校验（validity/accuracy/perplexity…） |
| P3 | E2 | 模块 `inputs/outputs` | 加 `is_novel_component`（bool）与 `component_role` | K8 | `AlgorithmModule.is_novel_component` | 每篇至少 1 个 true 或显式 false |
| P4 | E2 | `mechanism` 一句话 | 加 `assumptions[]`（该模块成立前提） | K11 Type II | `AlgorithmModule.assumptions` | Type II 审计的输入 |
| P5 | E3 | `input_form/output_form/n_samples` | 加 `protocol{seeds, split, eval_script, epochs}` | K3 / INV-C1 | `Benchmark.protocol` | 缺 `seeds` 即 `blocked` |
| P6 | E3 | `metrics[]` | 加 `contribution_link`（该指标度量哪个贡献） | K11 Type III | `Benchmark.metrics[].contribution` | Type III 审计的输入 |
| P7 | E4 | `model_results[]` 五个字段 | 加 `seeds` / `sample_size` / `train_scale` | K5 | `model_results[].conditions` | 五项 evidence_sufficiency 可算 |
| P8 | E4 | 无主次区分 | 加 `outcome_class`（primary/secondary） | K4 | `model_results[].outcome_class` | primary 才走 numerical 门槛 |
| P9 | E5 | `tools_formulas` | 加 `citation_context`（引用支撑了哪句话） | K13 | `relations[].context` | 引用审计的输入 |
| P10 | E6 | `kind`（extends/improves/replaces） | 加 `assumption_delta`（改进了哪条前提） | K12 | `SUBCLASS_OF.properties.assumption_delta` | 逻辑审计输入 |
| P11 | 全部 | 无 | COMMON 加两句「证据纪律」 | K5 K12 | — | 抽查：不出现无出处的数值 |
| P12 | 全部 | `guide_text`（A-Box） | 加「本次实验矩阵」提示 | K3 | — | 与 `METHOD_LOCK.experiment_matrix` 一致 |

## 3.3 三个 before/after 原文示例

### 例 1 · E1 加问题锚定（P1）

**before**（`PROMPTS["E1_paper"]` 片断）：

```
- research_question: 一句话说清研究什么问题（≤60 字）
```

**after**：

```
- research_question: 一句话说清研究什么问题（≤60 字）
- problem_anchor_id: 固定格式 "Q-<arxiv_id>"，必须与全文主张一致
   ❗该 id 会被冻结，后续方法论/实验/结论都必须回引它；
     若原文实际研究的问题与标题不一致，以摘要中的研究陈述为准
```

### 例 2 · E4 加实验条件（P7）

**before**：

```
- model_results: [{"model","metric","value","unit","is_sota"}]
```

**after**：

```
- model_results: [{"model","metric","value","unit","is_sota",
                   "outcome_class","seeds","sample_size","train_scale"}]
  · outcome_class: primary（主实验）/ secondary（消融、鲁棒性、附加分析）
  · seeds: 整数；原文写 "3 runs" → 3；未提及 → null（不要猜 3）
  · sample_size / train_scale: 原文给出的样本量/训练规模，没有就 null
  ❗禁止把 "±0.01" 当成 unit；方差写进 seeds_note，不要混入 value
```

### 例 3 · E3 加协议字段（P5）

**before**：

```
- input_form / output_form / n_samples / scale / modality / research_object
```

**after**：

```
- input_form / output_form / n_samples / scale / modality / research_object
- protocol: {"seeds": int|null, "split": str, "eval_script": str|null,
             "epochs": int|null, "hardware": str|null}
  ❗只填原文明确写出的；缺 seeds 会被判 blocked（复现不可重复）
  ❗"we follow the standard split" 不是 split 值 → 填 null，不要编造 "80/10/10"
```

## 3.4 新增第 ④ 段「任务约束」的文本模板

```python
def task_constraints(stage: str, ctx: dict) -> str:
    """按阶段注入 120–200 字符的硬约束；不进词表、不进契约，独立一段。"""
    if stage == "E4_values":
        return (
            "【任务约束】\n"
            "- 每个数值必须标 outcome_class（primary/secondary）；\n"
            "- 必须给出 seeds（原文有才填）；单点结果标 seeds=1；\n"
            "- 数值不得跨列合并，不得用 unit 承载方差。\n")
    if stage == "E3_benchmark":
        return (
            "【任务约束】\n"
            "- protocol.seeds 缺失即视为不可复现，填 null 不要猜；\n"
            "- 每个 metric 必须说明它度量方法的哪个贡献（contribution_link）。\n")
    if stage == "E1_paper":
        return (
            "【任务约束】\n"
            "- 问题锚定 id 固定为 Q-<arxiv_id>，后续所有产物都要回引；\n"
            "- 领域证据规范只填枚举值，不写解释。\n")
    return ""
```

## 3.5 改造的验收清单

| 检查 | 方式 | 通过标准 |
|---|---|---|
| 新增字段是否真的落库 | 读 `semantic_extraction/*.json` | 4 篇样例中 ≥3 篇有 `protocol` / `outcome_class` |
| prompt 体积是否失控 | `len(render(stage))` | E1–E6 合计 ≤ 10000 字符（当前 8395） |
| 是否引入编造 | 人工抽查 20 条 `seeds` / `protocol` | 无「原文没写却填了值」 |
| 下游是否可用 | `compile_reprospec` | `numeric` SAU 带 `outcome_class`，`protocol` SAU 带 `seeds` |
| 是否影响 spec_hash | 两次编译对比 | 未改 `stable_key()` 的字段不进 hash |

## 3.6 一个重要取舍

`task_constraints` **不进 `contract_text`**，原因：

- 契约是「字段定义」，会被 `semantic_contract()` 复用到别处；
- 任务约束是「本次抽取的口径」，随任务变（复现 vs 生成要求不同）；
- 混在一起会让契约长度随阶段膨胀，破坏「契约只描述输出结构」的边界。

放在 `render()` 里单独拼接，既能被 LLM 看到，又不污染契约。
