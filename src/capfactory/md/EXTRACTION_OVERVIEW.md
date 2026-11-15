# 知识抽取总览：从论文到语义层图谱

> 本文是抽取链路的**代码级说明**：每一节都给出文件路径与函数入口，便于对照源码。
> 相关文档：`docs/EXTRACTION_PARADIGM_RESEARCH.md`（范式调研）、
> `docs/EXTRACTION_ARCHITECTURE.md`（属性级矩阵）、
> `docs/SEMANTIC_EXTRACTION_DESIGN.md`（契约设计）、
> `docs/FULL_BATCH_RUN.md`（全量运行）。

## 0. 一句话定位

抽取的目标**不是**把论文变成一大堆节点，而是把「客观可抽取的事实」按
**语义层 6 类**填进图谱，其余派生视图留给应用层：

```
论文 md ──► [确定性层: 分块/表格/AST/元数据]
        ──► [LLM 层: E1–E6 六个小契约]
        ──► [校验层: 词表/逐字证据/类型归一]
        ──► [范式层: NER/规范化/关系落地/模块追踪]
        ──► 语义层图（6 类）
        ──► [应用层挖掘] 复现/生成论文时才构建
```

**两条链路并存**：

| 链路 | 入口 | 目标 TBox | 状态 |
|---|---|---|---|
| legacy | `sciforge/stage_extract.py`、`deepdive.py` | 46 类旧 TBox | 保留（pipeline/老测试依赖） |
| **新链路** | `semantic/extraction/runner.py` | 语义层 6 类 | **当前主力**，已跑 783 篇 |

## 1. 语义层：抽取的目标结构

定义在 `capfactory/semantic/tbox_v4.py`，用 `SEMANTIC_CLASSES` 声明
「类 → 字段(名, 级别, 说明)」：

```python
SEMANTIC_CLASSES = {
  "Paper":           ("论文", (("title","must"), ("research_question","should"), ...)),
  "Algorithm":       ("算法", (("name","must"), ("mechanism","should"), ...)),
  "AlgorithmModule": ("算法模块（原 AlgorithmStep）",
                      (("name","must"), ("mechanism","should"),
                       ("formula","optional"), ("inputs","should"), ("outputs","should"))),
  "CodeRepository":  ("代码仓库", (("repo_name","must"), ...)),
  "CodeFunction":    ("代码函数", (("name","must"), ("purpose","should"),
                                  ("comment","optional"), ("params","optional"),
                                  ("returns","optional"), ("func_type","should"))),
  "Benchmark":       ("基准", (("name","must"), ("input_form","should"),
                              ("output_form","should"), ("metrics","should"),
                              ("model_results","should"), ...)),
}
```

**被删掉的 9 类**（`Section / Observation / ResearchQuestion / ProblemCategory /
MetricDefinition / LeaderboardEntry / DataContract / Evidence / Limitation /
SourcePaper`）全部有落点：或降级为属性（`Paper.research_question`、
`Benchmark.metrics[]`、`Benchmark.model_results[]`），或上移到应用层
（`capfactory/applayer/`）。落点表见 `tbox_v4.REMOVED_CLASS_MAP`。

**关键约束（`contracts.NON_LLM`）**：下面这些字段**不允许 LLM 抽**，只能由规则/AST/表格填：

```python
NON_LLM = {
  "Paper": ("title","arxiv_id","doi","year","venue","domain","flow_family","keywords"),
  "CodeRepository": ("repo_name","repo_url","local_path","license","is_original_repo"),
  "CodeFunction": ("name","purpose","comment","params","returns","func_type"),
  "Benchmark": ("model_results","sota_by_metric","is_evaluation"),
}
```

所以 `CodeFunction` 的 `llm_fields_of("CodeFunction") == ()` —— 完全不让模型碰。

> **重要**：`NON_LLM` 是**代码侧契约**，不是给大模型看的提示词。
> 2026-11-14 优化前，`contract_text()` 会把
> 「- CodeFunction: （本阶段不由 LLM 抽…）」这种句子打印进每个 prompt，
> 模型本来就没有这些输出位，说它等于纯噪声。现已删除：
> 阶段契约只列「本阶段目标类的 LLM 字段」，无关类一个字都不出现。

## 2. 确定性层：不花 LLM 的字段

### 2.1 切片：优先 blocks，缺失回退原文

`semantic/extraction/runner.py::_slices(md, arxiv_id)`

```python
KIND_MAP = {"paper": ("abstract","introduction","background","related_work"),
            "algorithm": ("method","approach","model","architecture"),
            "benchmark": ("experiment","result","evaluation","benchmark")}
LINEAGE_KINDS = ("related_work","introduction","method","approach")
```

