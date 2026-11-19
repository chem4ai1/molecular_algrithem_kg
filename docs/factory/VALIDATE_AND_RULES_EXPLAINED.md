# validate() 与 apply_rules() 到底做了什么

> 一句话：**validate 做清洗和裁剪，rules 做确定性补抽**。两者顺序固定，缺一不可。

## 1. 完整管线（精确版）

```
LLM 输出（不可信 JSON）
   ↓ parse_llm_json()          容错解析（markdown 代码块/截断/前后文字）
   ↓ validate()                ① 清洗 + 归一化 + 裁剪  ← 白名单式
   ↓ apply_rules()             ② 规则补抽 + 覆盖空值  ← YAML 声明式
   ↓ 报告落盘
   ↓ apply_one()               写进图
```

## 2. validate()：白名单式清洗

**入口**：`validator.validate(stage, data)` → 按 stage 分派到 `_e1`/`_e2`/`_e3`…

**四件事**：

### 2.1 类型强制

```python
_str(x)    # 非字符串→""，strip
_list(x)   # 非列表→[]
```

实测：LLM 返回 `"method_limits": "旧方法不可解释"`（字符串）→ 变成 `["旧方法不可解释"]`（列表）。

### 2.2 字段裁剪

`_e1` 只构造它认识的键。**LLM 幻觉出的字段直接丢弃**。

实测：`unknown_field: "LLM 幻觉出的字段"` → 输出里根本没有这个键。

### 2.3 长度截断

```python
"why_hard": _str(...)[:220]       # 300 字符 → 220
"abstract": _str(...)[:2000]
"mechanism": _str(...)[:300]      # E2
```

防止一条超长输出撑爆图。

### 2.4 结构归一化（嵌套对象只留指定子键）

```python
claims: [{"statement": ..., "evidence": ...}]   # LLM 的 junk 字段被丢
```

实测：`{"statement":"提出MECo","evidence":"Abstract L5","junk":"多余"}` → `{"statement":"提出MECo","evidence":"Abstract L5"}`。

**为什么这里是"第一道容易漏字段的关"**：
每加一个 YAML 字段，必须在 `_e1`/`_e2` 里加一行归一化，否则 LLM 输出了也会被丢。
我踩过三次（E1 加 5 字段、E2 加 3 字段、E2 加 3 字段的 apply 白名单）。
这就是 `scripts/check_field_sync.py` 存在的原因。

## 3. apply_rules()：YAML 声明式补抽

**入口**：`runner._call_stage()` 在 validate 之后调用。

### 3.1 规则来自 YAML，不是 Python

```yaml
# data/extract_target/stages/E1_paper.yaml
rules:
  preprocess: normalize_pdf       # 先修 PDF 拆字 0 _._ 6 → 0.6
  data_sources:   {type: db_names}
  dedup_rule:     {type: regex, patterns: [...], group: 0}
  split_spec:     {type: regex, patterns: [...]}
  hyperparams:    {type: hyperparam_list, max_items: 6}
  result_tables:  {type: md_tables, max_tables: 3, max_rows: 30}
  formal_def:     {type: regex, patterns: [...]}
```

Python 里只有 4 个**规则类型实现**（`db_names`/`regex`/`hyperparam_list`/`md_tables`），
不含任何具体正则——改规则只改 YAML。

### 3.2 执行流程

```python
# runner.py 里
rule_filled = apply_rules(spec.rules, 整篇 md 全文)
for k, v in rule_filled.items():
    if out.get(k) in (None, "", [], {}):   # 只补空值，不覆盖 LLM 的结果
        out[k] = v
```

**两个关键设计**：
1. **用整篇 md 而非切片**——切片会漏掉 Methods 里的公式和表格（我踩过这个坑）
2. **只补空值**——LLM 抽到的语义字段不被规则覆盖

### 3.3 MECo 实测补了 4 个

```
rule_filled = [data_sources, dedup_rule, result_tables, formal_def]

data_sources   = [ZINC, ChEMBL, USPTO, PDB, ChemCoTBench]
dedup_rule     = "Tanimoto similarity _≥_ 0.6"
formal_def     = "Mo =  F ( Mi, T )"
result_tables  = 3 张表
```

