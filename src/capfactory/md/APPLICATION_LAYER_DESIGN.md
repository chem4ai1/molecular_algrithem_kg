# 应用层设计：它是什么、后面怎么用

> 2026-11-14　面向后续智能体的设计说明（不是实现日志）
> 关联：`REPRODUCTION_APPLICATION_BLUEPRINT.md`（文献与总体框架）、
> `SEMANTIC_LAYER_ARCHITECTURE.md`（语义层 v4.1）、`APPLICATION_TASK_LAYERS.md`（任务层 v1）、
> `REPRODUCTION_EVALUATION_DESIGN.md`（验证方案）

---

## 0. 先回答两个问题

**Q：我会建造一个什么样的应用层？**

不是"另一张知识图"，也不是"一个 UI 页面"。我会建一个**任务生命周期对象**：
以语义层客观事实为唯一输入，按任务编译出可验证规格，在独立工作区里执行并产生
运行时证据，最后把判定结果和产物一起封成可复现的包。它由 6 个构件组成，
每个构件都有明确的写入边界与生产者。

**Q：后面怎么用它？**

三条路径，同一套内核：
1. **Python API**（研究/批处理）：`compile_reprospec → plan → execute_lite → verify → report`
2. **CLI / 脚本**（CI、批量回归）：一条命令跑一篇论文，产物落 `storage_cf/repro_runs/<aid>/`
3. **Web**（人看）：8091 端口的复现任务页展示 SAU 检查单、执行轨迹、判定与锚

无论哪条路径，**语义层永不被写入**，所有任务态都在应用层或 run 工作区。

---

## 1. 为什么要单独一层（设计动机）

项目里已经有三套 TBox 与两类图，如果再往里塞"复现状态"会立刻失控：

| 层 | 现在装什么 | 能不能装复现状态 |
|---|---|---|
| 语义层 v4.1（6001/7460） | 论文/算法/模块/仓库/函数/基准的**客观事实** | ❌ 装了就污染事实层，换任务无法复用 |
| legacy TBox（46/105） | domain/range 判定入口 | ❌ 只是规则，不是数据 |
| 应用层 v1（任务派生图） | 榜单行、指标、数据契约、证据、局限、出处 | ⚠️ 只该装"挖掘派生"，不该装"本次跑的结果" |

真实矛盾：一次复现会产生 `MethodLock` / `EvaluationResult` / `ClaimAnchor` 等
**只在本次 run 有意义**的对象。把它们写进 `app_reproduction.json` 会导致：
- 多 run 互相覆盖（同一个 `ClaimAnchor` id 属于谁？）
- 页面默认快照混入运行时噪声
- `build_task_layer` 重跑时无法判断哪些是挖掘结果、哪些是执行结果

**结论**：应用层必须再分两个子层——**任务派生层**（可重算、随图重建）与
**运行时层**（按 run 隔离、只追加、不重算）。这就是下面 6 构件里
`AppGraph` 与 `RuntimeGraph` 分开的原因。

---

## 2. 三层架构与写入边界

```
┌─────────────────────────────────────────────────────────────┐
│ 语义层  semantic/  6 类 / 9 关系  6001 节点 / 7460 断言        │
│ 客观事实，NON_LLM 优先（AST/表格/规则），只读                  │
│ 文件：batch10_semantic_v4.json                                │
└───────────────────────┬─────────────────────────────────────┘
                        │ build_task_layer(task)   复制+挖掘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ 任务派生层  applayer/  8 类 / 9 关系                          │
│ 榜单行 / 指标 / 数据契约 / 证据 / 局限 / 出处                  │
│ 可重算、幂等、随语义层重建；文件：app_<task>.json             │
└───────────────────────┬─────────────────────────────────────┘
                        │ compile_reprospec(paper_id)   确定性编译
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ 规格层  reprospec/ReproSpec                                  │
│ 5 类 SAU + MethodLock + DataContract + MetricPlan + CodePlan  │
│ 只读图、零 LLM、spec_hash 幂等                                │
└───────────────────────┬─────────────────────────────────────┘
                        │ R0–R6 消费
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ 运行时层  reprospec/application.py                           │
│ 8 类运行时节点（按 run_id 命名空间隔离）                     │
│ 文件：<out_dir>/app_repro_runtime.json（每个 run 独立）        │
└───────────────────────┬─────────────────────────────────────┘
                        │ evaluate_sau / execute_lite
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ 证据层（run 工作区）                                         │
│ REPRO_SPEC / SAU_VERDICTS / S2_LADDER / raw_results /         │
│ CLAIM_ANCHORS / events.ndjson / RUNSTATE / REPRO_REPORT        │
└─────────────────────────────────────────────────────────────┘
```