读 `storage_cf/sciforge/batch_multistage/<aid>/blocks.jsonl`，按 `kind` 聚合；
`paper` 切片不足 3000 字时用原文前 6000 字补足；返回 `(slices, meta)`，
`meta.source` 会是 `blocks.jsonl` 或 `fallback`。**783 篇里只有 10 篇有 blocks**，
其余全部走 fallback。

### 2.2 表格数值：主路径

`sciforge/table_extract.py`（`_clean_metric` / `_looks_metric` / `_num` 等）
把 markdown 表格拍平成结果行，`sciforge/leaderboard.py::rows_from_tables` 转成
`{model_name, metric_name, value_raw, unit, paper_id, provenance}`。

在 runner 里：

```python
def _table_results(md, aid):
    from ...sciforge.table_extract import parse_tables
    from ...sciforge.leaderboard import rows_from_tables
    return rows_from_tables(parse_tables(md), paper_id="paper:"+aid, benchmark_id="")
```

`provenance` 形如 `table_extract:1`，这是后面**单元格级溯源**的依据。

### 2.3 去重：表格优先

`runner.py::_dedup_results(rows)` 按 `(model, metric, value)` 归一，表格行排在
LLM 兜底行之前，因此重复时保留表格版本（更可信）。

### 2.4 AST：`CodeFunction` 的唯一来源

`ontology/modules.py::code_structure(repo_root, max_files, max_symbols)`

```python
item = {"file": rel, "name": node.name, "params": ", ".join(args),
        "returns": ret,                       # ast.unparse(node.returns)
        "func_type": _ast_func_type(...),     # yield→generator / forward / init / loss / io…
        "signature": sig, "owner": owner,
        "doc": doc, "lineno": node.lineno}
```

`_ast_func_type()` 判定顺序：类 → `__init__` → 含 `yield` → `forward` →
名称关键词（loss/optim/schedule/io/transform/accessor）。

落图在 `build_module_graph()`，写 `purpose/comment/params/returns/func_type`，
不再写 `causal_role`。

### 2.5 元数据与规则校准

- 标题/arXiv/DOI/年份：文件名 + `data/papers/papers.csv`
- `Paper.domain_code`：**`papers.csv` 权威覆盖 LLM 判断**（`runner._csv_domain`），
  早期实测 LLM 判领域 9/10 篇错
- `Paper.flow_family`：由 `PROPOSES_METHOD → Algorithm.flow_family` 反查，不让模型猜
- `Paper.keywords`：`semantic/enrich.py::fill_keywords`，词频 × IDF，零依赖
- `CodeRepository.repo_url`：`enrich.fill_repo_url` 用原文 GitHub URL 与
  `repo_name` 归一匹配（9/10 命中）

## 3. LLM 层：六个小契约

契约声明在 `contracts.E_CONTRACTS`，prompt 模板在 `prompts.PROMPTS`，
用 `prompts.render(stage, ...)` 拼装。

```python
E_CONTRACTS = {
  "E1_paper":      # Paper 核心：research_question / problem_category / why_hard / relation_hints
  "E2_algorithm":  # Algorithm + AlgorithmModule（modules[] 带 code_symbols / tools）
  "E3_benchmark":  # Benchmark 结构（禁止输出数值）
  "E4_values":     # 只兜底表格之外的显式数值
  "E6_lineage":    # 算法-算法改进链（extends/replaces/improves/compared_with）
  "E5_relations":  # 仅 Module→Tool / Module→Formula 两类关系
}
```

每个阶段都只做一件事、输出小（约 2k 字符 prompt），失败重试时追加
`validator.retry_contract(stage)` 要求「只输出必填字段」。

### 3.1 prompt 的四段结构（按阶段裁剪）

`prompts.render(stage, ...)` 拼的是：

```
COMMON 通用规则（纯 JSON / 不确定留空 / ≤60 字 / evidence 逐字）
+ 【动态词表】vocab.render(text, stage)   ← 只给本阶段需要的词表
+ 语义层契约 contracts.contract_text(stage) ← 只给本阶段目标类的字段
+ 阶段模板 PROMPTS[stage]                  ← 该阶段唯一目标
```

`STAGE_CLASSES` / `STAGE_VOCABS` / `STAGE_INSTANCE_KINDS` 三张表决定裁剪：

