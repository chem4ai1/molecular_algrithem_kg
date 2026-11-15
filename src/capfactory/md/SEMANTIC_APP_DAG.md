# 语义层 → 应用层 → DAG：三块拆开讲清楚

> 面向三个疑问：① 应用层到底怎么从语义层建出来；② 一篇论文怎么变成详细 DAG；
> ③ DAG 的每个过程分别用了应用层的哪些东西。
> 全部对照真实代码与 MolMiner 产物，不写理想化设计。

## 0. 先分清四个「图」，这是最容易混的地方

| 图文件 | 里有什么 | 谁写的 | 什么时候写 |
|---|---|---|---|
| `batch10_semantic_v4.json` | **6001 节点 / 7460 断言**，只有语义层 6 类 | `semantic/apply.py` | 抽取回填期 |
| `batch10_app_v1.json` | 纯语义层快照，**0 个应用节点** | `mine_all(task=None)` | `refresh_all` 时 |
| `app_reproduction.json` / `app_generation.json` | 语义层副本 + 按任务建的应用节点 | `applayer/builder.py` | **显式调用任务构建时** |
| `app_repro_runtime.json` | 单篇复现的运行时节点（MethodLock/RubricNode/…） | `reprospec/application.py` | 某次 `run_repro` 时 |

**第一条铁律**：抽取与回填期**不产生任何应用节点**。页面默认图
（`data_api._graph()` 读的就是 `batch10_app_v1.json`）里
`layer="application"` 的节点数为 0。应用节点只在任务启动时构建。

## 1. 应用层是怎么从语义层建出来的

### 1.1 入口与开关

```
mine_all(sem_g, task=None)              → 只复制语义层节点 + 断言，直接 return
mine_all(sem_g, task="reproduction")   → 复制语义层 + 跑挖掘器
mine_all(sem_g, task="generation")     → 复制语义层 + 跑挖掘器（不同集合）

用户侧唯一入口：build_task_layer("reproduction" | "generation")
```

`applayer/miner.py` 顶部先做两步：

```python
for n in sem_g.nodes.values():          # ① 完整复制语义层节点
    g.node(n.id, n.type, n.label, layer="semantic", **attrs)
for a in sem_g.assertions:              # ② 完整复制语义层断言
    g.assert_rel(a.source, a.target, a.relation, layer="semantic", **props)
```

所以任务层图 = **语义层原样一份 + 叠加的应用节点**，不是替代关系。
所有应用节点/边都带 `layer="application"`、`task=<任务名>`，可随时按层剥离。

### 1.2 过滤：同一个挖掘器，两个任务产出不同

`miner.py` 里所有挖掘器都照常计算，但 `add()` / `rel()` 会按 `TaskSpec` 放行：

```python
def add(nid, typ, label, **attrs):
    if typ not in allowed_c or nid in g.nodes: return False
    g.node(nid, typ, label, layer="application", task=task, **attrs)

def rel(s, r, t, **props):
    if r not in allowed_r or s not in g.nodes or t not in g.nodes: return
    g.assert_rel(s, t, r, layer="application", task=task, **props)
```

`allowed_c / allowed_r` 来自 `applayer/tasks.py::TASK_SPECS`：

| | reproduction | generation |
|---|---|---|
| 应用类 | `LeaderboardEntry` `MetricDefinition` `DataContract` `Evidence` `Limitation` `SourcePaper` | `ResearchQuestion` `ProblemCategory` + 共享 5 类 |
| 应用关系 | `HAS_ENTRY` `USES_METRIC` `HAS_METRIC` `HAS_CONTRACT` `SUPPORTED_BY` `HAS_LIMITATION` `SITUATED_IN` | `FORMULATES` `IN_CATEGORY` + 共享 5 条 |
| 挖掘器 | metrics / leaderboard / contracts / evidence / limitations / source_papers | questions / categories / + 共享 6 个 |

**结果**：复现任务不建 `ResearchQuestion`，生成任务不建 `LeaderboardEntry`——
两类任务视角互不污染，但共享 `MetricDefinition / DataContract / Evidence / Limitation / SourcePaper`。

### 1.3 八个挖掘器逐条（这是「建立」的实际内容）

