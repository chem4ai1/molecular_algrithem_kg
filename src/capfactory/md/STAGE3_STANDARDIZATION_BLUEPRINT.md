# Stage3 标准化蓝图（修正版）

> **文档定位**：这是 Stage0–Stage3 抽取流水线中 **Stage3（装配层）** 的唯一设计依据。
> 面向对象是后续接手实现的智能体：按本文的「P0-1 → P0-5」顺序实现即可，无需再读其它文档做推断。
>
> **基线时间**：2026-11-13 15:53　**基线 commit 状态**：P0 五项均未实现（见 §1.4 核对表）
> **生成依据**：`capfactory/md/algrithem.md`、`docs/THREE_STAGE_EXTRACTION.md`、`docs/ALGORITHM_PROBLEM_FRAMEWORK.md`、`docs/LEADERBOARD_V2.md`、`docs/TABLE_EXTRACTOR.md`、`docs/PG_AND_BENCHMARK.md`、`capfactory/ontology/{schema_v3,chains,library}.py`、`capfactory/sciforge/{pipeline,deepdive,sources,benchmark_fill,leaderboard,tentacle}.py`

---

## 0. 一页摘要（给赶时间的智能体）

**问题**：Stage2 把论文肢解成了结构化片段（`STAGE2_*.json`），但**只有 1/4 进了图**，其余三份只写了文件。Stage3 现状是「导三份 CSV」，没有装配职责。

**方案**：把 Stage3 重新定义为 **Assembly（装配层）**，拆成 A1–A5 五个确定性子阶段：Collect → Normalize → Link → Materialize → Verify。**Stage3 内不调 LLM 做新抽取**（唯一可选例外是算法族推断）。

**六个必修 bug**（全部已定位到行号）：
1. `deepdive.py:287-289` 只放行 4 种关系，且 `REPLACES` 写成 `REPLACED_BY` → 科技树丢边
2. TBox 缺 4 条关系（`DELTA`/`HAS_LIMITATION`/`ON_METRIC`/`REFERS_TO`）→ 入图必失败
3. `EVALUATED_ON` 全图 0 条 → Benchmark 根找不到，B1/B2/B3 三条链永久空转
4. `sources.py:18-22` 模块级全局路径 → 10 篇批量互相覆盖
5. `benchmark_fill.py:266` `n.attrs.clear()` → 抹掉溯源
6. `pipeline.py:107-110` `try/except` 吞异常 → 失败不可见

**验收基线**：`default_library()` 关系数 98 → **102**；测试基线 **700** 项；MolMiner `2411.06608` 装配后 gate=`PASS`、悬空边=0。

---

## 1. 现状诊断

### 1.1 三处 `Stage3` 指三件事（必须先统一命名）

| 位置 | 行号 | `Stage3` 的实际含义 |
|---|---|---|
| `sciforge/pipeline.py` | `44-110` | 处理步骤第 4 步：导三份出处 CSV |
| `ontology/chains.py` | `155-172` `STAGES["stage3_benchmark"]` | **根族阶段**：以 Benchmark 为根的抽取 |
| `ontology/schema_v3.py` | `88-103` `ROOT_FAMILIES["Benchmark"]["stage"]=3` | 同上，数字形式 |
| `ontology/chains.py` | `144, 151` 注释 | "Stage2：算法的出处论文"、"Stage3：基准的出处论文" |

**结论**：同一个词指 4 种含义，是本项目最容易误解的地方。

### 1.2 Stage2 产物只有 1/4 入图（核心问题）

`pipeline.py:80-86` 实际代码：

```80:86:capfactory/sciforge/pipeline.py
    for k, v in dd["logical"].items():
        (out / f"STAGE2_{k}.json").write_text(...)
    tree = dd["logical"]["related_work"]
    graph_stats = tree_to_graph(graph, tree.get("chains") or [],
                                paper_id=paper_id)
```

`dd["logical"]` 实际产出四份（`deepdive.py:233-251`）：

| 产物 | 内容 | 是否入图 |
|---|---|---|
| `STAGE2_related_work.json` | `chains[]`（科技树，8 种关系） | ✅ 入图但丢边（见 1.3） |
| `STAGE2_method.json` | `steps[]` + `invariant` | ❌ **只写文件** |
| `STAGE2_benchmark.json` | `benchmarks[]` | ❌ **只写文件** |
| `STAGE2_benchmark.json` | `observations[]` | ❌ **只写文件** |

因此本体里 `A1_decompose` / `A2_code_grounding` / `B1_values` / `B2_data_profile` 四条链**没有装配器**，`project_chains` 必然查不到 → ABSENT。

### 1.3 唯一那次入图仍在丢边

`deepdive.py:11-12` 词表定义 8 种：

```python
TREE_RELS = {"HAS_LIMITATION", "ADDRESSED_BY", "IMPROVED_BY", "REPLACES",
             "BELONGS_TO", "COMPARES_WITH", "ON_METRIC", "DELTA"}
```