| 阶段 | 契约类 | 词表 | A-Box 实例 |
|---|---|---|---|
| E1 | Paper | problem_category, domain_code | algorithms, benchmarks |
| E2 | Algorithm, AlgorithmModule | task_type | algorithms, code_symbols, modules |
| E3 | Benchmark | form | benchmarks |
| E4 | Benchmark | 无 | 无 |
| E5 | AlgorithmModule | 无 | modules |
| E6 | Algorithm | 无 | algorithms |

**实测体积**：优化前每阶段 `2806 + 2509 = 5315` 字符 × 6 = 31890；
优化后 6 阶段合计 **8395 字符（省 73.7%）**。契约块 611 → 142–232，
词表块 1205 → E1 588 / E2 482 / E3 168 / E4–E6 0。
精度收益：模型不再看到无关类的字段，越界输出减少；`guide_text` 也不再
重复注入契约与全量词表，`retrieve_instances` 的 BGE 兜底只在 E2 触发。

`COMMON` 里有一条关键规则：

```
4. 遇到词表外的新类：字段填 "other"，并在 proposed_new 写出建议新类名。
```

### 3.2 各阶段要点

| 阶段 | 输入切片 | 关键约束 | 代码 |
|---|---|---|---|
| E1 | `paper` | `research_question` 是字符串不是数组；`problem_category` 只用词表 | `prompts.PROMPTS["E1_paper"]` |
| E2 | `algorithm` + AST 符号 | `code_symbols` 只能从清单选；`tools` 只写方法节真实出现的 | `"E2_algorithm"` |
| E3 | `benchmark` | **不要输出任何数值**；form 从封闭词表选 | `"E3_benchmark"` |
| E4 | `benchmark` | 只补表格外数值；禁 epoch/表号/学习率；**表格 ≥40 行时跳过** | `"E4_values"` |
| E6 | `lineage`(related_work+method) | 谱系措辞才抽；`compared_with` 不建边 | `"E6_lineage"` |
| E5 | `algorithm` | 只允许 tool/formula | `"E5_relations"` |

调用与重试在 `runner.py::_call_stage`：

```python
raw = fn(prompt, max_tokens=1600, timeout=180)
out, issues = validate(stage, parse_llm_json(raw), source_text=text)
bad = fatal(issues)
if tolerate_empty and bad and all(x.startswith("missing:") for x in bad):
    bad = []          # 数据集/综述论文抽不出新算法是合法的
```

## 4. 校验层：把「编造」变成机械失败

文件 `semantic/extraction/validator.py`。核心原则：
**辅助字段失败不阻断核心字段**（历史教训：paper_core 首版因关系线索类型不符，
10 篇只成功 1 篇）。

| 机制 | 函数 | 行为 |
|---|---|---|
| 类型归一 | `_list` / `_str` | 字符串自动包成 list；dict/list 值降级为空 |
| 逐字证据 | `_norm_evidence` / `_evidence_ok` | 归一空白/弯引号/断词连字符后 `in` 原文，≤200 字 |
| 词表外扩表 | `_vocab_or_other` | 越界 → `"other"` + `vocab.observe()` 收集候选 |
| 数值合法性 | `_e4` | `NUM_PAT` 必须数字；metric 含 epoch/table/year 直接丢 |
| 关系类型 | `_e5` | `kind` 只能 `tool`/`formula` |
| 谱系类型 | `_e6` | `kind ∈ {extends, replaces, improves, compared_with}` |
| 致命判定 | `fatal` | 只有非 `warn:`/非 `other:` 的 `missing:*` 才算 fatal |

`_norm_evidence` 是逐字校验的关键：

```python
s = s.replace("\u2019", "'").replace("\u201c", '"')
s = re.sub(r"-\s*\n\s*", "", s)   # 断词连字符
s = re.sub(r"\s+", " ", s)
return s.strip().lower()
```

否则 blocks 拼接造成的换行/弯引号会让 evidence 全部假阴性。

## 5. 指导机制：让模型「知道边界」和「知道已有」

`semantic/extraction/guides.py`，三类指导拼成 `guide_text()`：

### 5.1 T-Box 指导

`tbox_guide()` → `contracts.contract_text()`：6 类字段、封闭词表位置、
「研究问题与问题类别是 Paper 的字符串属性」「数值写 `Benchmark.model_results[]`」。
**不再包含**「禁止输出 Observation/Section/...」这类历史约束（语义层已无这些类）。

### 5.2 A-Box 指导：实例检索

```python
def instance_catalog(graph):  # 已有算法/基准/代码符号/模块/族/任务类型
def retrieve_instances(text, graph, k=12):
    # ① 名称字面命中（确定性）
    # ② 语义检索兜底：优先 vector_sync.search（BGE，带 paper_ids）
    #    失败再退回 algorithm_problem.search_algorithms
def abox_guide(text, graph):
    # "库中已有 X 个 algorithms，例：..." + "库里存在的名字必须原样使用"
```

