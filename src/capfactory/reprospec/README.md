# reprospec/ — 复现规格工作目录（P0-1 + P0-2）

> 新建于 2026-11-14。设计依据：`capfactory/md/REPRODUCTION_APPLICATION_BLUEPRINT.md` §3–§5。
> 本文是后续智能体接手 P0-3 起的实现基线。

## 1. 这个目录解决什么

`capfactory/sciforge/repro/` 已有 R0–R6 执行骨架（DAG、门、events 重放），但缺一层
「**可验证规格**」：R6 只有 `Perf Gap` 一个数，无法检测 SA-Bench 所说的
`semantic drift`（代码能跑但实现与论文不符）。

本目录补上规格层：

```
语义层（只读，6001/7460）
  → build_task_layer("reproduction")          已有
应用层 app_reproduction.json (8300/10260)
  → compile_reprospec()                       ★ 本目录
ReproSpec（5 类 SAU 的可验证规格树）
  → R0–R6 消费（sciforge/repro/）             宿主，本目录不改其执行逻辑
```

分工必须清楚：

| 目录 | 职责 | 是否运行时状态 |
|---|---|---|
| `capfactory/reprospec/` | 关系真相源、SAU/ReproSpec 契约、确定性编译 | 否 |
| `capfactory/sciforge/repro/` | R0–R6 DAG、门、执行、事件重放 | 是 |

## 2. 文件清单

| 文件 | 行数级 | 职责 |
|---|---|---|
| `__init__.py` | 55 | 统一导出（P0-1~P0-4） |
| `relations.py` | 230 | **P0-1**：9 语义 + 9 应用 + 4 复现运行时关系、12 条历史别名、6 条派生链、`validate_phasegraph()`、`check_against_tbox()` |
| `contract.py` | 132 | **P0-2**：`SAU` / `ReproSpec` dataclass、`spec_hash`、save/load |
| `compiler.py` | 594 | **P0-2**：`compile_reprospec()`，五类 SAU 编译、环检测、MethodLock |
| `application.py` | 265 | **P0-3**：8 类复现运行时应用节点、4 条关系的 domain/range 判定、独立运行时图构建 |
| `verdict.py` | 265 | **P0-4**：逐 SAU 静态判定、`SAUReport`、辅助语义门 |
| `README.md` | 本文 | 使用与实现说明 |

配套改动（不在本目录内）：

| 文件 | 改动 |
|---|---|
| `capfactory/sciforge/repro/phasegraph.json` | **P0-1**：`schema_version` 1.1、R2 关系名统一、R1/R3/R4 补关系、R0 字段改 v4 规范名；**P0-4**：R6 `produces` 增加 `SAU_VERDICTS.json` / `app_repro_runtime.json`，新增 `auxiliary` 段声明「不参与门」 |
| `capfactory/sciforge/repro/planner.py` | 关系比较走 `resolve_relation()`；`relation_index` 链显式登记；Paper 属性加规范名 fallback。**输出结构不变** |
| `capfactory/sciforge/repro/runner.py` | **P0-4**：R6 后追加 `_auxiliary_evidence()`，写 SAU 判定与运行时图；主门链不变，dry 仍 BLOCKED |
| `capfactory/applayer/tasks.py` | **P0-3**：reproduction TaskSpec 声明 8 运行时类 / 4 运行时关系 / `runtime_extends`；挖掘器不变 |
| `tests/Phase/test_reprospec.py` | **P0-1/P0-2** 28 项 |
| `tests/Phase/test_repro_p03_p04.py` | **P0-3/P0-4** 22 项 |

## 3. P0-1：关系名统一

### 问题（实测 2026-11-14）

三套口径并存：

```
phasegraph.json R2 reads : REALIZED_BY / IMPLEMENTS_MODULE   ← 语义层不存在
semantic/tbox_v4.py:91   : MODULE_IMPLEMENTED_BY / HAS_MODULE / HAS_FUNCTION
planner.py:63            : relation_index.json 的 algorithm_code / data_paper 派生链
```

### 约定

1. **TBox 关系** = 图上真实存在的边，只能用 `SEMANTIC_RELATIONS`(9) 或 `APP_RELATIONS`(9) 的规范名
2. **派生链** = `relation_index[...]` 预计算多跳路径，登记在 `RELATION_INDEX_CHAINS`，**不是关系**
3. **历史别名** = `LEGACY_ALIASES` 只用于「解析读取方声明」，绝不回写图
4. 字段名别名（`Paper.research_problem` → `Paper.research_question`）单列，不改任何既有读取行为

