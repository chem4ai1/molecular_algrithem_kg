# 复现生命周期重设计：锁定 → 生成 → 执行 → 锚定

> 2026-11-15。代码：`reprospec/lifecycle.py`（436 行）、
> `web/repro_api.py`、`web/static/repro.html`。
> 工作区示例：`storage/repro_test/2411.06608/`。

## 1. 旧实现的四个薄弱点

| 环节 | 旧实现 | 问题 |
|---|---|---|
| 方法锁定 | `spec.method_lock` 里一个 `method_sau_hash` | 只有集合级 hash，无法定位是哪条 SAU 变了；没有漂移拒绝 |
| 代码生成 | `build_repro_script` 直接出单文件 | `CodeGenerationTask` 只是给前端看的节点，没有依赖 DAG、没有任务级校验 |
| 复现执行 | `_run_once` 跑一次 + ladder 两档 | 没有双跑一致性；失败只到脚本级，落不到 SAU |
| 主张锚定 | `claim_anchors` 给前 5 条 numeric SAU 挂同一组 hash | 没有「claim → 表格单元格 → 图节点」的链；无法逐条验证 |

## 2. 新架构：统一生命周期

```python
run_lifecycle(paper_id, ws) ->
  lock   → METHOD_LOCK.json
  codegen→ CODE_PLAN.json + REPRO_SCRIPT.py
  execute→ EXECUTION_LOG.json
  anchor → CLAIM_ANCHORS.json
  ─────────────────────────────
  LIFECYCLE.json（四阶段结果 + status + verify）
```

四个环节**都可以单独触发**（`POST /api/v9/repro/{aid}/run?stage=lock|codegen|execute|anchor`），
任一环节 `blocked` 就停在那里并记录 `blocked_at / blocked_by`，不静默继续。

## 3. 逐环节设计

### 3.1 方法锁定（lock）

- **双层锁**：`spec_hash`（全局）+ `method_sau_hash`（method SAU 集合）+ **逐条 `fingerprints{}`**
- 指纹只取影响复现语义的字段：`id / kind / statement / source_node_ids / check / required`
- **漂移检测**：与已有锁比对，新增/变更的 SAU 进入 `drift[]`，`passed=false`
- 门：无 method SAU → `BLOCKED(no_method_sau)`

```json
{"locked": true, "n_method_sau": 14,
 "method_sau_hash": "sha256:6960a89e0908d6300dc5",
 "fingerprints": {"sau:241106608:method:000": "sha256:…"},
 "drift": [], "passed": true}
```

### 3.2 代码生成（codegen）

- **DAG**：节点 = `ordering` SAU 的 before/after + method SAU 引用的模块；边 = 依赖
- **环处理**：真实论文可能双向声明（如跨论文共享模块 `2608.06956`），
  拓扑排序遇环时**降级为稳定排序 + `warnings`**，不阻断
- **任务化**：每模块一个 `CodeGenerationTask`，含 `order / depends_on / strategy(existing|generate) / status`
- **三项校验**：
  1. `safety`：`check_script_safety()`（纯 stdlib、不读应用层期望值）
  2. `symbol_recall`：`code_grounding` 的 `check.target`（CodeFunction id）在图中真实存在
  3. `order_ok`：任务 order 严格递增
- 产物：`CODE_PLAN.json` + `REPRO_SCRIPT.py`（记录 `sha`）

### 3.3 复现执行（execute）

- **阶梯**：脚本内部 `subset(12 行)` → `full(全量)`，两档分别记录 `rows / steps / baseline / candidate`
- **双跑一致性**：同一脚本跑两次，比对 payload 与 `outputs_sha`，不一致 → `BLOCKED(not_repeatable)`
- **SAU 级失败定位**：
  - 脚本失败 → `diagnose(stderr)` 归因（NameError / SyntaxError / Timeout，含 `fixable`）
  - 模块未出现在 `symbol_trace` → 对应 method SAU 记 `module_not_exercised`
- 产物：`EXECUTION_LOG.json`（stages / coverage / failures / double_run）

### 3.4 主张锚定（anchor）

**三级链**，每条 claim 都可回溯：

```
L1 claim   numeric SAU：model / metric / value / unit / direction / tolerance
L2 cell    表格单元格：entry_id + table_ref(table_extract:N) + row_index + paper_id
L3 graph   图节点：benchmark_id + LeaderboardEntry id + MetricDefinition id
```

- L2 出处取值优先级：`LeaderboardEntry.provenance` → `Benchmark.model_results[].provenance`
  → **抽取报告**（`semantic_extraction/<aid>.json` 的 `model_results.rows`，按 model/metric/value 精确匹配）