### 5.3 paper_type 与阶段计划

```python
STAGE_PLAN = {
  "method": ("E1","E2","E3","E4","E5","E6"),
  "dataset_benchmark": ("E1","E2","E3","E4","E5","E6"),   # 已补 E2，避免漏抽模块
  "theory": ("E1","E6"),
  "survey": ("E1","E6"),
  "system_tool": ("E1","E2","E5"),
  "application": ("E1","E2","E3","E4","E6"),
}
```

`classify_paper_type()` = 规则优先（关键词加权）+ 低置信时用**标题 + 摘要**
做一次轻量分类（只输出一个类型词，`max_tokens=24`，失败静默回退规则）。

2026-11-14 两项修正：
- runner 之前把 `chat_fn=None` 传给分类器，导致 **783 篇全是 `method=rule`，
  LLM 兜底从未生效**；现改为传入真正会调 LLM 的函数。
- 裸 `survey/review` 出现在 "recent surveys have…" 会误判综述；现降权到 0.5，
  只有 `this survey` / `we survey` / `systematic review` 等明确措辞才给 2 分。
- 触发条件由 `conf<0.30` 放宽为 `conf<0.5 或 top2 差 ≤1 或无信号`，
  实测约 14.2%（111/783）会触发，每次仅 24 token 输出。
- 返回新增 `margin` / `uncertain` 便于观测；`use_llm_classify=False` 可关闭。

## 6. 动态词表注入标准

`semantic/extraction/vocab.py`：

```python
VOCAB_LIMIT = 20        # 每类最多注入 20 项
PROMOTE_AFTER = 2       # 候选出现 2 次自动进词表
select(name, text, k=20)   # ≤20 全给；>20 字面命中优先 + 向量/字符相似度补足
observe(name, value)       # 词表外值 → 候选计数 → 达标 promote
render(text)               # 生成【动态词表】块
```

向量打分优先 `vector.embedder.BgeEmbedder`，失败回退字符 3-gram 余弦（零依赖）。
持久化在 `storage_cf/sciforge/semantic_extraction/vocab.json`。
实测已自动 promote：`generative_modeling`、`hypothesis_generation`。

## 7. 范式层：NER → 槽位 → 关系 → 模块

文件 `semantic/extraction/paradigm.py`，在 `run_extraction()` 末尾自动执行
（`apply_paradigm()`），结果写进报告 `report["paradigm"]`。**不调 LLM**。

### 7.1 阶段一 NER

```python
def recognize_entities(slices, graph) -> {algorithms, benchmarks,
                                          code_symbols, metrics, tables}
```

- ① 图目录命中：语义层已有节点名 → `source=graph_catalog`，带 `node_id`
- ② 文本模式：大写缩写/驼峰（≥2 大写或 `[a-z][A-Z]`）→ `source=surface_pattern`，带 `offset`
- ③ `Table N` 引用单独成类

实测 MolMiner 产出 **223 个候选**（algorithms 80 / benchmarks 70 / code_symbols 40 /
metrics 30 / tables 3）。这一步让后续「复用已有名字」有据可依。

### 7.2 阶段二 槽位规范化

```python
def canonicalize(report, graph, threshold=0.62):
    # 精确归一(_norm) → 字符 3-gram Dice ≥ 0.62 → 新建
    # code_symbols 与 CodeFunction 求交，未命中标 ungrounded
```

返回 `canonical_map / alias_groups / n_exact / n_fuzzy / n_new / n_ungrounded_code`。
MolMiner：`exact 4 / fuzzy 0 / new 0 / ungrounded_code 0` —— 抽出的实体全部对上已有节点。

**为什么需要**：调研里最容易被跳过的一步。没有它，`Mol-Miner`、`MolMiner`、
`the proposed model` 会变成三个节点。

### 7.3 阶段三 关系逐字落地

```python
def ground_relations(report, slices, full_text=None):
    text = _norm_evidence(full_text or "\n".join(slices.values()))
    pos = text.find(_norm_evidence(ev))
    # 长引文命中不了时，用前 40 字符再试一次
    # 命中 → grounded（带 char_offset）；否则 ungrounded（带 reason，不落图）
```

用**全文**而不是切片，因为证据常落在切片之外。MolMiner：grounded 8 / ungrounded 2，
后者是 `Geometry-aware Attention --formula--> Eq. 2`（`evidence_not_in_source`），
被明确排除在图外。

### 7.4 阶段四 模块追踪