`deepdive.py:287-289` 只放行 4 种：

```287:289:capfactory/sciforge/deepdive.py
            if rel not in ("IMPROVED_BY", "REPLACED_BY", "BELONGS_TO",
                           "COMPARES_WITH"):
                continue
```

三个具体缺陷：
- **`REPLACES` vs `REPLACED_BY` 不一致** → 提示词要求 LLM 输出 `REPLACES`，代码却检查 `REPLACED_BY`，替代链全丢
- `HAS_LIMITATION` / `ADDRESSED_BY` / `ON_METRIC` / `DELTA` 四种最有信息的边全丢
- 节点 id `sourcepaper:tree:{slug(name)[:40]}` 会被截断到 40 字符 → **长方法名撞 id**

### 1.4 TBox 缺 4 条关系（实测）

```python
import capfactory.ontology.library as L
a = L._all_relations()      # 实测 98 条
# DELTA          MISSING
# HAS_LIMITATION MISSING
# ON_METRIC      MISSING
# REFERS_TO      MISSING
```

即使修好 1.3 的代码，这 4 条关系**不在 TBox 里**，`check_domain_range` 会判违反。

### 1.5 Benchmark 根永远找不到

`chains.py:254`：

```python
if c.root == "Benchmark":
    return paper_out("EVALUATED_ON", "Benchmark")
```

`tentacle.py:259` 同样只靠 `targets("EVALUATED_ON", "Benchmark")`。

而 `EVALUATED_ON` 虽在 TBox（`Paper|Algorithm|CodeRepository → Benchmark`），**全图 0 条实例**。结果：`benches=[]`，`B1_values` / `B2_data_profile` / `B3_source_paper` 三条链与 `benchmark.evaluation_values` / `benchmark.data_profile` 两类触手**永久空转**。这就是 `docs/INTAKE_TBOX_ABOX.md` 里"B1 只能 PARTIAL"的根因。

### 1.6 关系 domain 不匹配

`tentacle.py:308` 用 `HAS_STEP` 从 `Algorithm` 连 `AlgorithmStep`，但 TBox 定义：

```
HAS_STEP          : (AlgorithmComposition, AlgorithmStep, "方法栈的一步")
HAS_MODULE_DETAIL : (Algorithm, AlgorithmStep, "整体方法由哪些模块构成")   ← 正确
```

装配器若照抄 `HAS_STEP` → domain 违反。

### 1.7 工程性问题清单（已定位行号）

| # | 位置 | 问题 |
|---|---|---|
| E1 | `sources.py:18-22` `CSV_PATHS` | **模块级全局路径**，与 `out_dir` 无关；批量互相覆盖 |
| E2 | `sources.py:74` | `sourcepaper:{aid}:{kind}:{refno}` 不含 root，同 `[n]` 被多根引用时后者静默覆盖 |
| E3 | `sources.py:58-59` | `tree_relation[name] = rel` 同名覆盖（应为列表） |
| E4 | `sources.py:108/115` | `rep["csv"][k]` 是行数 int，`rep["csv_paths"]` 是全局路径，报告与本次 run 不一致 |
| E5 | `sources.py:153` | `resolve_sources(graph)` 不接受 `out_dir` |
| E6 | `sources.py:23-26` `FIELDS` | 缺 `match_score` / `provenance` / `run_id` / `inputs_sha`，无法复核 |
| E7 | `benchmark_fill.py:14` `OUT` | 全局硬编码报告路径 |
| E8 | `benchmark_fill.py:306/504` | `graph.save("storage_cf/sciforge/batch10_final_graph.json")` 覆盖别人的图 |
| E9 | `benchmark_fill.py:266` | `n.attrs.clear()` 抹掉 `source`/`evidence`/`provenance` |
| E10 | `benchmark_fill.py:483` | `refresh_from_pg` 遍历全图 Benchmark，与本次 run 无关 |
| E11 | `pipeline.py:107-110` | `try/except` 吞异常，不重试不降级 |
| E12 | `leaderboard.py:30-44` `direction_of` | 未命中词表默认 `max`，无 `direction_source` 标记 |
| E13 | `leaderboard.py:30-44` 并列 SOTA | 并列时保留先入库者，无 tie-break 记录 |
| E14 | `leaderboard.py:73` `rows_from_tables` | `unit` 恒 `""` |
| E15 | `table_extract` 兜底 | `benchmark:table:{aid}:{n}` 把属性区间表也当评测基准算 SOTA |
| E16 | `algorithm_problem.py:241` vs `citations.find_root_refs` | **两套原论文反查**并存且不一致 |
| E17 | `benchmark_fill.KNOWN` vs `benchmark_schema.FAMILIES` | **两套族词表** |

### 1.8 基线核对表（实现前请自行复核，全为 2026-11-13 实测）

