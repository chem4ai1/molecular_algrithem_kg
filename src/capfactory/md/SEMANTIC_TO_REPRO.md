# 语义层驱动的代码复现：完整梳理

> 回答一个问题：**现有的语义层（6 类节点 / 9 条关系）是怎么变成一次可验证的代码复现的？**
> 相关实现：`reprospec/{compiler,contract,verdict,scoring,lifecycle}.py`、
> `sciforge/repro/{phasegraph.json,planner,runner,gates}.py`。

## 1. 一句话总览

```
语义层（6001 节点 / 7460 断言）
  └─ 确定性编译 → ReproSpec（5 类 SAU，共 71 条 / MolMiner）
       └─ R0–R6 门控 → REPRO_SCRIPT.py（纯 stdlib、自包含）
            └─ 执行 + 逐 SAU 判定 → SAU_VERDICTS / FINAL_EVALUATION
                 └─ 三级锚定 → CLAIM_ANCHORS（claim → 表格单元格 → 图节点）
```

**全程零 LLM**：语义层是唯一事实源，复现只做「编译 + 执行 + 判定」，
每一步都能回溯到节点 id 与表格单元格。

## 2. 语义层提供了什么

| 层 | 内容 | 在复现中的角色 |
|---|---|---|
| 6 类节点 | Paper / Algorithm / AlgorithmModule / CodeRepository / CodeFunction / Benchmark | 复现的**骨架**：方法、模块、实现、数据 |
| 9 条关系 | `PROPOSES_METHOD` / `HAS_MODULE` / `MODULE_IMPLEMENTED_BY` / `HAS_FUNCTION` / `EVALUATED_ON` / `HAS_CODE` / `RELATED_TO` / `SUBCLASS_OF` / `BELONGS_TO_MODULE` | 编译 SAU 的**依据**（也是判定时查证据的路径） |
| 属性 | `Benchmark.model_results[]` / `metrics[]` / `input_form` / `Algorithm.limitations` / `AlgorithmModule.inputs,outputs` | 数值、指标方向、数据契约、模块依赖 |

关键设计：语义层**不存**「这次复现该怎么跑」，只存客观事实；
**怎么跑**由 `compiler.py` 从事实推导。

## 3. 编译：5 类 SAU（Semantic Alignment Unit）

`compile_reprospec(paper_id)` 把图编译成「原子且可验证的实现声明」，共 5 类：

| SAU | 来源节点/关系 | 判据（check 主要内容） | MolMiner 条数 |
|---|---|---|---|
| `method` | `Algorithm` + `HAS_MODULE` → `AlgorithmModule` | `target`(模块 id) + `mechanism` + `inputs/outputs` | 14 |
| `code_grounding` | `MODULE_IMPLEMENTED_BY` → `CodeFunction` | `target`(函数 id) + `signature/file/lineno` + `stub_allowed=false` | 17 |
| `protocol` | `Benchmark` + `DataContract` | `input_form` / `output_form` / 规模 | 6 |
| `numeric` | `LeaderboardEntry` + `MetricDefinition` | `metric/value/value_num/unit/direction/tolerance` | 31 |
| `ordering` | `AlgorithmModule.inputs/outputs` 依赖闭包（不足时降级为 `declared_order`） | `before/after` 或 `cycle` | 3 |

### 3.1 为什么是这 5 类

它们正好覆盖代码复现的五条**独立可验证轴**：

```
方法说得对不对 (method) → 有没有真实现 (code_grounding)
 → 数据契约对不对 (protocol) → 数值对不对 (numeric) → 模块顺序对不对 (ordering)
```

少一类就会漏掉一种失败模式：只查数值会放过「方法描述与代码不符」，
只查代码会放过「跑出来的数不对」。

### 3.2 编译是确定性的

- 同一份图，两次编译 `spec_hash` 完全相同（`test_repro_spec.test_spec_hash_stable`）
- 每条 SAU 带 `source_node_ids`，可直接回溯到图节点
- 图缺信息就记 `gaps` / `warnings`，**不编造**（如无 CodeRepository 会写
  「R2 走 PaperCoder 生成路径」）

## 4. R0–R6 门控流水线

`sciforge/repro/phasegraph.json` 定义 7 个阶段，每阶段「读什么 / 产什么 / 哪道门」：