```python
def track_modules(report, ast_symbols=None):
    for i, m in enumerate(modules):
        {step_order: i+1,
         depends_on: 上一个模块名,
         data_flow: f"{上一个 outputs} -> {本模块 inputs}",
         goal: mechanism[:80], formula,
         code_symbols, code_aligned, code_alignment_rate}
```

MolMiner 的输出：

```
Fragment Coarse-Graining → Symmetry-Aware Attachment Standardization
→ Order-Agnostic Rollout → Geometry-Aware Transformer → Fragment Predictor
```

| step | depends_on | data_flow |
|---:|---|---|
| 1 | — | 完整分子结构 |
| 2 | 片段粗粒化 | 片段集合及索引映射 → 片段原子环境及索引映射 |
| 3 | 对称性连接点标准化 | 确定性连接点映射 → 当前部分结构及目标性质 |

这对应调研里的「模块 = 接收什么、产生什么、为什么需要 + 信息流」。

### 7.5 槽位审计

```python
def slot_audit(report, graph):  # 只审计实际跑过的阶段
```

避免「dataset_benchmark 没跑 E2 却因算法槽位扣分」的误判。
返回 `checks[] / n_ok / n_total / score`。

## 8. 回填与派生层重建

### 8.1 回填

`semantic/apply.py::apply_all()` → 逐篇 `apply_one(g, rep)`：

| 阶段 | 落图动作 |
|---|---|
| E1 | 写 `Paper.research_question / problem_category / domain_code / why_hard / relation_hints` |
| E2 | 按名称找/建 `Algorithm`，写属性；建 `HAS_MODULE`；**`code_symbols` 对齐 `CodeFunction` 建 `MODULE_IMPLEMENTED_BY`** |
| E3 | 按名称找/建 `Benchmark`，写结构字段；建 `Paper-EVALUATED_ON->Benchmark` |
| E4 | 追加 `model_results`（`(model,metric,value)` 去重） |
| E6 | 只对 `extends/replaces/improves` 建 `SUBCLASS_OF`，边上带 `kind/evidence/paper_id` |
| E5 | **不建节点**，写 `application_hints.json` 留给应用层 |

幂等：`apply_all` 先清掉所有带 `paper_id` 属性的 `SUBCLASS_OF` 再重建。

### 8.2 派生层刷新

`semantic/refresh.py::refresh_all()`：

```
repair() → build_index() → export_missing_csv()
→ build_relations() → vector_sync.build() → mine_all()
```

一条命令串起：溯源修复、provenance 索引、缺失论文 CSV、关系索引、
BGE 向量索引、应用层图重建。

## 9. 数值抽取与单元格级溯源

`Benchmark.model_results[]` 每行长这样：

```json
{"model": "GDSS", "metric": "uniqueness", "value": "99.6", "unit": "",
 "is_sota": false, "paper_id": "paper:2411.06608",
 "provenance": "table_extract:1"}
```

`semantic/provenance.py::trace(graph, node_id)` 会把图内行与抽取报告
`model_results.rows` 按 `(model, metric, value)` join，补齐 `provenance/evidence`：

```python
cells.append({"cell_id": f"{node_id}#cell:{i}",
              "model", "metric", "value", "unit",
              "paper_id", "provenance", "evidence", "table_ref"})
```

`benchmark:zinc` 实测 **120 个 cell**，`provenance=table_extract:1`。
前端 `/relations` 的「单元格级溯源」表直接消费这个字段
（`web/static/provenance_card.js` 的 `renderProvenance()`）。

## 10. 代码联系：从论文模块到真实函数

三段链接：

```
原文 GitHub URL ──► CodeRepository（sources.py + enrich.fill_repo_url）
仓库本地目录   ──► code_structure() ──► CodeFunction（name/params/returns/func_type）
E2 的 code_symbols ──跨表对齐──► MODULE_IMPLEMENTED_BY
```

第三段在 `apply.py` 里：

```python
for sym in m.get("code_symbols") or []:
    fn = _find(g, "CodeFunction", str(sym))
    if fn:
        g.assert_rel(mid, fn.id, "MODULE_IMPLEMENTED_BY", paper_id="paper:"+aid)
    else:
        out["gaps"].append({"code_symbol": sym, "reason": "not_in_code_functions"})
```

**未命中就记 gap，不硬造**。AST 侧同时建 `CodeRepository-HAS_FUNCTION->CodeFunction`。

## 11. 批处理：783 篇断点续跑

`semantic/batch_extract.py`：

```python
def papers():          # data/docx/*.md → 783 个 arxiv_id
def report_exists(a):  # 报告存在即算已处理（ok=false 不反复重跑）
def status(n_shards=2) # total / done / n_ok / n_not_ok / failed / remaining
def run(limit, shard, n_shards)
```