| 项 | 期望基线 | 核对命令 |
|---|---|---|
| `STAGES` 键 | `stage1_paper`/`stage2_algorithm_code`/`stage3_benchmark` | `python3 -c "from capfactory.ontology.chains import STAGES; print(list(STAGES))"` |
| `ROOT_FAMILIES[].stage` | `{'Paper':1,'Algorithm':2,'Benchmark':3}` | 同上 schema_v3 |
| TBox 关系数 | **98** | `python3 -c "import capfactory.ontology.library as L; print(len(L._all_relations()))"` |
| `assembly/` 目录 | **不存在** | `ls capfactory/sciforge/assembly` |
| 测试数 | **700** | `grep -rho "def test_" tests/*.py tests/Phase/*.py \| wc -l` |
| MolMiner 三份 CSV 行数 | related 9 / algorithm 10 / benchmark 11 | `wc -l storage_cf/sciforge/source_*.csv` |
| `stage3_leaderboard` 真实落盘 | **0 处** | `grep -rl stage3_leaderboard storage_cf/sciforge/*/PIPELINE_REPORT.json` |

> ⚠️ `sources.py` 的 CSV 是全局的，所以那 9/10/11 行是**最后一次 run 覆盖后的残留**，且 `host_arxiv_id` 可能是 `2611.06237` 而非 MolMiner。这正是 E1 造成的。

---

## 2. 目标定义

### 2.1 四层职责边界（写进各模块 docstring，防止职责膨胀）

```
Stage0  Screen     决定「哪些内容值得抽」              → STAGE0_HEADING_PLAN.json
Stage1  Vector     把内容变成可检索块                   → blocks.jsonl
Stage2  Decompose  把每块肢解成结构化片段（不写图）      → STAGE2_*.json
Stage3  Assemble   把片段规范化、对齐、拼成图            → 图 + CSV + PG + Manifest
                   ↑ 只做确定性装配
                   ↑ 禁止调 LLM 做新抽取
                   ↑ 唯一可选例外：算法族/问题推断（标 optional，见 §5.4）
```

**一句话原则**：**Stage2 负责「抽得对」，Stage3 负责「装得对」。Stage3 不产生新事实**，只做映射、去重、校验、落盘。这样失败可定位、可重跑、可测试。

### 2.2 命名统一（P0-1 的具体内容）

| 现在 | 改成 | 理由 |
|---|---|---|
| `pipeline.py` 的 `stage0/1/2/3` 内部键 | `s0_screen` / `s1_vector` / `s2_decompose` / `s3_assembly` | 与根族数字解耦 |
| `chains.py:155` `STAGES` | 改名 `ROOT_STAGES`，**删除 `order` 字段** | 根族不是"阶段" |
| `schema_v3.py:89/96/99` `"stage": 1/2/3` | 改为 `"root_family": "Paper"/"Algorithm"/"Benchmark"` | 同上 |
| `chains.py:144/151` 注释 "Stage2/Stage3" | 改为 "Algorithm 根 / Benchmark 根" | 消除歧义 |

**兼容策略**：`STAGES = ROOT_STAGES` 保留一个别名并标 `DeprecationWarning`，避免一次性打断 700 个测试。别名在下一轮删除。

---

## 3. 装配层架构：A1–A5

新增包 `capfactory/sciforge/assembly/`：

```
assembly/
├── __init__.py        # 只导出 assemble_stage3 与 Stage3Manifest
├── contract.py        # Stage3Input / LinkPlan / Stage3Manifest / 词表常量
├── collect.py         # A1 收敛 Stage0-2 产物 + 完整性门 + inputs_sha
├── normalize.py       # A2 ID/词表/单位/方向规范化（纯函数，零 IO）
├── link.py            # A3 根定位（含自举）、出处反查、AST 对齐
├── materialize.py     # A4 写图 / 写 CSV / 写 PG / 刷新榜单
├── verify.py          # A5 TBox 校验 + 报告 + 指纹
└── cards.py           # 算法卡片 / 基准卡片（algrithem.md 的 1/4/7 落地）
```

### 3.1 A1 Collect — 收敛输入

```python
def collect(out_dir: Path, *, arxiv_id: str, paper_id: str, graph: POGraph,
            repo: str = "", md: str = "") -> Stage3Input
```

**必读 6 份**：`STAGE0_HEADING_PLAN.json`、`blocks.jsonl`、`STAGE2_related_work.json`、`STAGE2_method.json`、`STAGE2_benchmark.json`、原文 md。

**完整性门**（任一不满足 → `gate=BLOCKED`，不进入 A2）：
- 四份 STAGE2 JSON 存在且可 JSON 解析
- `graph` 中存在 `paper_id`
- `blocks` 的 `kind` 分布与 `STAGE0_HEADING_PLAN.blocks` 一致

**幂等**：`inputs_sha = sha256(规范化后的四份 JSON)`，写入 Manifest。重跑时若同 sha 且产物齐全 → 直接 `skipped`。