| # | 挖掘器 | 触发条件（语义层字段） | 节点 id / 属性 | 建边 | 全量实测 |
|---|---|---|---|---|---:|
| 1 | `questions` | `Paper.research_question` 非空且非 unknown | `appq:<aid>`：question / paper_id / problem_category / derived_from | `Paper -FORMULATES->` | 783 |
| 2 | `categories` | `Paper.problem_category` 非空 | `appcat:<slug>`：code / n_papers（按类别聚合计数） | `ResearchQuestion -IN_CATEGORY->` | 17 |
| 3 | `metrics` | `Benchmark.metrics[]` 每条 | `appmetric:<slug(name)>`：name / direction / unit / n_benchmarks / sota_model（**按名字跨基准去重**） | 见 #5 | 447 |
| 4 | `leaderboard` | `Benchmark.model_results[]` 每行的 model+metric 都在 | `applb:<bench_slug>:<i>`：benchmark / model / metric / value / unit / is_sota / paper_id | `Benchmark -HAS_ENTRY->` | 247 |
| 4b | `contracts` | `Benchmark.input_form` 或 `output_form` 存在 | `appcontract:<bench_slug>`：input/output_form / n_samples / scale / modality | `Benchmark -HAS_CONTRACT->` | 604 |
| 4c | 指标挂行 | `appmetric:<metric>` 已存在 | — | `LeaderboardEntry -USES_METRIC-> MetricDefinition` | 随行 |
| 5 | 指标挂基准 | `Benchmark.metrics[]` | — | `Benchmark -HAS_METRIC-> MetricDefinition` | — |
| 6 | `evidence` | `model_results[]` 中 value+metric 都在 | `appev:<bench_slug>:<i>`：quote=`"<model> <metric>=<value>"` / kind=table_cell / paper_id / source=`provenance` | `LeaderboardEntry -SUPPORTED_BY-> Evidence` | 247 |
| 7 | `limitations` | `Algorithm.limitations[]`（字符串或列表） | `applim:<algo_slug>:<i>`：statement / algorithm / kind=stated | `Algorithm -HAS_LIMITATION->` | 728 |
| 8 | `source_papers` | `Paper -RELATED_TO-> Paper` | `appsrc:<slug(src:tgt)>`：title / ref_paper / relation / resolved | `Paper -SITUATED_IN->` | 26 |

> 表中 1/2 的 783/17 来自 `app_generation.json`，3–8 的数字来自
> `app_reproduction.json`（两任务挖掘器放行集合不同，见 1.2）。

**关键观察**：应用节点都不是「新事实」，而是把语义层里的**数组字段**
（`metrics[]`、`model_results[]`、`limitations[]`）和**字符串字段**
（`research_question`、`problem_category`）**提升成可查询、可按任务聚合的节点**。

判断标准：能一句话说清且不需要独立查询 → 留在语义层做属性；
需要跨论文聚合 / 按任务过滤 / 作为评分对象 → 提升到应用层。

### 1.4 实测规模

```
app_reproduction.json   8300 节点（应用 6 类：MetricDefinition 447 / LeaderboardEntry 247 /
                        DataContract 604 / Evidence 247 / Limitation 728 / SourcePaper 26）
app_generation.json     8853 节点（ResearchQuestion 783 / ProblemCategory 17 + 共享 5 类）
batch10_app_v1.json     6001 节点，应用节点 0
```

运行时类（`MethodLock` / `RubricNode` / `EvaluationResult` 等 9 类）**不进这两张全量任务图**，
只写单篇 `app_repro_runtime.json`，由 `reprospec/application.py` 在 run 启动时建。

## 2. 一篇论文怎么分解成「详细 DAG」

**先破除一个误解**：项目里其实有三个不同层次的 DAG，名字都叫「DAG/顺序」，
但来源、粒度、用途完全不同。

| | DAG-A 流程 DAG | DAG-B 模块依赖 DAG | DAG-C rubric 树 |
|---|---|---|---|
| 定义处 | `sciforge/repro/phasegraph.json` | `reprospec/compiler.py` + `lifecycle.py` | `reprospec/rubric_tree.py` |
| 节点 | 7 个阶段 R0–R6 | 14 个 `AlgorithmModule` | 根 / 分支 / 74 条 SAU 叶 |
| 边 | `next` 顺序 | `inputs/outputs` 交集 | `parent_id` / `HAS_SAU` |
| 用途 | 决定「先做哪一步」 | 决定「代码按什么顺序生成/执行」 | 决定「逐条怎么打分」 |
| 产物 | `REPRO_PLAN.json` | `CODE_PLAN.json` / `REPRO_SPEC.code_plan` | `RUBRIC_TREE.json` |

**用户问的「论文分解」主要指 DAG-B**，下面把它逐步拆开。

### 2.1 DAG-A：流程 DAG（先看全貌）