- 完成判定用「报告文件存在」，避免 `ok=false` 让 `remaining` 永不为 0
- state 原子写（`os.replace`），报告也是原子写
- 分片 `--shard i --n-shards n`，两个进程各写独立 state
- 收尾要求 `remaining==0` 且拿到 `_finalize.lock` 文件锁

配套守护 `semantic/finalize_watch.py`：每 60s 轮询，全齐后自动
`apply_all → refresh_all`，写 `_finalize_done.json`。

## 12. 溯源

`semantic/provenance.py`：

| 函数 | 作用 |
|---|---|
| `trace(graph, node_id)` | 五层证据聚合（关系 / `paper_id` 属性 / 抽取报告 / 单元格 / 向量建议） |
| `audit(graph)` | 覆盖率 + 孤儿分类（`有属性但缺关系` / `报告命中` / `预置库` / `无线索`） |
| `repair(graph)` | 自动补 `PROPOSES_METHOD` / `EVALUATED_ON`（过 TBox 校验，幂等） |
| `export_missing_csv` | 两份 CSV + `provenance_report.json` |
| `build_index` | `provenance_index.json`（节点 ↔ 论文 正反向） |

`export_missing_csv` 的 12 列：
`node_id, label, type, reason, paper_id_attr, report_hits, model_result_sources,
suggested_arxiv_id, suggested_title, suggested_similarity, action, priority`。

`suggest_paper()` 只给**建议**，不自动写回图。

## 13. 实测（全量运行中，396 篇时点）

| 指标 | 数值 |
|---|---|
| 结构完整率 | 98.0%（388/396） |
| 槽位质量分 | 均值 0.827 / 中位 0.875 |
| 关系逐字落地 | 88.7%（1575/1776） |
| NER 实体候选 | 平均 209 / 篇 |
| 算法模块 | 1350 个 |
| 表格数值 | 7865 行 |
| 算法改进链 | 978 条（谱系类 576） |
| Tool/Formula 线索 | 852 条 |
| 论文类型 | method 283 / dataset_benchmark 79 / survey 26 / system_tool 4 / theory 4 |
| 单篇耗时 | 平均 111 s（2 并发） |

`n_not_ok=8` 全部是 E2 抽不出算法核心（`dataset_benchmark` 6 + `method` 2），
属合理空结果，已由 `tolerate_empty` 宽容。

## 14. 代码索引

| 文件 | 职责 | 关键入口 |
|---|---|---|
| `semantic/tbox_v4.py` | 语义层 6 类定义、删类落点 | `SEMANTIC_CLASSES` / `REMOVED_CLASS_MAP` |
| `semantic/extraction/contracts.py` | 阶段契约、非 LLM 字段、T-Box 文本 | `E_CONTRACTS` / `NON_LLM` / `contract_text` |
| `semantic/extraction/prompts.py` | 六阶段 prompt 模板与拼装 | `PROMPTS` / `render` / `stages` |
| `semantic/extraction/validator.py` | 类型归一、逐字证据、词表越界 | `validate` / `fatal` / `cross_check` |
| `semantic/extraction/guides.py` | T-Box/A-Box/paper_type 指导与实例检索 | `guide_text` / `retrieve_instances` / `classify_paper_type` |
| `semantic/extraction/paradigm.py` | NER/规范化/关系落地/模块追踪/槽位审计 | `apply_paradigm` |
| `semantic/extraction/runner.py` | 切片、CSV 校准、阶段编排、报告落盘 | `run_extraction` |
| `semantic/extraction/vocab.py` | 动态词表、top20 注入、other 扩表 | `select` / `observe` / `render` |
| `semantic/apply.py` | 回填语义层图（含代码联系） | `apply_one` / `apply_all` |
| `semantic/refresh.py` | 派生层一条命令刷新 | `refresh_all` |
| `semantic/provenance.py` | 溯源追踪/审计/修复/CSV | `trace` / `audit` / `repair` / `export_missing_csv` |
| `semantic/vector_sync.py` | 语义层 BGE 向量索引 | `build` / `search` |
| `semantic/batch_extract.py` | 全量断点续跑 | `run` / `status` |
| `semantic/finalize_watch.py` | 收尾守护 | `main` |
| `semantic/enrich.py` | repo_url/license/keywords/SUBCLASS_OF/算法级评测 | `enrich` |
| `semantic/migrate.py` | legacy 图 → 语义层图 | `migrate` |
| `sciforge/table_extract.py` | 表格拍平 | `parse_tables` |
| `sciforge/leaderboard.py` | 行列转换、方向、SOTA | `rows_from_tables` / `compute_sota` |
| `ontology/modules.py` | AST 解析与模块落图 | `code_structure` / `build_module_graph` |
| `web/provenance_api.py` | 溯源 API | `trace` / `audit` / `missing` / `refresh` |
| `web/relation_api.py` | 关系浏览器（含溯源卡片数据） | `relations` |
| `static/provenance_card.js` | 前端溯源卡片渲染 | `renderProvenance` |