### 写入权限矩阵（必须遵守）

| 生产者 | 允许写 | 禁止写 |
|---|---|---|
| `semantic/` 抽取与回填 | `batch10_semantic_v4.json` | 任何 app/run 文件 |
| `applayer/build_task_layer` | `app_<task>.json` | 语义层、run 工作区 |
| `reprospec/compile_reprospec` | 只返回对象；`out_dir` 给定时写 `REPRO_SPEC.json` | 图（一个节点都不改） |
| `reprospec/application` | `app_repro_runtime.json` | `app_reproduction.json` |
| `reprospec/executor` | `REPRO_SCRIPT.py` / `raw_results.json` / `events.ndjson` / `EDIT_LOG.jsonl` | 图 |
| `sciforge/repro/runner` | `REPRO_VERDICTS.json` / `REPRO_REPORT.md` / `RUNSTATE.json` | 图 |

**一句话**：只有 `semantic/` 和 `applayer/` 能写图；其余模块只写 run 目录。

---

## 3. 六个构件与数据契约

| # | 构件 | 定义处 | 关键字段 | 生命周期 |
|---|---|---|---|---|
| 1 | `TaskSpec` | `applayer/tasks.py` | task / classes / relations / miners / runtime_extends | 静态配置 |
| 2 | `AppGraph` | `applayer/builder.py` | `app_reproduction.json`（8300/10260） | 随语义层重建 |
| 3 | `ReproSpec` | `reprospec/contract.py` | `sau[]`, `method_lock`, `data_contract`, `metric_plan`, `lineage`, `code_plan`, `budgets`, `spec_hash` | 每论文一份，可缓存 |
| 4 | `RuntimeGraph` | `reprospec/application.py` | 8 类运行时节点 + 4 关系，`run_id` 命名空间 | 每 run 一份 |
| 5 | `SAUReport` | `reprospec/verdict.py` | `verdicts[]`, `sau_score`, `coverage`, `drift_rate`, `by_drift` | 每 run 一份 |
| 6 | `ExecutionBundle` | `reprospec/executor.py`（P1-5） | `REPRO_SCRIPT.py`, `raw_results.json`, `S2_LADDER.json`, `EDIT_LOG.jsonl`, `events.ndjson` | 每 run 一份 |

### 3.1 为什么 `ReproSpec` 是核心

文献调研（`REPRODUCTION_APPLICATION_BLUEPRINT.md` §1–2）的共同结论是：
**所有有效复现系统都有"论文 → 结构化中间规格 → 代码"这一步**，规格粒度决定复现质量。
PaperBench 靠原作者人工共建 8316 项 rubric，SA-Bench 人工标 1491 条 SAU——最贵的是这一步。

我方 2856 个 `AlgorithmModule` + 758 条代码落地边 + 604 个 `Benchmark`
让这一步可以**从图确定性编译**，边际成本近零，且每条 SAU 自带
`source_node_ids` / `evidence_ids` 可回溯。因此 `ReproSpec` 是应用层的主对象，
其余构件都是它的消费者或产物。

### 3.2 五类 SAU（复用 P0-2 已实现）

| kind | 来源节点 | 判什么 |
|---|---|---|
| `method` | Algorithm + AlgorithmModule | 模块机理是否实现 |
| `code_grounding` | MODULE_IMPLEMENTED_BY → CodeFunction | 符号是否存在、是否 stub |
| `protocol` | Benchmark + DataContract | 输入/输出形式、样本量、shape |
| `numeric` | LeaderboardEntry + MetricDefinition | 数值、单位、方向、容差 |
| `ordering` | Module inputs/outputs 闭包 | 执行顺序（环自动降级） |

---

## 4. 生命周期：从图到报告的 6 步