`phasegraph.json` 是**固定 7 步**，每篇论文都一样，不是按论文内容分解出来的：

```
R0 intake-paper → R1 resolve-method → R2 ground-code → R3 bind-data
  → R4 fix-metrics → R5 execute → R6 verify-and-replay
```

每阶段有自己的 `reads`（读哪些语义层/应用层元素）、`produces`（产物文件）、
`gate`（门函数）。这是**流程骨架**，不是论文的 DAG。

### 2.2 DAG-B：模块依赖 DAG（论文专属，重点）

**输入**：语义层里这篇论文的 10~14 个 `AlgorithmModule`，每个带 `inputs` / `outputs`。

**Step 1 — 找出依赖边**（`compiler.py` 457–468 行）：

```python
observed = []
for i, before in enumerate(modules):
    outs = set(before.attrs["outputs"])
    for j, after in enumerate(modules):
        if i == j: continue
        ins = set(after.attrs["inputs"])
        if outs & ins:                 # 词元交集 = 数据流依赖
            observed.append((before, after))
```

即：**A 的输出词元出现在 B 的输入里 → A 必须在 B 之前**。
例如 `Fragment Starter.outputs=['fragment_graph']`，
`Geometry-Biased Attention.inputs=['fragment_graph', ...]` → 前者先于后者。

**Step 2 — 压缩直接前驱**（避免 O(n²) 爆炸）：

14 个模块两两比对曾产生 44 条候选边；代码对每个 `after` **只保留最靠近的一个
直接前驱**（`last[a] = (b,a)`），其余前驱存进 `s.check["all_predecessors"]` 备查。

**Step 3 — 检测环**（`_find_cycle_edges`）：

真实论文里同一个词元（如 `'潜在向量 z'`）可能被多个模块复用，形成双向依赖。
命中的边标 `check["cycle"]=True`、`required=False`、`provenance="inferred"`，
并写 `warnings`，**不硬造顺序**。

**Step 4 — 生成 `ordering` SAU 与 `code_plan.order`**：

```python
order = [s.check["before"] for s in spec.by_kind("ordering") if before]
order = list(dict.fromkeys(order + [m for m in modules if m not in order]))
spec.code_plan = {"strategy": ..., "modules": modules,
                  "functions": [...], "order": order, ...}
```

即 `order` = 所有 `before` 去重 + 补齐没出现在边里的模块。

**Step 5 — 生命周期层再做一次 Kahn 拓扑排序**（`lifecycle.py::run_codegen`）：

```python
for s in spec.by_kind("ordering"):
    edges.append((s.check["before"], s.check["after"]))
order, cycle = _topo(edges, nodes)
# 有环时按 (入度, id) 稳定排序兜底，记 warnings 而不阻断
for i, mid in enumerate(order):
    tasks.append({"task_id": f"cgt:{i:03d}", "module_id": mid,
                  "order": i+1, "depends_on": [...],
                  "strategy": "existing" if 有 code_grounding 覆盖 else "generate",
                  "status": ...})
```

### 2.3 MolMiner 的真实 DAG 产物

```
CODE_PLAN.json
  dag.nodes   14 个模块
  dag.edges   3 条：
      graph_encoder           → autoregressive_decoder
      hierarchical_decoder    → graph_encoder
      graph_encoder           → hierarchical_decoder
  dag.cycle   ['autoregressive_decoder', 'graph_encoder', 'hierarchical_decoder']
              （这 3 个是跨论文共享模块 2608.06956，双向声明成环）
  dag.order   14（环降级：按 (入度,id) 稳定排序，不阻断）
  tasks       14 个，其中 10 个 strategy=existing（有 CodeFunction 锚），4 个 generate

REPRO_SPEC.code_plan
  modules 14 · functions 19 · order 14
  order 前 5：graph_encoder → hierarchical_decoder
              → symmetry_aware_attachment_standardization
              → geometry_biased_attention → fragment_starter
  另有 data_contract 6 条、metric_plan 8 个
```

**两套 order 为什么不同**：`code_plan.order` 来自编译器「依赖边 + 声明顺序补齐」；
`CODE_PLAN.dag.order` 来自生命周期的 Kahn 拓扑 + 环降级稳定排序。
两者都自洽，但**判定 ordering SAU 时用的是 `code_plan.order`**（`verdict.py`），
`CODE_PLAN` 的 order 用于任务编排。这个分工要记牢，否则会以为数据不一致。

### 2.4 DAG-C：rubric 树（打分用，不是执行顺序）