## 15. 边界与常见问题

**Q：为什么页面看到的图比报告少？**
回填统一放在收尾（`apply_all`），抽取过程中语义层图不变。全量跑完由
`finalize_watch` 一次性重建。

**Q：为什么 `CodeFunction` 不用 LLM？**
`contracts.NON_LLM` 明确排除。函数名/参数/返回值/注释/类型全部来自 AST，
`_ast_func_type()` 用 `yield`、`forward`、`__init__` 判定，不靠名称猜。
`comment` 只有 34/49（源码只有这么多 docstring），这是真实数据。

**Q：`evidence_not_verbatim` 是不是抽取失败？**
不是。归一后仍不匹配才标 ungrounded，且**不落图**。全量 88.7% 的关系能逐字定位，
剩余 11.3% 多为公式排版/跨行断词，属于保守策略（宁缺毋滥）。

**Q：`n_not_ok` 会阻塞收尾吗？**
不会。完成判定用「报告存在」，`ok=false` 也算已处理；只是不参与回填的有效段。

**Q：词表会不会越抽越大导致 prompt 爆炸？**
不会。`vocab.render()` 每类最多注入 20 项（超出按向量相似度筛），
且词表外值先进候选，出现 2 次才 promote。

**Q：老论文没有 `blocks.jsonl` 能抽吗？**
能。`_slices()` 回退原文前 6000/12000 字，`meta.source=fallback`。
783 篇里只有 10 篇有 blocks，实测 fallback 质量可用（例：2508.01459 slot=1.0）。

## 16. 快速上手

```bash
cd /home/zengshuxin/xKG-main/xKG-main

# 单篇（会调 LLM）
.venv-linux/bin/python -c "from capfactory.semantic.extraction.runner import run_extraction as r; \
  print(r('2411.06608')['paradigm']['summary'])"

# 不调 LLM，只对已有报告补范式层
.venv-linux/bin/python -c "import json; from capfactory.semantic.extraction.paradigm import apply_paradigm; \
  d=json.load(open('storage_cf/sciforge/semantic_extraction/2411.06608.json')); \
  print(apply_paradigm(d)['paradigm']['summary'])"

# 全量续跑 / 查进度
nohup .venv-linux/bin/python -m capfactory.semantic.batch_extract --shard 0 --n-shards 2 > /tmp/b0.out 2>&1 &
.venv-linux/bin/python -m capfactory.semantic.batch_extract --status

# 回填 + 重建派生层
.venv-linux/bin/python -c "from capfactory.semantic.refresh import refresh_all; print(refresh_all())"

# 溯源审计与缺失清单
.venv-linux/bin/python -c "from capfactory.semantic.provenance import *; from capfactory.po import POGraph; \
  g=POGraph.load('storage_cf/sciforge/batch10_semantic_v4.json'); \
  print(audit(g)['by_type']['Algorithm']['coverage']); print(export_missing_csv(g)['n_missing'])"
```

## 17. 旧抽取链路的清理与统一（2026-11-14）

### 17.1 统一后的唯一入口

| 位置 | 之前 | 现在 |
|---|---|---|
| `sciforge/pipeline.py` | `stage3_paper_core` 调 `paper_core.apply_paper_core`（旧 LLM 重抽） | `semantic_extract` 调 `semantic.extraction.runner.run_extraction` |
| `sciforge/core.py` | 导出 `apply_paper_core` / `fill_papers` | 导出 `run_extraction` / `apply_all` / `refresh_all` |
| `sciforge/__init__.py` | 包级导出 `STAGE_PROMPTS` / `CALL_ORDER` / `deep_dive_module` 等旧 API | 移除，注释指向新入口 |
| `web/data_api.py` | `from ..sciforge.paper_core import FACET_LABELS` | 本地 3 个中文标签常量 |
| `web/extraction_api.py` | `_prompt_catalog()` 读 `deepdive.PROMPTS`（旧 3 模块） | 读 `semantic.extraction.prompts.PROMPTS`（新 E1–E6） |

**推荐调用方式**：