```python
from capfactory.reprospec.relations import (
    resolve_relation, canonicalize_reads, validate_phasegraph,
    check_against_tbox)

resolve_relation("REALIZED_BY")          # 'MODULE_IMPLEMENTED_BY'
check_against_tbox()                     # [] 表示与 tbox_v4 / applayer.tbox 一致
validate_phasegraph(pg)                  # [] 表示 phasegraph.reads 全部可解释
```

`validate_phasegraph` 能抓三类错误：历史别名、未知关系、未知节点类型；对
`*.json` / `relation_index[...]` / `kg.result` / 节点类型名放行。

## 4. P0-2：ReproSpec 编译

### 用法

```python
from capfactory.reprospec import compile_reprospec

spec = compile_reprospec(arxiv_id="2411.06608")
spec.counts()        # {'method':14,'code_grounding':17,'protocol':6,
                     #  'numeric':31,'ordering':3}
len(spec.sau)        # 71
spec.spec_hash       # 'sha256:0f1f79f2...'
spec.save("storage_cf/repro_runs/2411.06608")

# 传自己的图（避免重复加载 15MB）
from capfactory.po import POGraph
g = POGraph.load("storage_cf/sciforge/app_reproduction.json")
spec = compile_reprospec(g, paper_id="paper:2411.06608")
```

`out_dir` 给出时写 `REPRO_SPEC.json` + `SAU_LIST.json`；`ReproSpec.load()` 可逆。

### 五类 SAU 与节点来源

| kind | 编译自 | `check.op` | required |
|---|---|---|---|
| `method` | `PROPOSES_METHOD`→`Algorithm`→`HAS_MODULE`→`AlgorithmModule` | `module_implemented` | True |
| `code_grounding` | `MODULE_IMPLEMENTED_BY` + 反向 `BELONGS_TO_MODULE` → `CodeFunction` | `symbol_exists` | True |
| `protocol` | `EVALUATED_ON`→`Benchmark`→`HAS_CONTRACT`→`DataContract` | `data_contract` | `is_evaluation` |
| `numeric` | `HAS_ENTRY`→`LeaderboardEntry`→`USES_METRIC`→`MetricDefinition` | `numeric_compare` | `is_sota/is_ours` |
| `ordering` | `AlgorithmModule.inputs/outputs` 依赖闭包 | `ordering` / `declared_order` | True（环降级时 False） |

每条 SAU 都带 `source_node_ids`（可回溯到图节点）与 `evidence_ids`。

### 编译期硬约束

- **只读图、不写图**（`test_compile_is_read_only`）
- **零 LLM**：`provenance ∈ {extracted, derived, inferred}`，`inferred` 仅允许出现在顺序降级场景
- **不编造数值/符号/shape**：`protocol.check.shape_probe` 恒为 `None`，留给 R3.5 实测
- **幂等**：同一输入 `spec_hash` 恒定（稳定字段 = id/kind/statement/source_node_ids/check/required）
- 无事实记 `gaps`/`warnings`，绝不补默认值

### 三处真实数据缺陷的修复（实现时踩到，已固化为测试）

1. `inputs/outputs` 有时是**字符串** `"分子片段"`；直接 `set(map(str, ...))` 会拆成
   `['分','子']` 并产生虚假顺序约束。→ `_as_list()` 按分隔符切词，字符串整体作词元。
2. O(n²) 依赖闭包在 14 模块上产生 **44 条** ordering SAU。→ 每个 `after` 只保留
   最近的一个直接前驱（3 条），其余记入 `check.all_predecessors`。
3. 剩余 3 条里 `Graph Encoder ↔ Hierarchical Decoder` 构成**环**（图里同名数据流）。
   → `_find_cycle_edges()` DFS 检测，环内 SAU 降 `required=False` / `provenance=inferred`
   并写 warning，避免 R6 拿矛盾门。

## 5. 真实黄金用例：MolMiner `2411.06608`

图：`storage_cf/sciforge/app_reproduction.json`（8300 节点 / 10260 断言）。

| 项 | 实测值 |
|---|---|
| `Paper --PROPOSES_METHOD-->` | 4 个 Algorithm |
| `HAS_MODULE` | 14 个 AlgorithmModule |
| `MODULE_IMPLEMENTED_BY` + 反向 | 17 个 CodeFunction |
| `EVALUATED_ON` | 6 个 Benchmark |
| `HAS_ENTRY` | 31 条榜单行 |
| **SAU 总数** | **71**（method 14 / code 17 / protocol 6 / numeric 31 / ordering 3） |
| **required** | **48**（2 条环降级） |
| `code_plan` | `strategy=audit_repo`，1 仓库 / 19 函数 / 14 模块 |
| `lineage` | 3 条（JTNN / G-SchNet / HierVAE） |
| `metric_plan` | 8 个指标 |
| `spec_hash` | `sha256:0f1f79f23800ac4e5098d5162ed0760b04cdb00eda6b21380a938250e3aef805` |
| `gaps` | `[]` |
| `warnings` | `['ordering 存在 2 条环依赖，已降级为 required=False']` |