这 4 个 LLM 没抽到（切片看不到 Methods），规则从全文补回来了。

## 4. LLM 抽的到底有哪些字段？（不止 5 个）

上一轮我说的 5 个只是**新增的语义字段**，完整清单是：

### E1_paper（30 个字段）

| 类别 | 字段 |
|---|---|
| 核心问题 | `research_question` `problem_category` `why_hard` `relation_hints` |
| 证据规范化 | `evidence`（子键 research_question/why_hard）、`paradigm` `evidence_type` `evidence_norm` |
| 元数据 | `authors` `abstract` `references` `venue` `year` `doi` |
| 贡献与空白 | `claims` `gaps` `open_problems` `delta_claims` `negative_results` `protocol_disclosure` |
| 写作方法论 | `figures` `section_map` `citation_style` `writing_style` |
| **P0 新增** | **`formal_def` `old_forms` `method_limits`** |
| 规则补的 | `data_sources` `dedup_rule` `split_spec` `hyperparams` `result_tables` |

### E2_algorithm（13 个字段）

| 类别 | 字段 |
|---|---|
| 算法身份 | `name` `task_type` `mechanism` `why_it_works` `applicable_to` `problems_solved` `limitations` |
| 模块 | `modules[]`（每个含 name/mechanism/formula/inputs/outputs） |
| 前提与新颖性 | `assumptions` `novelty_basis` |
| **P1 新增** | **`arch_modules` `key_challenge` `why_not_other`** |

### E3_benchmark（10 个字段）

`name` `input_form` `output_form` `n_samples` `scale` `modality` `research_object` `metrics[]` `model_results[]` `protocol` `failure_modes`

**所以 LLM 抽的是 30+13+10 = 53 个字段**，规则补的是其中 7 个结构化字段。

## 5. 10 个状态转移：把"抽取"拆成可观察的机器

抽象流程说"抽取 → 建图 → 生成"，但那不是机器状态。真实的 10 个转移是：

```
状态0  PDF 文件
  │ parse_pdf()
状态1  Markdown（79K 字符，38 章节）
  │ YAML 驱动 E1/E2/E3
状态2  三份 JSON 报告（每份是 {ok, stages, data, rule_filled}）
  │ validate（清洗）+ rules（补抽）
状态3  归一化后的 data（30/13/10 字段）
  │ apply_one()
状态4  语义层图（6 类节点 / 9 关系，Paper 36 字段）
  │ Leiden + 统计聚合
状态5  B 类图谱（MethodLineage/Norm/FailureLib，带 rating + 边）
  │ route_phase(6维画像)
状态6  阶段路由结果（skills + tools + gate + 模板）
  │ readiness.yaml 审计
状态7  就绪度判定（P0~P7 的 READY/PARTIAL/BLOCKED + 补抽清单）
  │ WritingContext 类型接口
状态8  C 类决策节点（带 run_id/source/via/verdict + ledger）
  │ table_to_latex / skeleton / plot
状态9  论文部件（18 张 .tex + 章节骨架 + PDF 图）
```

**"可观察"的意思是**：每个状态都有落盘文件，你能打开看：

| 状态 | 落盘文件 |
|---|---|
| 1 | `data/docx/2510.14455.md` |
| 2 | `storage/sciforge/semantic_extraction/2510.14455.json` |
| 4 | `storage/sciforge/factory_knowledge_partial.json` |
| 5 | `storage/sciforge/factory_knowledge_leiden.json` |
| 6 | `phase_router_v2.route_phase()` 返回值 |
| 7 | `storage/sciforge/readiness_report.json` |
| 8 | `storage/demo/knowledge_graph_demo.json` |
| 9 | `storage/generated/*.tex` |

**状态转移的本质**：每一步都是「读上一状态的产物 → 用声明式配置（YAML）→ 写下一状态的文件」。
没有隐藏在内存里的步骤——这就是可回放、可调试的意思。

## 6. 复现

```bash
PYTHONPATH=src python3 stages/0_pipeline/simulate_extraction.py
cat storage/simulation/simulation_trace.json
```