### 3.2 A2 Normalize — 规范化（纯函数，最先实现，最易测）

`normalize.py` 内所有函数**无 IO、无 LLM**，输入 dict 输出 dict。

| Stage2 字段 | 规范化规则 | 依据 |
|---|---|---|
| `input_form` / `output_form` | 映射到封闭词表 `{SMILES, 3D坐标, 向量, 图, 序列, 分布, 标量}`；越界值进 `gaps`，不落图 | `deepdive.py:58` 已有该词表 |
| `input_object` / `output_object` | 映射到 `ResearchObject` 词表 | `chains.py:130-133` |
| `metrics[]` | 走 `capfactory.ontology.metrics` 三策略（exact → alias → canonicalize）；unmapped 进 `metric_proposals`，**禁止造节点** | 保榜单可比 |
| `baselines[]` / `methods[]` / `code_symbols[]` | `slug()` + `leaderboard.normalize_model_name()`（去 `(ours)`） | 同模型多种写法 |
| `formula_ref` | 只接受 `(1)`–`(12)`，其余清空 | `deepdive._issues:44` |
| `observations[].value` / `.unit` | `_num()` + `table_extract._clean_metric()` 解析单位 | 修 E14 |
| 科技树 8 关系 | 见 §5.1 的关系映射表 | 修 §1.3 |

**输出**：`NormalizedInput`，`problems: list[str]`（越界/无法归一），`metric_proposals: list[dict]`。

### 3.3 A3 Link — 根定位与对齐（解决 §1.5 死结）

```python
def link(inp: NormalizedInput, *, tbox: OntologyLibrary,
         graph: POGraph, repo: str = "") -> LinkPlan
```

#### 3.3.1 根定位改为三级（**不再只靠 `EVALUATED_ON`**）

```python
def find_roots(graph, paper_id, kind, hints) -> list[str]:
    # 1. hints（Stage2 明确给出的名字）→ 与图内同类型节点 label 匹配
    #    Stage2_benchmark.benchmarks[].name 就是最强证据
    # 2. 图内关系：EVALUATED_ON / PROPOSES_METHOD / ADDRESSED_BY
    # 3. 都没有 → Stage3 自建根 + 补根边
    #    → 下一次 project_chains / run_tentacles 就找得到（自举）
```

**这条是整个方案的枢纽**：装配层必须负责把 `EVALUATED_ON` 补上，否则 `chains.project_chains`、`tentacle.run_tentacles`、`intake` 的 B 链永远断。

#### 3.3.2 统一原论文反查（修 E16）

把 `algorithm_problem.find_source_paper()` 与 `citations.find_root_refs()` 合并为 `link.resolve_source_ref()`：

| 优先级 | 规则 | 来源要求 |
|---|---|---|
| 1 | `[n]` → `parse_references()` → arXiv 精确 → DOI 精确 → 标题 Jaccard ≥ 0.72 | `THREE_STAGE_EXTRACTION.md` 已记录 |
| 2 | `(Author, Year)` 作者-年份式 | 当前**完全缺失**，本次补上 |
| 3 | 引用式名称（`Huang et al. RNN`）→ 用「作者+年份」匹配参考条目，**不得用 `rnn` 这类通用词** | `algrithem.md:68` P1 |
| 4 | 标题-算法名相似度校验；`votes` 相近时输出多候选，供人工填 `added_paper_id` | `algrithem.md:69` P1 |

#### 3.3.3 AST 对齐

`code_symbols[]` 与仓库 AST（`_ast_functions(repo)`）求交：命中 → 建 `CodeFunction` + `REALIZED_BY`；未命中 → 写入 `LinkPlan.gaps`，**不硬造符号**。

> MolMiner `2411.06608` 实测 12/12 命中，可作为该子模块的黄金用例。

### 3.4 A4 Materialize — 落盘

#### 3.4.1 入图映射表（**本文最重要的交付物**）