- 每条 claim 记录 4 个 hash：`spec / code / inputs / outputs`
- `integrity`：所有 claim 的 `code_sha` 与当前脚本一致、`outputs_sha` 与执行日志一致
- 产物：`CLAIM_ANCHORS.json`

### 3.5 完整性校验（verify）

`verify_lifecycle(ws)` 重算并比对，任一不符即 `ok=false`：

- `script_modified_after_codegen`：脚本被改动
- `anchor_code_sha_mismatch` / `anchor_outputs_sha_mismatch`
- `claim_unverified`

## 4. 实测（MolMiner 2411.06608，lite）

| 环节 | 结果 |
|---|---|
| lock | 14 条 method SAU，`method_sau_hash sha256:6960a89e…`，drift 0 |
| codegen | 14 任务、3 条依赖边、10 个模块有代码锚、`symbol_recall 1.0`、脚本安全通过 |
| execute | 2 档（subset/full）、双跑一致、**方法覆盖 14/14 = 100%**、失败 0 |
| anchor | **31 条 claim、30 条三级命中**、`integrity true`、`double_run_equal true` |
| verify | `ok true`，无 issue |

四阶段全部 `done`，`ready=true`。

## 5. 开放模块（API）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v9/repro/papers` | 有工作区的论文列表（按 arxiv_id 去重，四环节齐全者优先） |
| GET | `/api/v9/repro/{aid}/status` | 四环节状态 + 关键指标（前端状态条） |
| GET | `/api/v9/repro/{aid}/lifecycle` | 完整生命周期结果 |
| GET | `/api/v9/repro/{aid}/method-lock` | 锁文件（含逐条指纹） |
| GET | `/api/v9/repro/{aid}/code-plan` | DAG + 任务表 + 校验 |
| GET | `/api/v9/repro/{aid}/execution` | 阶梯 + 覆盖 + 失败定位 |
| GET | `/api/v9/repro/{aid}/anchors` | 三级锚（最多 200 条） |
| GET | `/api/v9/repro/{aid}/verify` | 完整性校验 |
| POST | `/api/v9/repro/{aid}/run?stage=all\|lock\|codegen\|execute\|anchor` | 触发（all 跑全流程） |

Python 侧等价入口：

```python
from capfactory.reprospec.lifecycle import (run_lifecycle, stage_status,
                                            verify_lifecycle, run_lock,
                                            run_codegen, run_execute, run_anchor)
```

## 6. 前端：`/repro` 复现控制台

单页（`web/static/repro.html`，无构建步骤）：

- 顶栏：论文下拉 + 刷新 + **运行全流程** + **校验完整性**
- 四环节状态条：每格显示 `pending / done / failed` 与关键指标
- 四个详情面板：
  - ① 方法锁定：锁定时间、`spec_hash`、漂移数、逐条 SAU 指纹表
  - ② 代码生成：脚本 sha/字节数、安全/顺序/告警、任务表（顺序/模块/策略/依赖/状态）
  - ③ 复现执行：输出 sha、阶梯表（阶段/状态/行数/步数/baseline/candidate）、失败定位表
  - ④ 主张锚定：四个 hash、claim 表（模型/指标/值/**表格出处**/级别/校验）
- 校验结果条：通过为绿，问题列出 `issues`

## 7. 与旧实现对照

| 能力 | 旧 | 新 |
|---|---|---|
| 锁粒度 | 集合 hash | 集合 hash + 逐条指纹 |
| 锁漂移 | 无检测 | `drift[]` + 不通过 |
| 代码生成 | 单文件 | DAG + 任务化 + 三项校验 |
| 依赖环 | 未处理 | 降级为 warn，不阻断 |
| 执行 | 跑一次 | 双跑一致性 + 阶梯 + SAU 级失败定位 |
| 锚定 | 前 5 条共用一个 hash | 31 条全覆盖 + 三级链 + 逐条 verified |
| 可观测 | 只有最终 evaluation | 四阶段独立 API + 控制台 |
| 篡改检测 | 无 | `verify_lifecycle` |

## 8. 边界

- 全流程零 LLM；`execute` 只跑 `REPRO_SCRIPT.py`（纯 stdlib），不联网、不读应用层期望值。
- `effort=lite` 时 `perf_gap` 无意义（脚本重算的是表格行本身），真实执行器接入后才有复现质量含义。
- `anchor` 的 L2 依赖 `table_extract:N`，若某数值来自 LLM 兜底（无表格出处），该 claim 为两级（`three_level=false`），如实标注不伪造。
- 依赖环降级排序会牺牲顺序最优性，但 `order_ok` 仍校验单调，且 `warnings` 如实记录。
- 工作区路径约定 `storage/repro_test/<arxiv_id>/`；旧 `storage/repro_runs/` 仍可读（API 自动回退）。