```python
from capfactory.sciforge.core import run_extraction, apply_all, refresh_all
# 或
from capfactory.semantic.extraction.runner import run_extraction
```

### 17.2 保留为兼容层（已加 DEPRECATED 头）

三个旧实现**未物理删除**，因为仍有 8 个测试与旧 `/extraction` 页面依赖它们，
其中部分（`deepdive.TREE_RELS`、blocks 分块、Stage3 装配输入）仍有效：

| 文件 | 保留理由 | 状态 |
|---|---|---|
| `sciforge/stage_extract.py` | `test_stage_extract.py` 测旧 4 prompt 的校验/重试；`semantic_contract()` 转发新契约 | 头部标 DEPRECATED |
| `sciforge/deepdive.py` | `TREE_RELS` 被 `test_stage3_assembly` 用；`stage2_deepdive` 仍产 `STAGE2_*.json` 供装配 | 头部标 DEPRECATED |
| `sciforge/paper_core.py` | `test_paper_relations.py` 测三核心/CSV 领域校准；`FACET_LABELS` 常量 | 头部标 DEPRECATED |
| `web/extract_v7.py` | 旧 v7 页面 API，`test_v7_ui` / `test_chain_viz` 直接 import | 保留注册 |

`sciforge/pipeline.py` 的 `stage2_deepdive` 属于**原料生产**（按块切分 + 科技树），
不是语义层抽取，故保留；新链路的 E1–E6 在它之后通过 `semantic_extract` 执行。

### 17.3 后续物理归档的前置条件

要把这 4 个文件真正移进 `backup/`，需要先完成三件事：

1. 把 `TREE_RELS` / `FACET_LABELS` / `CORE_FIELDS` 等**仍有效的常量**迁到
   `semantic/extraction/contracts.py` 或 `sciforge/assembly/contract.py`；
2. 把 `test_stage_extract.py`、`test_multistage.py::TestDeepDive`、
   `test_paper_relations.py::TestPaperCore` 三类**纯旧链路测试**迁到
   `backup/legacy_tests/`（其余测试保留）；
3. 旧 `/extraction` 页面若不再使用，从 `server.py::WEB_API_MODULES` 移除
   `extract_v7` 并把该页重定向到 `/relations`。

本轮采取「运行时统一 + 明确标记 + 迁移清单」而非暴力删除，
保证 783 unittest / Phase 81 / 冒烟 60 全部通过，同时让**新代码不可能再误用旧抽取实现**。


## 18. E4 调用优化（2026-11-14）

`E4_values` 的定位是「表格之外的数值」的 LLM 兜底。全量 783 篇实测：

```
E4 实际调用      733 篇（theory/survey/system_tool 的阶段计划本就不含 E4）
有兜底产出        64 篇（175 行）
零产出调用       669 篇（91.3%）
表格总行数      17810
```

**注意**：用户最初建议「对 theory/survey 且表格行数 >0 跳过 E4」，
实测**零收益**——`STAGE_PLAN["theory"]/["survey"]` 只有 `E1 + E6`，E4 从未被调用。
该规则仍保留为防御性配置（未来若给这两类加 E4 会生效）。

真正生效的是 `runner.should_skip_e4()`：

```python
def should_skip_e4(ptype, n_table_rows, *, run_stages=None,
                   enabled=True, min_table_rows=40):
    if not enabled or run_stages is not None: return False
    if ptype["paper_type"] in ("theory","survey") and n_table_rows > 0:
        return True
    return n_table_rows >= min_table_rows
```

阈值收益/损失（基于 733 篇真实报告回放）：

| 阈值 | 省调用 | 损失兜底行 | 损失篇数 |
|---:|---:|---:|---:|
| ≥1 | 209 | 78 | 26 |
| ≥10 | 191 | 70 | 23 |
| **≥40（默认）** | **113** | **37** | **20** |
| ≥80 | 72 | 13 | 8 |

默认 ≥40：省 113 次 E4 调用（15.4%），损失 37 行兜底，
占 17810 行表格数值的 **0.2%**。设 `e4_skip_min_table_rows=10**6` 可完全退回旧行为；
`min_table_rows=0` 则对理论/综述无条件跳过。

跳过时仍写完整的 `E4_values` 阶段记录
（`ok=True / skipped=True / reason=table_covered / n_table_rows`），
因此报告结构与 `rep["ok"]` 不变；表格数值照常进入 `model_results`。

**净调用账**：省 113 次 E4（约 700–900 字符输入 + 1600 token 输出上限），
新增最多 111 次分类调用（约 800 字符输入 + 24 token 输出），
token 成本净下降且阶段选择更准。