样例 SAU（真实输出）：

```json
{
  "id": "sau:241106608:method:000",
  "kind": "method",
  "statement": "MolMiner 的模块「Symmetry-Aware Attachment Standardization」实现 encoding（inputs=['fragment_graph'] → outputs=['canonical_attachments']）",
  "source_node_ids": ["algorithm:molminer", "algorithmmodule:..."],
  "check": {"op": "module_implemented", "mechanism": "encoding",
            "inputs": ["fragment_graph"], "outputs": ["canonical_attachments"],
            "formula": ""},
  "required": true, "provenance": "derived",
  "relation_hint": "PROPOSES_METHOD|HAS_MODULE"
}
```

数值 SAU 的方向归一：`higher` → `max`，同时保留 `direction_raw` 与
`value_num`（`float`），`tolerance=0.05` 对齐 `gates.reproduction_close`。

## 6. 与 R0–R6 的接入点（本目录**未**改动执行器）

| 阶段 | 应消费的 ReproSpec 字段 | 状态 |
|---|---|---|
| R0 | 写 `REPRO_SPEC.json` / `SAU_LIST.json`；门增 `sau_count(method,numeric)>0` | 已在 phasegraph.produces 声明，执行器待接 |
| R1 | `method_lock` 冻结；`lineage` 喂 Paper Lineage | 待接 |
| R2 | `code_plan.strategy` 决定 audit_repo vs generate_from_plan | 待接 |
| R3 | `data_contract`；`protocol.check.shape_probe` 由 R3.5 填实测 | 待接 |
| R4 | `metric_plan`（direction/direction_source/sota） | 待接 |
| R5 | `budgets`（debug_tries=20 / engineer_rounds=2 / tolerance=0.05） | 待接 |
| R6 | 逐 SAU 判四类 drift → `SAU_VERDICTS.json`；`spec_hash` 进 ClaimAnchor | 待接 |

**重要**：R5 目前仍是 `dry` 不执行、R6 无实跑值诚实 BLOCKED（`runner.py:44-46`）。
本目录只提供规格，**不改变这一诚实行为**。

## 7. 验证

```bash
cd /home/zengshuxin/xKG-main/xKG-main

# P0-1/P0-2 28 项 + P0-3/P0-4 22 项
PYTHONPATH=. python3 tests/Phase/test_reprospec.py
PYTHONPATH=. python3 tests/Phase/test_repro_p03_p04.py

# Phase 目录全量（131 项）
PYTHONPATH=. python3 -m unittest discover -s tests/Phase -p "test_*.py"

# 全仓回归（798 项）
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py"

# 冒烟（60/60）
PYTHONPATH=. python3 deploy/smoke_test.py
```

## 8. 后续（见蓝图 §9.2）

| 优先级 | 任务 | 状态 |
|---|---|---|
| P0-1 | 关系名统一 | ✅ 完成 |
| P0-2 | ReproSpec / SAU 编译 | ✅ 完成 |
| P0-3 | 8 类运行时应用节点 + 4 条应用关系 | ✅ 完成（7 升级 + 1 新增） |
| P0-4 | R6 逐 SAU 静态判定（dry 可用） | ✅ 完成 |
| P1-5 | R5 `lite` 真跑 + EDIT 循环 + events | ✅ `executor.py` |
| P1-6 | S2 ladder（subset → 3 态 Critic → full 严格优于） | ✅ `ladder.py` |
| P1-7 | lineage + shape probe | ✅ `probe.py` |
| P2-8 | 混合级 Align-Score + 三哈希 ClaimAnchor + `REPRO_SCRIPT.py` | ✅ `scoring.py` |
| P2-9 | `sau_drift_acceptable()` 接进 R6 门 + CLI 报告 | ✅ `runner.py` / `cli.py` |
| P3-1 | 范围归一化 + 证据化补边（不是盲目补 4 条） | ✅ `normalize.py` |
| P3-2 | 真实 mini-batch shape 实测 | ✅ `minibatch.py` |
| P3-3 | lineage 逐字证据分级 | ✅ `probe.py` |
| P3-4 | 多篇回归（4 篇） | ✅ `cli.py --batch` |
| P4 | 原论文模型训练复现（环境 / 数据 / 配置 / 执行器） | ⬜ 设计见 `md/FULL_TRAIN_REPRODUCTION_DESIGN.md` |