| Stage2 字段 | 节点类型 / id 模板 | 关系（src→dst） | 备注 |
|---|---|---|---|
| `related_work.chains[].methods[]` | `SourcePaper` / `sourcepaper:tree:{slug}` | `Paper --SITUATED_IN-->` | 保留 `tree_style`/`evidence` |
| `edges[COMPARES_WITH\|IMPROVED_BY\|REPLACES\|BELONGS_TO\|ADDRESSED_BY]` | 复用上表 SourcePaper | 同名边 | **8 种全保留** |
| `edges[HAS_LIMITATION]` | `Limitation` / `limitation:{aid}:{i}` | `SourcePaper --HAS_LIMITATION-->` | dst 是短语 |
| `edges[ON_METRIC]` | `MetricDefinition` / 复用 | `SourcePaper --ON_METRIC-->` | 走指标归一 |
| `edges[DELTA]` | **不建节点** | `SourcePaper --DELTA-->` + `properties.delta` | 数值挂边属性 |
| `method.steps[i]` | `AlgorithmStep` / `algostep:{aid}:{i:02d}` | `Algorithm --HAS_MODULE_DETAIL-->` | ⚠️ **不是 `HAS_STEP`**（domain 不符，见 §1.6） |
| `steps[i].formula` | `Formula` / `formula:{aid}:{i}` | `HAS_FORMULA` | `latex` 非空才建 |
| `steps[i].tools[]` | `Tool` / `tool:{aid}:{slug}` | `USES_TOOL` | |
| `steps[i].code_symbols[]` | `CodeFunction` | `REALIZED_BY` | AST 命中才建 |
| `method.invariant` | 写 `Algorithm.attrs.invariant` | — | 可选建 `Hypothesis` |
| `benchmark.benchmarks[i]` | `Benchmark` / `benchmark:{slug}` 或复用 | `Paper --EVALUATED_ON-->` | **补根边（自举）** |
| `benchmarks[i]` 契约字段 | `DataContract` / `datacontract:{aid}:{i}` | `HAS_DATA_CONTRACT` | 全字段落地 |
| `input_form` / `output_form` | `DataForm` / 复用 | `HAS_INPUT_FORM` / `HAS_OUTPUT_FORM` | 封闭词表内 |
| `input_object` / `output_object` | `ResearchObject` / 复用 | `HAS_INPUT_OBJECT` / `HAS_OUTPUT_OBJECT` | |
| `metrics[]` | `MetricDefinition` / 复用 | `USES_METRIC` | 归一后复用 |
| `baselines[]` | `Algorithm` / 复用 | `EVALUATES_METHOD` | 去 `(ours)` |
| `evaluation_tool` | `EvaluationTool` | `BINDS_EVAL_TOOL` | |
| `observations[i]` | `Observation` / `observation:{aid}:{i}` | `REPORTS_VALUE` + `OF_METRIC` | `evidence` 逐字校验 |
| 三类出处 | `SourcePaper` / `sourcepaper:{aid}:{kind}:{slug(root)}:{ref_no}` | `SOURCED_FROM` / `SITUATED_IN` / `RESOLVED_TO` | **id 加 root slug 防 E2** |

**每个节点强制 4 个溯源属性**：
```python
source       # "md:1423" | "ast:src/model.py:88" | "table:3"
provenance   # "stage2_llm" | "stage3_assembly" | "ast" | "table_extract"
run_id       # 本次 run
inputs_sha   # A1 计算的 sha
```

**每条边写之前**必须 `tbox.check_domain_range(src_type, rel, dst_type)`；违反则记入 `violations`，**不落图**。

#### 3.4.2 三份 CSV 标准化（修 E1–E6）

```python
SOURCES_DIR = out_dir / "sources"          # run-scoped，不再全局
FIELDS_V2 = FIELDS + ["match_kind", "match_score", "tree_relations",
                      "source_locator", "run_id", "inputs_sha"]
KEY = (host_arxiv_id, source_kind, root_id, root_name, ref_no)   # 加 root_id/root_name
```

- `SOURCE_INDEX.json` 与 CSV 同目录
- `resolve_sources(graph, *, out_dir=None)` 加参数
- `tree_relation` → `tree_relations`（JSON list in cell），修 E3
- 空 run 不覆盖既有清单；保留人工填写的 `added_paper_id`（现有 `_write` 的好设计保留）

#### 3.4.3 PG / 榜单标准化（修 E7–E15）

```python
def refresh_leaderboard(inp, plan, *, persist=False) -> dict:
    imp = import_tables(aid, paper_id, md,
                        benchmarks=plan.benchmark_index,    # Stage3 建好的 id 映射
                        paper_benches=plan.root_benchmarks,  # 不再查空的 EVALUATED_ON
                        refresh=True)
    ref = refresh_from_pg(graph, benchmark_ids=imp["benchmark_ids"],
                          persist=False)  # 存图由 assemble_stage3 统一做
```

必须同批修正：
1. `benchmark_fill.py:266` `attrs.clear()` → `attrs.update()`，保留溯源
2. 删除 `benchmark_fill.py:306/504` 的硬编码 `graph.save`，改由 `assemble_stage3` 写 `out_dir/graph.json`
3. 方向优先读 `kg.metric.direction`；启发式结果标 `direction_source=heuristic` 进 warnings
4. 并列 SOTA 增加 `ties: [...]`（不破坏现有 `sota_by_metric` 结构）
5. `rows_from_tables` 写入 `unit`
6. `benchmark:table:*` 标 `is_evaluation=False`，不参与 SOTA

**失败不吞**（修 E11）：`stage3_leaderboard.ok=false` + `error` 进 Manifest，`gate` 降级但 A5 照出报告。

### 3.5 A5 Verify — 校验与报告