```
paper:2411.06608                                    根
├─ algorithm:molminer ─ 10 个模块分支             L1/L2
│    └─ 74 条 SAU 叶（method/ordering/code_grounding）
└─ benchmark:zinc 等 6 个基准                     L1
     └─ 31 条 numeric SAU + 6 条 protocol SAU     L2 叶
```

`rubric_tree.py` 按 SAU 的 `source_node_ids` 末位类型反查父节点
（模块 → Algorithm，applb/appmetric → Benchmark），
得到深度 3 的树；`rubric_runtime.py` 再把它写成 `RubricNode` + `HAS_SAU` 进运行时图。

## 3. 每个过程怎么用应用层

### 3.1 先说一个关键点

> **DAG 的边不来自应用层，来自语义层。**
> 模块依赖边由 `AlgorithmModule.inputs/outputs` 交集算出，谱系边来自语义层 `SUBCLASS_OF`。
> 应用层提供的是**叶子事实**（数值、指标定义、数据契约、证据、局限、出处），
> 用于给 DAG 的每个节点「填内容」和「打判定」，不决定 DAG 的形状。

三层分工：

```
语义层   → 骨架（有哪些算法/模块/基准、谁连谁、模块输入输出）
应用层   → 可评分的叶子事实（一行数值、一个指标、一份契约、一条证据）
运行时层 → 这次 run 的状态（锁、任务、执行日志、锚、rubric 节点）
```

### 3.2 R0–R6 逐步对照（读什么 / 从哪张图读）

| 阶段 | `phasegraph.reads` | 实际取的应用层对象 | 产出 |
|---|---|---|---|
| R0 | `Paper.research_question/domain/flow_family/problem_category` | 语义层 Paper 属性（应用层不用） | REPRO_SPEC 门 |
| R1 | `PROPOSES_METHOD` `HAS_MODULE` `SUBCLASS_OF` `RELATED_TO` `Algorithm.mechanism` | 语义层关系 + **`appsrc:*`**（SourcePaper，科技树出处） | METHOD_CARD / LINEAGE |
| R2 | `HAS_CODE` `HAS_FUNCTION` `MODULE_IMPLEMENTED_BY` `BELONGS_TO_MODULE` `CodeRepository` `CodeFunction` | **纯语义层**：代码仓库、函数、模块实现边；不读应用节点 | CODE_PLAN / STATIC_CHECKS |
| R3 | `EVALUATED_ON` `HAS_CONTRACT` `Benchmark.input/output_form/n_samples` | **`appcontract:*`（DataContract）** 是这里的主输入 | DATA_PLAN / SHAPE_PROBE |
| R4 | `HAS_METRIC` `HAS_ENTRY` `USES_METRIC` `SUPPORTED_BY` `Benchmark.metrics` `MetricDefinition.direction` | **`appmetric:*`** 给方向/单位，**`applb:*`** 给数值行，**`appev:*`** 给出处 | METRIC_PLAN / SOTA_BASELINE / ALIGN_RUBRIC |
| R5 | `CODE_PLAN.json` `DATA_PLAN.json` `METRIC_PLAN.json` `REPRO_SPEC.json` | 前几步落盘的计划文件（不直接读图） | raw_results / RUNSTATE |
| R6 | `raw_results.json` `SOTA_BASELINE.json` `REPRO_SPEC.json` | **`appev:*`** 作为判定证据；结果写回 `EvaluationResult` / `ClaimAnchor`（运行时层） | REPRO_REPORT / SAU_VERDICTS |

### 3.3 四环节（lifecycle）用的具体节点

| 环节 | 读的应用层节点 | 怎么用的 | 落地产物 |
|---|---|---|---|
| `lock` | **不读应用节点** | 只用 `ReproSpec` 里 method SAU 的 `stable_key()` 算逐条指纹；方法边来自语义层 `HAS_MODULE` | `METHOD_LOCK.json` |
| `codegen` | `appev:*` 间接（通过 `code_grounding` SAU 的 `source_node_ids` 里 CodeFunction） | 校验「应用声明的实现符号」在语义层图里是否真有 CodeFunction 节点（`symbol_recall`）；`ordering` SAU 建 DAG | `CODE_PLAN.json` + `REPRO_SCRIPT.py` |
| `execute` | `spec.data_contract`（源自 **`appcontract:*`**）按 benchmark id 索引 | `_fixture_from_graph()` 从**语义层** `Benchmark.model_results[]` 取 `{model,metric,value,unit,is_sota,paper_id}` 内嵌为 FIXTURE；应用层只提供「取哪个基准、什么输入输出形式」，**数值本身不是应用节点** | `EXECUTION_LOG.json` |
| `anchor` | **`applb:*` → `appev:*` → `appmetric:*`** 全链 | 每条 numeric SAU 组三级链：L1=claim、L2=`appev.source`(`table_extract:N`)、L3=benchmark+entry+metric id，再挂 4 个 hash | `CLAIM_ANCHORS.json` |