```
S1  build_task_layer("reproduction")        已有 applayer
      → app_reproduction.json（若已存在直接复用）
S2  compile_reprospec(graph, paper_id)       P0-2 已完成
      → ReproSpec（71 条 SAU for MolMiner）+ spec_hash
S3  plan_repro(graph, paper_id)              已有 sciforge/repro/planner
      → ReproPlan（方法/代码/数据/指标清单 + gaps）
S4  run_repro(..., effort="lite")            P1-5 起
      ├─ 生成独立可重跑 REPRO_SCRIPT.py（Artisan 式）
      ├─ 沙箱 subprocess 执行（venv/隔离 env/超时）
      ├─ 失败 → traceback 归因 → EDIT N M 定点修复 → 重跑（≤20）
      ├─ subset → full 阶梯（SciForge S2 三态 Critic）
      └─ events.ndjson（durable truth）+ RUNSTATE（派生快照）
S5  verify                                  P0-3/P0-4 + P2-8
      ├─ 逐 SAU 判定（执行结果回填 numeric）
      ├─ 混合级 Align-Score / Exec Rate / Perf Gap
      ├─ 三哈希 ClaimAnchor（code / inputs / outputs）
      └─ 8 类运行时节点写独立图
S6  report
      → REPRO_REPORT.md + SAU_VERDICTS.json + CLAIM_ANCHORS.json
      → 汇总进 capfactory/md/REPRODUCTION_VALIDATION_REPORT.md
```

**幂等与可恢复**：
- `spec_hash` 相同 → 复用 ReproSpec，不重编译
- `events.ndjson` 是唯一 truth，`RUNSTATE.json` 可从事件重放（`state.replay`）
- 每个 run 用 `run_id` 命名空间，重跑不覆盖旧产物（`ws` 可指定）
- `ClaimAnchor` 三哈希任一变化即判 `drift`

---

## 5. 三种使用方式（具体到代码）

### 5.1 Python API（研究/批处理，推荐）

```python
from pathlib import Path
from capfactory.po import POGraph
from capfactory.reprospec import compile_reprospec, evaluate_sau
from capfactory.sciforge.repro import run_repro

g = POGraph.load("storage_cf/sciforge/app_reproduction.json")

# 只编译规格（秒级、零副作用）
spec = compile_reprospec(g, paper_id="paper:2411.06608")
print(spec.counts(), spec.spec_hash)

# 完整 lite 复现（真跑，产物落 out）
rep = run_repro(g, "paper:2411.06608",
                ws=Path("storage_cf/repro_runs/2411.06608"),
                effort="lite")
print(rep["overall"], rep["verdicts"]["R6"]["verdict"], rep["sau"])
```

### 5.2 CLI / 批处理（CI）

```bash
cd /home/zengshuxin/xKG-main/xKG-main
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
    --arxiv 2411.06608 --effort lite \
    --out storage_cf/repro_runs/2411.06608

# 批量：多篇论文 + 统一评估
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
    --batch 2411.06608,2102.09844 --effort lite --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md

# 崩溃恢复（events 重放）
PYTHONPATH=. python3 -m capfactory.reprospec.cli --resume storage_cf/repro_runs/2411.06608
```

### 5.3 Web（人看，8091）

```
GET  /api/v6/repro/tasks                   → 可复现论文清单 + 就绪度
GET  /api/v6/repro/spec?arxiv=...          → SAU 检查单（5 类、逐条状态）
POST /api/v6/repro/run  {arxiv, effort}    → 启动，返回 run_id
GET  /api/v6/repro/run/{run_id}            → events / ladder / verdicts / anchors
GET  /static/repro.html                    → 页面（P2 阶段）
```

页面只**读** run 目录，不直接改图；启动动作走 `run_repro`。

---

## 6. 目录与文件约定

```
capfactory/
├── semantic/          事实层（只读）
├── applayer/          任务派生层（可重建）
├── ontology/          legacy 判定入口（domain/range）
├── reprospec/         规格 + 运行时 + 验证（本次新增工作目录）
│   ├── relations.py / contract.py / compiler.py      P0-1/P0-2
│   ├── application.py / verdict.py                  P0-3/P0-4
│   ├── executor.py / ladder.py / probe.py           P1-5/P1-6/P1-7
│   ├── scoring.py / cli.py                         P2-8/P2-9
│   └── README.md
└── sciforge/repro/     R0–R6 状态机（宿主）
    ├── phasegraph.json / planner.py / gates.py
    ├── runner.py / state.py / contract.py
    └── ...

storage_cf/repro_runs/<arxiv_id>/
├── REPRO_SPEC.json  SAU_LIST.json  REPRO_PLAN.json
├── REPRO_SCRIPT.py  raw_results.json  S2_LADDER.json  EDIT_LOG.jsonl
├── events.ndjson    RUNSTATE.json   SHAPE_PROBE.json  LINEAGE.json
├── SAU_VERDICTS.json  ALIGN_RUBRIC.json  CLAIM_ANCHORS.json
├── app_repro_runtime.json
├── REPRO_VERDICTS.json  REPRO_REPORT.md
└── .repro/events.ndjson（重放源）
```