实测结果：`md/REPRODUCTION_VALIDATION_REPORT.md`（`--scope strict --effort lite`：
门链 `overall=PASS`、`FINAL_EVALUATION=PASS`、SAU_score 1.0、coverage 1.0、
drift_rate 0、双跑一致）；多篇回归见 `md/REPRODUCTION_REGRESSION_REPORT.md`。

## 9. 不要做的事

- 不要把 SAU 写进语义层（它是任务派生的判定单元）
- 不要用 LLM 生成 SAU 集合（会破坏 `spec_hash` 稳定性）
- 不要改 `sciforge/repro/runner.py` 的 dry 行为来「让测试变绿」
- 不要新增语义层类/关系（复现是应用任务，走 `build_task_layer`）
- 不要在 `check` 里填未经实测的 shape / value / 符号
- 不要把 8 运行时类写进 `app_reproduction.json`（只能进独立运行时图）
- 不要让 `DEVIATES_FROM` 在 dry 出现（无实跑值就不存在偏离）

## 10. P0-3 / P0-4 实现记录

### 10.1 P0-3 的升级策略：为什么不改 `applayer/tbox.py`

`tests/test_layered_tbox.py:107-108` 锁定应用层基础契约 **8 类 / 9 关系**，
`tests/Phase/test_graph_slice.py:248` 与 `test_layered_tbox.py:178-179` 锁定
legacy **46 类 / 105 关系**。直接往这两处塞新类会让 798 项回归退化。

因此采用「**扩展声明 + 独立运行时图**」：

- 8 类定义在 `application.py:REPRO_APP_CLASSES`，4 条关系定义在
  `relations.py:REPRO_APP_RELATIONS`；`ALL_CANONICAL` 变为 **22**。
- `applayer/tasks.py` 的 reproduction spec 声明允许这 8 类/4 关系 +
  `runtime_extends`，但**挖掘器不产生它们**，`app_reproduction.json` 不变。
- `materialize_runtime_nodes()` 只写 `<out_dir>/app_repro_runtime.json`，
  每个节点带 `layer=application / task=reproduction / derived_from /
  miner=repro_runtime / run_id`。
- 有效复现契约 = **16 类 / 13 关系**，基础 8/9 保持不变。

**诚实标注**：`reserved_status()` 实测只有 **7 类**在 legacy reserved 中；
`EvaluationResult` 不在（reserved 里是 `EvaluationRun` / `ReviewVerdict`），
它是 SA-Bench 逐 SAU 判定所需的**应用层新增类**，单独列在
`not_in_reserved` / `declared_new`，不伪装成升级。

4 条新关系：`VERIFIES`（EvaluationResult→图节点）、`DEVIATES_FROM`
（有实跑值才出现）、`LINEAGE_OF`（SourcePaper→Paper）、`GENERATED_BY`
（CodeGenerationTask→AlgorithmModule）。`validate_repro_edge()` 做应用层
自己的 domain/range 判定，不依赖 legacy TBox。

### 10.2 P0-4 的判定规则（dry 可用）

`verdict.py:evaluate_sau()` 五类规则见文件头表格。核心是：
**需要执行才能判的一律 `unverified`，不计入 `sau_score` 分子，也不伪装成通过**。

MolMiner 实测（71 条 SAU）：

| kind | 判定 |
|---|---|
| method | aligned 10 / **mismatch 4**（模块无代码落地边，真实信号） |
| code_grounding | aligned 17 |
| protocol | aligned 6（标 `execution_unverified=True`） |
| numeric | **unverified 31**（dry 无实跑值） |
| ordering | aligned 1 / unverified 2（环降级） |

`n_decidable=38`、`sau_score=0.8947`、`coverage=0.5352`、
`drift_rate=0.1053`、`by_drift.methodological=4`。

### 10.3 runner 接入方式（关键：不改变门）

`runner.py:_auxiliary_evidence()` 在 7 阶段门链**跑完之后**调用
`compile_reprospec → evaluate_sau → materialize_runtime_nodes`，写两个文件：
`SAU_VERDICTS.json` 与 `app_repro_runtime.json`，并把摘要塞进
`rep["sau"]` 与 `REPRO_REPORT.md` 的一行。

- `verdicts["R6"]` 仍由 `gates.reproduction_close(results)` 决定，
  **dry 下保持 BLOCKED**（`tests/test_p1_repro.py:150` 锁定）