**「不读应用层期望值」是硬约束**：`check_script_safety` 检查脚本没有
`from capfactory` / 网络访问；FIXTURE 的数值取自语义层 `Benchmark.model_results[]`
（来自论文表格原文），而 `SOTA_BASELINE` 这类应用层派生结论绝不进脚本。
这样重算出来的值才能与论文值做真比对，而不是自我印证。

### 3.4 一条真实链路（ZINC 上的 uniqueness = 99.6）

```
语义层  benchmark:zinc
         attrs.model_results[0] = {model:GDSS, metric:uniqueness,
                                   value:"99.6", paper_id:paper:2411.06608}
   │ ① 挖掘器 leaderboard（R4 前）
   ▼
应用层  applb:benchmark_zinc:0  ──HAS_ENTRY──  benchmark:zinc
        ├─USES_METRIC→ appmetric:uniqueness {direction:max, unit:""}
        └─SUPPORTED_BY→ appev:benchmark_zinc:0
                          {quote:"GDSS uniqueness=99.6", source:table_extract:1}
   │ ② 编译器 _sau_numeric（R0）
   ▼
规格层  sau:241106608:numeric:000
        check = {op:numeric_compare, target:applb:benchmark_zinc:0,
                 metric:uniqueness, value:"99.6", value_num:99.6,
                 direction:max, tolerance:0.05}
        source_node_ids = [benchmark:zinc, applb:benchmark_zinc:0,
                           appmetric:uniqueness]
   │ ③ 执行（R5 / lifecycle.execute）
   ▼
脚本    data_contract 指到 benchmark:zinc → 取语义层 model_results
        FIXTURE 内嵌 24 行 → 归一 → 重算 SOTA(benchmark:zinc)
        → symbol_trace 14 个模块
   │ ④ 判定 + 锚定（R6 / lifecycle.anchor）
   ▼
产物    SAU_VERDICTS: sau:...:numeric:000 → aligned
        CLAIM_ANCHORS: C001 = {
          L1: {model:GDSS, metric:uniqueness, value:99.6},
          L2: {entry_id:applb:benchmark_zinc:0, table_ref:table_extract:1},
          L3: {benchmark_id:benchmark:zinc, entry_id:..., metric_id:...},
          hashes: {spec, code, inputs, outputs}, verified:true}
        RUBRIC_TREE: 该 SAU 挂在 paper:2411.06608/benchmark:zinc 分支下
```

这条链把「语义层的一个数组元素」→「应用层节点」→「SAU」→「执行」→「判定」
→「可验证的锚」完整串起来，也是整个架构的最小闭环。

### 3.5 两种任务在同一套 DAG 上的差别

| | reproduction | generation |
|---|---|---|
| 应用层读什么 | `applb` `appmetric` `appcontract` `appev` `applim` `appsrc` | `appq` `appcat` + 共享 5 类 |
| DAG 用在哪 | 编译 SAU → 代码生成 → 执行 → 数值判定 | **不跑执行 DAG**（只做研究问题聚类、章节素材） |
| 是否产 `REPRO_SCRIPT.py` | ✅ | ❌ |

即：**同一个语义层、同一套 DAG 骨架，两种任务只是「取哪些应用节点」不同**；
复现任务会用全部叶子去跑判定，生成任务只用问题/类别/证据/局限去组织叙述。

## 4. 一句话总结

```
语义层 = 事实与骨架（谁提出什么、由什么模块组成、在什么基准上、数值是多少）
  ↓ 挖掘器把数组/字符串字段提升为节点
应用层 = 按任务筛出的可查询/可评分叶子（复现取榜单与契约，生成取问题与类别）
  ↓ 编译器把骨架 + 叶子编译成 SAU 与模块依赖 DAG
规格层 = ReproSpec（71 条 SAU + code_plan.order）
  ↓ R0–R6 / 四环节执行与判定
运行时层 = 锁、任务、执行日志、锚、rubric 节点（单篇）
```

**DAG 的形状由语义层决定；DAG 每一步的判断依据由应用层提供；
这次跑得怎么样由运行时层记录。**