```python
@dataclass
class Stage3Manifest:
    run_id: str; arxiv_id: str; paper_id: str
    inputs_sha: str; tbox_hash: str
    a1: dict; a2: dict; a3: dict; a4: dict; a5: dict
    nodes_added: dict[str, int]      # 按类型
    edges_added: dict[str, int]      # 按关系
    csv_rows: dict[str, int]
    pg_rows: int
    sota_changes: list[dict]
    violations: list[dict]           # TBox 违反 / 证据失败 / 悬空边
    gaps: list[dict]                 # 未对齐、需人工
    warnings: list[str]
    gate: str                        # "PASS" | "PARTIAL" | "BLOCKED"
```

**三档门**（与 `intake` 两档门精神一致）：

| 判定 | 条件 |
|---|---|
| `BLOCKED` | 输入不全 / `inputs_sha` 无法计算 / 图里无 `paper_id` |
| `PASS` | 悬空边 0 **且** `must_have` 违反 0 **且** 三个根族各至少 1 条链 present |
| `PARTIAL` | 有 warnings（AST 未命中 / 指标 unmapped / 出处 unmatched / 榜单失败） |

**落盘 10 件**（全部在 `out_dir` 内）：

```
STAGE3_MANIFEST.json   STAGE3_REPORT.md      STAGE3_VIOLATIONS.json
STAGE3_LINK_PLAN.json  graph.json
sources/related_paper.csv  sources/algorithm.csv  sources/benchmark.csv
sources/SOURCE_INDEX.json
algorithm_cards.json   benchmark_cards.json   leaderboard.json
```

---

## 4. TBox 补齐（P0-2）

在 `ontology/schema_v3.py` 的 `V3_RELATIONS` 追加 4 条：

```python
"HAS_LIMITATION": ("SourcePaper", "Limitation", "科技树瓶颈：局限短语"),
"ON_METRIC":      ("SourcePaper", "MetricDefinition", "对比链所用指标"),
"DELTA":          ("SourcePaper", "Observation", "数值提升量"),
"REFERS_TO":      ("SourcePaper", "Paper", "出处对应的库内论文（未命中时为空）"),
```

**验收**：
- `default_library()` 关系数 **98 → 102**
- `compile_tbox().issues == 0` 仍成立（需新增断言）
- 8 种 `TREE_RELS` 全部可 `check_domain_range` 通过

同步修 `deepdive.py:287-289`：放行集合改为 `TREE_RELS`，并把 `REPLACED_BY` 更正为 `REPLACES`；同时保留 `REPLACED_BY` 作为别名（LLM 可能输出两种）。

---

## 5. 语义映射细则

### 5.1 科技树 8 关系 → TBox（修 §1.3）

| LLM 输出 rel | TBox 关系 | src 类型 | dst 类型 | dst 落点 |
|---|---|---|---|---|
| `HAS_LIMITATION` | `HAS_LIMITATION` | `SourcePaper` | `Limitation` | 新建，label=短语 |
| `ADDRESSED_BY` | `ADDRESSED_BY` | `SourcePaper` | `SourcePaper` | 复用 |
| `IMPROVED_BY` | `IMPROVED_BY` | `SourcePaper` | `SourcePaper` | 复用 |
| `REPLACES` / `REPLACED_BY` | `REPLACES` / `REPLACED_BY`（两条都留） | `SourcePaper` | `SourcePaper` | 复用 |
| `BELONGS_TO` | `BELONGS_TO` | `SourcePaper` | ? | 若 dst 是家族名 → 建 `AlgorithmFamily`，否则 `SourcePaper` |
| `COMPARES_WITH` | `COMPARES_WITH` | `SourcePaper` | `SourcePaper` | 复用 |
| `ON_METRIC` | `ON_METRIC` | `SourcePaper` | `MetricDefinition` | 走指标归一 |
| `DELTA` | `DELTA` | `SourcePaper` | `Observation` | **数值写边属性 `properties.delta`，不建数值节点** |

### 5.2 为什么 `DELTA` 不建节点

数值本身不是实体。建 `Value` 节点会让「1.2」和「1.20」成为两个节点，且无法比较。正确做法是**挂在边上**：`properties={delta: "+1.2", unit: "%", metric: "..."}`。

### 5.3 算法卡片（`cards.py`，接 `algrithem.md` 的 1/4/7）

```python
def build_algorithm_cards(inp, plan, *, use_llm=False) -> dict:
    # 步1 候选识别：来源改为 Stage2 产物，不再从全图取
    candidates = method.code_symbols + related_work.methods + benchmark.baselines
    # 步2/3/6：classify_rule → resolve_source_ref → FAMILY_TASK + 白名单
    # 步4：algorithm_fill.extract_by_family(
    #          name, family, context=method.steps[i].mechanism)
    #      ← 恢复族专属字段为二级卡片
    # 步5：algorithm_problem.infer_problem_core，强制标 inference_basis
    # 步7：algorithm_fill._validate 校验 + build_index(graph) 重建
```

`algrithem.md` 三条建议的落点：