| 阶段 | 名称 | 读 | 产 | 门 |
|---|---|---|---|---|
| R0 | intake-paper | Paper 核心属性 | `RUN_BUDGET.json` `REPRO_SPEC.json` | `paper_core_present` |
| R1 | resolve-method | `PROPOSES_METHOD` / `HAS_MODULE` | `METHOD_CARD.json` `METHOD_LOCK.json` `LINEAGE.json` | `method_grounded` |
| R2 | ground-code | `MODULE_IMPLEMENTED_BY` / `HAS_CODE` / `HAS_FUNCTION` | `CODE_PLAN.json` `STATIC_CHECKS.json` | `code_located` |
| R3 | bind-data | `EVALUATED_ON` / `HAS_CONTRACT` | `DATA_PLAN.json` `SHAPE_PROBE.json` | `data_bound` |
| R4 | fix-metrics | `HAS_METRIC` / `HAS_ENTRY` / `direction` | `METRIC_PLAN.json` `SOTA_BASELINE.json` `ALIGN_RUBRIC.json` | `metrics_comparable` |
| R5 | execute | `REPRO_SCRIPT.py` | `RUNSTATE.json` `events.ndjson` `raw_results.json` | `verdicts_valid` |
| R6 | verify-and-replay | 执行结果 + SAU 判定 | `REPRO_REPORT.md` `REPRO_VERDICTS.json` `SAU_VERDICTS.json` | `reproduction_close` |

**门是硬约束**（`gates.py`）：R0 缺 `research_problem/domain` → `BLOCKED`；
R1 无方法或缺 `mechanism` → `PARTIAL`；R4 指标 `direction` 缺失或
`direction_source=heuristic` → `PARTIAL`（启发式不算 PASS）；
R6 数值偏差 > `0.05 × |baseline|` → `PARTIAL`。

**档位**（`effort_limits`）：

| 档 | 时限 | 允许执行 | 用途 |
|---|---|---|---|
| `dry` | 60s | ❌ | 只编规格与静态判定，numeric 一律 `unverified` |
| `lite` | 3600s | ✅ | 当前实测档（跑 `REPRO_SCRIPT.py`） |
| `full` | 86400s | ✅ | 预留（真实训练/大规模） |

## 5. 逐 SAU 判定规则

`verdict.evaluate_sau(spec, graph, results=None)` 对每条 SAU 给出五种状态：

| SAU kind | 判定依据 | 状态 |
|---|---|---|
| `method` | 有代码符号落地（`code_by_module`） | `aligned`；无 `mechanism` → `absent`；模块无实现边 → `mismatch`（`drift_type=methodological`） |
| `code_grounding` | CodeFunction 节点存在 + 非 stub + 有 signature/name/params | `aligned` / `stub` / `absent` / `mismatch` |
| `protocol` | `input_form` 与 `output_form` 齐 | `aligned`（标 `execution_unverified`，shape 待实测）/ `absent` |
| `numeric` | 有实跑值且偏差在 `tolerance` 内 | `aligned` / `mismatch`（`numerical`）/ **无实跑值 → `unverified`** |
| `ordering` | `code_plan.order` 的先后 | `aligned` / `mismatch`（`ordering`）；成环 → `unverified` |

**诚实约束**：`dry` 下所有 `numeric` 必为 `unverified`，且 `verdict.py` 明写
「dry 无实跑值，R6 不得据此判 PASS」——不允许用「没跑」冒充「跑对了」。

### 5.1 汇总指标（`SAUReport`）

```
decidable   = 非 unverified 的条数
sau_score   = aligned / decidable
coverage    = decidable / total
drift_rate  = (decidable - aligned) / decidable
by_drift    = {numerical, methodological, protocol, ordering} 的失败条数
score_by_kind[k] = aligned_k / decidable_k
```

`drift_rate > 0.2` 触发警告「R6 语义门应判 PARTIAL」；
`coverage < 0.5` 或 `drift_rate > 0.2` 时 `sau_drift_acceptable` 返回 `PARTIAL`。

## 6. 语义层元素 → 复现环节 的完整映射

| 语义层元素 | 进入哪一步 | 变成什么 |
|---|---|---|
| `Paper` 的 `research_question` / `domain` | R0 `paper_core_present` | 门判据（缺则 BLOCKED） |
| `PROPOSES_METHOD` → `Algorithm` | R1 / `method` SAU 的所属 | 方法卡与 LINEAGE |
| `HAS_MODULE` → `AlgorithmModule` | `method` SAU（每模块一条） | 「这个模块做什么」 |
| `AlgorithmModule.inputs/outputs` | `ordering` SAU | 模块执行先后（数据流依赖） |
| `MODULE_IMPLEMENTED_BY` → `CodeFunction` | `code_grounding` SAU + R2 门 | 「模块由哪个函数实现」 |
| `HAS_CODE` → `CodeRepository` / `HAS_FUNCTION` | R2 `code_located` | 代码定位与符号表 |
| `EVALUATED_ON` → `Benchmark` | R3 `data_bound` | 在哪个基准上复现 |
| `Benchmark.input_form/output_form/规模` | `protocol` SAU | 数据契约（怎么喂数据） |
| `Benchmark.metrics[]`（含 `direction`） | R4 `metrics_comparable` | 指标方向与可比性 |
| `LeaderboardEntry`（`model/metric/value`） | `numeric` SAU | 要复现/对比的每一个数 |
| `Benchmark.model_results[].provenance` | `anchor` L2 | 数值的表格单元格出处 |
| `SUBCLASS_OF` | R1 `LINEAGE.json` | 与哪些方法比、改进自谁 |
| `metric.direction = heuristic` | R4 门 | 降为 PARTIAL（不许猜方向） |