---

## 7. 设计取舍（为什么这样做）

| 取舍 | 选择 | 理由 |
|---|---|---|
| 规格放不放图里 | **不放**，作为独立 JSON | SAU 是任务派生判定单元，不是客观事实；放图会污染语义层且无法按 run 隔离 |
| 运行时节点放哪 | 独立 `app_repro_runtime.json` | 8/9 基础契约被 798 项测试锁定；多 run 不能共享同一 id 空间 |
| LLM 用在哪 | **规格编译与判定零 LLM** | 保证 `spec_hash` 稳定、结果可复核；LLM 只用于抽取阶段（Stage2）与可选族推断 |
| 执行隔离 | 子进程 + env 白名单 + 超时；Docker 可选 | 本机 Docker 28.4 可用但拉镜像成本高；先保证接口一致，生产可换 `xkg-coderunner` |
| 不真跑原论文训练 | 明确保留为边界 | 无数据集/GPU/原仓库权重；诚实标注哪些 SAU 仍 unverified |
| 失败修复 | `EDIT N M` 定点替换，不整文件重生成 | AutoReproduce 消融：去掉 Debug+Refine，Perf Gap 从 19.72% 恶化到 88.78% |
| 门是否一次全打开 | dry 保持 BLOCKED，lite 才允许 PASS | `test_p1_repro.py:150` 锁定诚实行为；避免"让测试变绿"式造假 |

---

## 8. 与其他智能体的接口约定

1. **不要**修改 `semantic/tbox_v4.py`、`applayer/tbox.py` 的类/关系数量（测试锁定 6/9 与 8/9）
2. **不要**把运行时类写进 `app_reproduction.json`
3. 新增 run 产物时，同步在 `phasegraph.json` 对应 phase 的 `produces` 里登记（publish 门会做集合双向比对）
4. 新增关系名先登记到 `reprospec/relations.py` 的 `ALL_CANONICAL`
5. 任何"实跑值"必须来自 `REPRO_SCRIPT.py` 的 stdout，禁止从图里抄期望值当结果
6. 改 `gates.py` 的 `reproduction_close` 前先确认 `dry` 分支仍 BLOCKED
7. 每个阶段跑完必须 `append` 一条 `events.ndjson`，否则 `resume_repro` 会失忆

---

## 9. 这个应用层"不做"什么

- 不做原论文完整训练复现（需要数据集、GPU、原仓库权重）
- 不做论文生成 / 想法发现（那是 SciForge 的 16 相位，不在本层）
- 不做语义层本体的自动归纳（GrOIL 式，属另一条路线）
- 不替代 `sciforge/repro/` 的状态机（本层提供规格与证据，宿主负责门与调度）
- 不在 dry 模式伪装任何执行结果

---

## 10. 落地状态与下一步

| 阶段 | 状态 |
|---|---|
| 事实层 / 任务派生层 | 已有 |
| 规格层 P0-1/P0-2 | ✅ 完成（28 项测试） |
| 运行时层 + 静态判定 P0-3/P0-4 | ✅ 完成（22 项测试） |
| 执行层 P1-5（lite 真跑） | ✅ 完成（`reprospec/executor.py`） |
| 阶梯/探针 P1-6/P1-7 | ✅ 完成（`ladder.py` / `probe.py`） |
| 评分/锚/门 P2-8/P2-9 | ✅ 完成（`scoring.py` / `cli.py` / `runner.py`） |
| 真实验证报告 | ✅ `capfactory/md/REPRODUCTION_VALIDATION_REPORT.md` |
| 实现设计取舍汇总 | ✅ `capfactory/md/REPRODUCTION_IMPLEMENTATION_BLUEPRINT.md` |

验证方法见 `REPRODUCTION_EVALUATION_DESIGN.md`。