| 建议 | 落点 |
|---|---|
| P0 步骤 1/4/7 挂进 pipeline，与 `stage3_leaderboard` 对称 | 本 §3.4.4，与榜单同为 A4 子模块 |
| P0 恢复族专属字段为二级卡片 | `cards.py` 的 `family_fields` 二级结构 |
| P1 `inference_basis` 逐字证据校验 | A2 + A5；无证据强制标「由族推断」并降检索权重 |
| P1 引用式名称用作者+年份 | A3 `resolve_source_ref` 优先级 3 |
| P2 代码符号回填卡片 | A4 写回 `REALIZED_BY` / `CodeFunction` |
| P2 按 task_type/族重排检索 | `build_index` 在 A4 末尾重建 |

### 5.4 LLM 使用边界

| 允许 | 禁止 |
|---|---|
| 算法族推断（标 `optional`，失败降级为 `classify_rule`） | 用 LLM 抽新实体/新关系 |
| 问题-机理推断（`algorithm_problem`，标 `inference_basis`） | 用 LLM 补指标名、补数值 |
| 环消解类判断（如需要） | 用 LLM 决定 domain/range |

---

## 6. 真实黄金用例：MolMiner `2411.06608`

输入实测：**5 steps**、**3 benchmarks**、**8 observations**、**2 条科技树链**、1 个 invariant、12 个 `code_symbols`。

装配后**预期可断言的数值**：

```
A2 normalize:
    form 词表命中 6/6
    metric 归一：Wasserstein / Uniqueness / Novelty / Diversity → 全部命中已有 MetricDefinition

A3 link:
    Benchmark 根 3 个（新建 + 补 3 条 EVALUATED_ON）
    AST 12/12 命中

A4 materialize（新增节点）:
    AlgorithmStep 5      Formula 1 (eq 2)      Tool 1 (RDKit)
    CodeFunction 12      DataContract 3        DataForm 4
    ResearchObject 4     Observation 8
    SourcePaper: related 4 / algorithm 2 / benchmark 1
    （现状 related 4 / algorithm 0 / benchmark 1，且全部未入图）

A5 verify:
    悬空边 0    must_have 违反 0    gate = PASS
    warnings: "3 篇出处 unmatched，需补 papers.csv"
```

**现状对比**（`storage_cf/sciforge/batch_multistage/2411.06608/`）：
- `PIPELINE_REPORT.json` 的 `stages` 只有 `stage3_sources`
- `stage3_leaderboard` **从未落盘**（全仓 0 处）

---

## 7. 实施顺序与验收

| 优先级 | 任务 | 产出 | 验收测试 |
|---|---|---|---|
| **P0-1** | 命名统一 | `ROOT_STAGES` + 别名 | `chains_summary()` 不含 stage 数字；700 测试不退化 |
| **P0-2** | TBox 补 4 关系 + 修 `tree_to_graph` | 102 关系 | 8 种 TREE_RELS 全可入图；`compile_tbox().issues==0` |
| **P0-3** | `assembly/{contract,collect}.py` | `Stage3Input` | 缺任一 STAGE2 → BLOCKED；同 sha 重跑 → `skipped` |
| **P0-4** | `assembly/{normalize,link}.py` | `NormalizedInput` / `LinkPlan` | MolMiner 三根齐、12/12 AST、8 关系全保留 |
| **P0-5** | `assembly/{materialize,verify}.py` + `assemble_stage3()` | 图 + Manifest | 悬空边 0、domain/range 全合法、幂等重跑不增节点 |
| P1-6 | CSV run-scoped（修 E1–E6） | `sources/` | 两 run 不互串；人工填值保留；ref_no 冲突不覆盖 |
| P1-7 | PG/榜单 6 处修正（E7–E15） | `leaderboard.json` | `unit` 非空；`ties` 可查；表级兜底不进 SOTA；失败不吞 |
| P1-8 | `cards.py`（算法 7 步的 1/4/7） | `algorithm_cards.json` | 含族专属二级字段；`build_index` 重建 |
| P2-9 | `pipeline.py` 合并为一个 `s3_assembly` | `PIPELINE_REPORT.stages.s3_assembly` | 出现且 `ok` 由 Manifest 决定 |
| P2-10 | Web v7 增加 Stage3 装配卡片 | 页面 | 冒烟 +1 |

### 7.1 每步的「不可破坏」约束

1. **700 个测试必须全绿**（现有基线）
2. **`smoke_test.py` 45/45**
3. **`compile_tbox().issues` 必须为 0**
4. **不改 `Stage2` 的 prompt 与产物格式**（Stage3 只消费，不修改上游契约）
5. **不删任何现有函数签名**；需要改签名时保留旧签名作 wrapper

### 7.2 建议的提交粒度

```
commit 1  P0-1 命名统一（纯重命名 + 别名）
commit 2  P0-2 TBox 4 关系 + tree_to_graph 修丢边
commit 3  P0-3 assembly/contract.py + collect.py + 测试
commit 4  P0-4 assembly/normalize.py + link.py + 测试
commit 5  P0-5 assembly/materialize.py + verify.py + assemble_stage3 + 测试
```