- `sau_drift_acceptable()` 已实现但**未接进门**，留到 P2-9
- 辅助层用 `try/except` 包住，异常写 `sau.available=false`，不中断主门链

`phasegraph.json` R6 的 `auxiliary.note` 明确写着「不参与 reproduction_close 门」。

## 11. P3 / full 实现记录（2026-11-14 续）

### 11.1 新增文件

| 文件 | 职责 |
|---|---|
| `normalize.py` | **P3-1** `normalize_for_repro()`：只读源图，返回内存归一化视图 + `NormalizationResult` 审计；`grounding_snapshot()` 只读诊断 |
| `minibatch.py` | **P3-2** `write_runtime_probe()`：生成纯 stdlib 脚本，隔离子进程**实际构造** mini-batch 并测量 shape/dtype；`resolve_forms()` 表单同族继承 |
| `probe.py`（追加） | **P3-3** `lineage_evidence()` / `write_lineage_evidence()`：区分 verbatim_quote / bibliographic / none |
| `train.py` | **full** `probe_environment()` / `build_train_plan()` / `write_train_feasibility()`：只探测与规划，不执行训练 |
| `verdict.py`（改） | `declared_order` 从 `unverified` 改为可静态验证的 `aligned`，但强制带 `declaration_only=True` / `execution_unverified=True` |
| `cli.py`（改） | `--scope strict\|legacy`、`--train-plan`、`--data-root`；主流程、规格编译、双跑共用同一归一化视图 |
| `runner.py`（改） | R6 辅助产物增加 `MINIBATCH_PROBE.json` / `LINEAGE_EVIDENCE.json`，独立 `try` 隔离 |
| `tests/Phase/test_repro_p3.py` | 20 项 P3 测试 |

### 11.2 为什么「补 4 条边」改成了「范围归一化」

实测 4 条 `method mismatch` 里，`identity_pullback` 的 id 前缀是 `2608.06956`
（**另一篇论文**）；同批混入的 `graph_encoder ↔ hierarchical_decoder`
正是 2 条 ordering 环的来源。给它们补 `MODULE_IMPLEMENTED_BY` 会伪造跨论文事实。

所以 `normalize_for_repro()` 做三件事，且**源图文件一个字节都不改**：

1. 删除「本篇 Algorithm `--HAS_MODULE-->` 其它论文模块」的边（4 条）；
2. 删除归一化后**没有任何本篇模块**的基线算法 `--PROPOSES_METHOD-->` 边（3 条，
   否则 R1 门会因 `JTNN/MoLeR 缺机理` 判 PARTIAL）；
3. 对仍缺落地边的本篇模块，只在本篇 `CodeRepository` 前缀下的 `CodeFunction`
   中按 `name + purpose` 关键词命中建边（6 条），每条带 `matched_terms /
   evidence_purpose / grounding_rule`，`attribution=analyst_inference`。

`--scope legacy` 可跑未归一化对照：仍是 71 条 SAU / `drift_rate=0.058` / PARTIAL。

### 11.3 CLI 用法

```bash
cd /home/zengshuxin/xKG-main/xKG-main

# 单篇：strict + 训练可行性
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
  --arxiv 2411.06608 --effort lite --scope strict \
  --out storage_cf/repro_runs \
  --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md --train-plan

# 多篇回归（有仓库 / 无仓库 / 表格规模差异）
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
  --batch 2411.06608,2405.03370,2302.09048,2611.06237 \
  --effort lite --out storage_cf/repro_runs/regression \
  --report-md capfactory/md/REPRODUCTION_REGRESSION_REPORT.md
```

### 11.4 run 目录新增产物

`NORMALIZATION.json`（全部增删改与证据）、`MINIBATCH_SCRIPT.py`、
`OBSERVED_SHAPES.json`、`MINIBATCH_PROBE.json`、`LINEAGE_EVIDENCE.json`、
`TRAIN_FEASIBILITY.json`、`TRAIN_PLAN.json`。

### 11.5 不要做的事（补充）

- 不要为了 PASS 给跨论文模块补边；先做 scope 隔离，再谈落地证据
- 不要把 `SourcePaper.title` 当 `Evidence.quote`（书目证据 ≠ 逐字引文）
- 不要把同族继承来的 form 标成论文原文声明（`paper_declared=False`）
- 不要为了消除 `unknown_forms` 编造 shape；无法构造就如实保留
- 不要在 `TRAIN_FEASIBILITY.executable=false` 时启动 `full` 训练
- 不要原地改 `anaconda3` 的 torch（798 项回归依赖它），必须隔离环境