## 7. 四环节与 R0–R6 的对应

新增的 `reprospec/lifecycle.py` 把散落在 R0–R6 的可验证动作收敛成四个**可单跑、可校验**的环节：

| 环节 | 对应阶段 | 产物 | 核心校验 |
|---|---|---|---|
| `lock` | R1 | `METHOD_LOCK.json` | 逐条 method SAU 指纹；漂移即不通过 |
| `codegen` | R2 | `CODE_PLAN.json` + `REPRO_SCRIPT.py` | 脚本安全 / 符号召回 / 顺序单调；环降级告警 |
| `execute` | R5 | `EXECUTION_LOG.json` | 双跑一致 + 方法覆盖 + 失败定位到 SAU |
| `anchor` | R4 + R6 | `CLAIM_ANCHORS.json` | 三级链 + 四 hash + 逐条 `verified` |

## 8. MolMiner 全链路实测（effort=lite）

```
语义层：paper:2411.06608 + algorithm:molminer + 10 个模块 + ZINC 等 6 个基准
编译：71 条 SAU（method 14 / code_grounding 17 / protocol 6 / numeric 31 / ordering 3）
R0–R6：门全过（R4 指标方向均为显式，无 heuristic 降级）
执行：subset + full 两档，14 步，24 行、3 个基准，双跑一致
判定：aligned 65 / mismatch 4（method，模块无实现边）/ unverified 2（ordering，缺数据流）
     sau_score 0.942 · coverage 0.9718 · drift_rate 0.058 · exec_rate 1.0
     symbol_recall 1.0 · perf_gap 0.0 · align_mixed 98.2
结论：PARTIAL（drift_rate 0.058 > 0.05），原因可定位到 4 个具体模块
锚定：31 条 claim，30 条三级命中（claim → table_extract:N → Benchmark）
```

**PARTIAL 不是失败**：它精确指出「4 个模块没有实现证据」，
这正是复现需要的结论——比给一个笼统的总分有用。

## 9. 语义层缺信息时怎么降级

| 缺失 | 表现 | 处理 |
|---|---|---|
| 无 `CodeRepository` | `gaps: no_code_symbol_sau`（R2） | 走 PaperCoder 式生成路径，`code_grounding` SAU 为 0 |
| 无 `Benchmark.metrics[]` | R4 `metrics_comparable` → PARTIAL | 只做数值比对，不判方向 |
| 指标方向是启发式 | R4 记 `direction_source=heuristic` | 门降 PARTIAL，要求人工确认 |
| 无数值行 | `numeric` SAU 为 0 | `coverage` 降低，`sau_score` 只按可判定的算 |
| 模块依赖成环 | `ordering` SAU 标 `cycle` | 判 `unverified`，不硬判顺序 |
| 数值来自 LLM 兜底（无表格出处） | `anchor` 的 L2 为空 | claim 标两级（`three_level=false`），不伪造 |

## 10. 边界：这套方法**不能**做什么

- **不能替代真实训练**：`REPRO_SCRIPT.py` 重算的是表格行（数值归一、SOTA 重算、
  baseline/candidate 对比），不是重跑一遍模型训练。`perf_gap` 在 `lite` 下
  只反映「脚本内部一致性」，不代表论文结论被复现。
- **不做自动调参**：`S2_LADDER` 的 GOOD/ENGINEER/BAD 三态由执行结果判定，
  但没有超参搜索循环。
- **不猜缺失信息**：门宁可 BLOCKED/PARTIAL，也不补全 `mechanism` 或指标方向。
- **依赖语义层质量**：E1–E6 抽错的字段会一路传导；`drift_type=methodological`
  往往指向抽取缺失（模块没有实现边），而不是代码真有错。

## 11. 相关文档

- `md/SEMANTIC_LAYER_ARCHITECTURE.md` — 6 类 / 9 关系逐字段说明
- `md/REPRO_LIFECYCLE.md` — 四环节设计与 API
- `md/RUBRIC_TREE_LAYER.md` — 层次化 rubric 树
- `md/GRAPH_ENGINE.md` — networkx 适配与图算法