每个 commit 独立可回滚，且都能单独跑测试。

---

## 8. 反面清单：实现时**不要**做的事

| 不要 | 原因 |
|---|---|
| 在 Stage3 里调 LLM 抽新实体 | 破坏"可重跑、可测试"；新事实应回 Stage2 |
| 用 `HAS_STEP` 从 `Algorithm` 连 `AlgorithmStep` | domain 是 `AlgorithmComposition`，会违反 TBox |
| 给数值建节点（`DELTA`/metric value） | 数值不是实体，挂边属性 |
| 让 `benchmark:table:*` 参与 SOTA | 属性区间表不是评测基准（E15） |
| 用 `attrs.clear()` 写属性 | 抹掉溯源（E9） |
| 在 `sources.py` 用模块级路径 | 批量互相覆盖（E1） |
| 用 `try/except` 静默吞掉 Stage3 失败 | 失败不可见（E11） |
| 一次性删掉 `STAGES` 别名 | 会打断 700 测试 |
| 依赖 `EVALUATED_ON` 找 Benchmark 根 | 全图 0 条，必须自举（§1.5） |
| 让 4 套 TBox 口径继续并存 | 40/72、44/90、45/98、46/96 已四处不一致 |

---

## 9. 附录：关键代码位置速查

| 用途 | 文件:行号 |
|---|---|
| 流水线主入口 | `sciforge/pipeline.py:28` `run_pipeline` |
| Stage2 只入图 1/4 | `sciforge/pipeline.py:80-86` |
| 科技树入图（丢边） | `sciforge/deepdive.py:270-300`，放行判断在 `:287-289` |
| 科技树词表 | `sciforge/deepdive.py:11-12` `TREE_RELS` |
| 三类 prompt | `sciforge/deepdive.py:16-70` |
| Stage2 产物结构 | `storage_cf/sciforge/batch_multistage/2411.06608/STAGE2_*.json` |
| 出处 CSV（全局路径） | `sciforge/sources.py:18-26` |
| 出处 CSV 冲突 | `sciforge/sources.py:74` |
| TBox 关系合并 | `ontology/library.py:54` `_all_relations` |
| TBox 类/关系定义 | `ontology/schema_v3.py:16` `V3_CLASSES`、`:56` `V3_RELATIONS` |
| 根族定义 | `ontology/schema_v3.py:88` `ROOT_FAMILIES` |
| 根阶段定义 | `ontology/chains.py:155` `STAGES` |
| 链定义（10 条） | `ontology/chains.py` |
| 触手定义（8 类） | `ontology/chains.py:174` `TENTACLE_SPECS` |
| 触手执行 | `sciforge/tentacle.py` |
| Benchmark 根定位（失效） | `ontology/chains.py:254`、`sciforge/tentacle.py:259` |
| 表格抽取 | `sciforge/table_extract.py:143` `parse_block` |
| PG 导入 | `sciforge/pgstore.py` `import_tables` |
| 榜单算法 | `sciforge/leaderboard.py:54/78/103` |
| 榜单方向（E12） | `sciforge/leaderboard.py:37` `direction_of` |
| 基准填充硬编码（E7-E9） | `sciforge/benchmark_fill.py:14/266/306/504` |
| 指标归一 | `ontology/metrics.py` |
| 算法族 schema | `sciforge/algorithm_schema.py` |
| 算法填充 | `sciforge/algorithm_fill.py:123/194/299` |
| 算法问题框架 | `sciforge/algorithm_problem.py:241/396` |
| intake（TBox 编译） | `sciforge/intake.py:91` `compile_tbox` |

---

## 10. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| `md/algrithem.md` | **算法侧子设计**。本文 §5.3 是其 P0/P1/P2 的落点 |
| `docs/THREE_STAGE_EXTRACTION.md` | 三阶段抽取契约。本文 §2.2 修正其命名歧义 |
| `docs/ALGORITHM_PROBLEM_FRAMEWORK.md` | 算法问题框架。本文 §3.3.2 统一其反查逻辑（E16） |
| `docs/LEADERBOARD_V2.md` | 榜单设计。本文 §3.4.3 修其 6 处工程问题 |
| `docs/TABLE_EXTRACTOR.md` | 表格抽取。本文 E15 修正其兜底误判 |
| `docs/PG_AND_BENCHMARK.md` | PG schema。本文 §3.4.3 复用 |
| `docs/INTAKE_TBOX_ABOX.md` | intake 契约。本文 §1.5 解释其"B1 PARTIAL"的根因 |
| `docs/V3_ONTOLOGY.md` | V3 本体。本文 §4 追加 4 关系 |

**冲突处理原则**：本文与任何文档冲突时，**以本文为准**（本文基于 2026-11-13 代码实测），并同步修正被冲突文档。
