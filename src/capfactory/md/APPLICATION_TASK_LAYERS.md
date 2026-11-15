# 图导入 / 前端显示审视 · 应用层任务化设计

> 2026-11-14。本文回答两个问题：
> ① 图导入后端与前端显示有没有问题、怎么修；
> ② 应用层是怎么构建的、会不会在抽取过程中出现暧昧；
> 并给出「论文复现 / 论文生成」两种任务构建应用层的思路与过程。

---

## 1. 图导入后端与前端：审视结论

### 1.1 数据一致性（检查通过）

| 项 | 实测 |
|---|---|
| 语义层 | 6001 节点 / 7460 断言 |
| 页面默认图（语义层快照） | 6001 节点 / 7460 断言，`layer=semantic` |
| 应用层断言 | 全部带 `layer="semantic"` 或 `layer="application"` |
| 页面属性对齐 | `domain / keywords / research_question / title` 与语义层逐字段一致 |
| 类型别名 | `AlgorithmModule → AlgorithmStep`（兼容旧前端渲染） |
| 语义层断言复制 | 7460 条完整复制，无丢失 |

### 1.2 发现并修复的 5 个问题

| # | 问题 | 影响 | 修复 |
|---|---|---|---|
| 1 | `POGraph.outgoing/incoming` 每次全扫 `self.assertions`（11826 条） | 三库树要扫数千万次，算法树 2.3s | 加惰性邻接索引 `_ensure_adj()`，按 `(node, relation)` 查表；断言列表整体替换也能按 `(len, id)` 自动重建。3000 次查询 30ms |
| 2 | `data_api._CACHE` 永不失效 | **图重建后页面仍读旧图，必须重启服务** | 按 `application` 图文件 `st_mtime_ns` 自动失效重载 |
| 3 | 论文树把应用层 `ResearchQuestion` 当子节点混进语义层 | 违反「应用层只在任务时构建」；且每篇 Paper 全扫 783 个应用节点（63 万次） | 语义层论文树只展示语义层关系，删除该段 |
| 4 | 应用层断言缺 `layer` 标记（4366 条为 `None`） | 无法按层过滤断言，节点卡片 `in/out` 混入应用关系 | `miner.rel()` 统一写 `layer="application"`、`task=<任务名>` |
| 5 | `refresh_all` / `apply_all` **无条件** `mine_all()` 建全 8 类应用节点 | 抽取/回填期就产生应用层，与「只在复现/生成任务时构建」的约定冲突（**暧昧根源**） | 改成只出「纯语义层快照」，应用节点改由 `TaskSpec` 显式构建（见 §2） |

### 1.3 前端性能（修复前后）

| API | 修复前 | 修复后（首次 / 缓存后） |
|---|---:|---:|
| 论文树 `tree?library=paper` | 1019 ms | 523 / **74 ms** |
| 算法树 `tree?library=algorithm` | 2333 ms | **129 / 118 ms** |
| 数据树 `tree?library=dataset` | 645 ms | **294 ms** |
| 关系实例 | 353 ms | — |
| 节点卡片 | 6 ms | — |

三库树分组正常（论文 12 组 / 算法 9 组 / 数据 6 组），
`/relations` 关系实例 paper 808 / algorithm 1674 / data 584，
ZINC 溯源卡片 155 格、跨 7 篇论文。**前端导入与显示无异常**。

---

## 2. 应用层构建机制审视

### 2.1 之前是怎么做的（有暧昧）

```
semantic.apply.apply_all(rebuild_app=True)
semantic.refresh.refresh_all(rebuild_app=True)
        └─ applayer.miner.mine_all(sem_g)
             ├─ 复制语义层 6001 节点 + 7460 断言
             └─ 无差别跑 8 个挖掘器，一次性建出全部 8 类应用节点
                 （ResearchQuestion / ProblemCategory / LeaderboardEntry /
                  MetricDefinition / DataContract / Evidence / Limitation /
                  SourcePaper）写入 batch10_app_v1.json
```

三个暧昧点：

1. **时机暧昧**：抽取 783 篇论文、回填语义层的过程中就把应用节点建好了，
   而应用层本该是「任务驱动」的派生视图。
2. **语义暧昧**：复现关心榜单/数值/证据，写作关心研究问题/类别/叙述素材；
   两者混在同一张图里，消费方无法区分「这条证据是为复现还是为写稿准备的」。
3. **类名暧昧**：应用层去掉 `App` 前缀后与 legacy TBox 同名
   （`ResearchQuestion` / `MetricDefinition` …），早期只靠 `layer` 属性区分，
   而断言没有 `layer`，跨层关系容易误读。

### 2.2 现在：任务驱动，抽取期零应用节点

```
抽取 / 回填 / refresh
   └─ mine_all(task=None)  → batch10_app_v1.json
        仅复制语义层节点与断言（6001 / 7460），
        by_type={} / n_relations=0 / 挖掘器完全不跑

任务启动时（显式调用）
   ├─ build_task_layer("reproduction") → app_reproduction.json
   └─ build_task_layer("generation")   → app_generation.json
        按 TaskSpec 只建该任务的类、关系、挖掘器
```

**结论：现在不会在抽取过程中出现暧昧。** 页面默认图里
`layer="application"` 的节点数为 0；应用节点只存在于任务层文件，
且每个节点带 `task`、每条关系带 `layer` + `task`。

代码位置：

| 文件 | 职责 |
|---|---|
| `applayer/tasks.py` | `TASK_SPECS` 两种任务规格 + `spec()` / `snapshot()` / `out_path()` |
| `applayer/builder.py` | `build_task_layer(task)` 唯一允许产生应用节点的入口 |
| `applayer/miner.py` | `mine_all(task=...)`；`task=None` 直接短路，指定任务时 `add/rel` 按 spec 过滤 |
| `web/graph_source.py` | `load_task(task)` / `rebuild(task)` |
| `web/tbox_api.py` | `/api/v8/task/specs`、`/{task}/status`、`/{task}/build`、`/task/snapshot/build` |

`apply_all(rebuild_app=False)` 默认不再建应用图；`refresh_all(rebuild_app=True)`
只重建语义层快照，并在报告里用 `semantic_snapshot` 明确标注。

### 2.3 两种任务的规格对比

| | 论文复现 reproduction | 论文生成 generation |
|---|---|---|
| 目标 | 把方法/数值/代码复现并比对 | 基于谱系生成新的研究叙述与稿件 |
| 应用类 | LeaderboardEntry · MetricDefinition · DataContract · Evidence · Limitation · SourcePaper | ResearchQuestion · ProblemCategory · MetricDefinition · DataContract · Evidence · Limitation · SourcePaper |
| 应用关系 | HAS_ENTRY · USES_METRIC · HAS_METRIC · HAS_CONTRACT · SUPPORTED_BY · HAS_LIMITATION · SITUATED_IN | FORMULATES · IN_CATEGORY · HAS_METRIC · HAS_CONTRACT · SUPPORTED_BY · HAS_LIMITATION · SITUATED_IN |
| 挖掘器 | metrics · leaderboard · contracts · evidence · limitations · source_papers | questions · categories · metrics · contracts · evidence · limitations · source_papers |
| 主要读取 | `Benchmark.model_results[]`、`metrics[]`、`Algorithm.limitations`、`RELATED_TO`、`application_hints.json` | `Paper.research_question / problem_category / keywords`、`Benchmark.metrics[]`、`Algorithm.limitations`、`RELATED_TO` |
| 独有 | **榜单行 + 动态 SOTA + 单元格证据链** | **研究问题与类别聚类 + 章节素材** |
| 实测产物 | 8300 节点 / 10260 断言（应用关系 2800） | 8853 节点 / 11195 断言（应用关系 3735） |

两者共享 `MetricDefinition / DataContract / Evidence / Limitation / SourcePaper` 五类，
差异正对应「数值比对」与「叙述组织」的分工。

---

## 3. 任务一：论文复现 reproduction

### 3.1 思路

复现的判定链是「论文声称了什么数值 → 我们跑出来多少 → 差在哪 → 代码在哪」。
所以应用层不重新抽事实，只把语义层里**已经抽好的** `model_results[]`、
`metrics[]`、`limitations`、`RELATED_TO` 展开成可计算、可比对的节点。

### 3.2 构建过程

```
输入  batch10_semantic_v4.json（6001/7460）
     + semantic_extraction/application_hints.json（Tool/Formula 线索）

① mine_all(task="reproduction")
   ├─ 复制语义层节点 + 断言（layer=semantic）
   └─ add/rel 只放行 TASK_SPECS["reproduction"] 的 6 类 / 7 关系
② 挖掘器按序执行（仍确定性、无 LLM）：
   metrics      ← Benchmark.metrics[] 去重归一 → MetricDefinition(447)
   leaderboard  ← Benchmark.model_results[] 展开 → LeaderboardEntry(247)
   contracts    ← input/output_form + 规模 → DataContract(604)
   evidence     ← 每个单元格 → Evidence(247)，带 paper_id / provenance
   limitations  ← Algorithm.limitations[] → Limitation(728)
   source_papers← Paper-RELATED_TO->Paper → SourcePaper(26)
③ 建边：HAS_ENTRY / USES_METRIC / HAS_METRIC / HAS_CONTRACT /
        SUPPORTED_BY / HAS_LIMITATION / SITUATED_IN
④ 输出到 storage_cf/sciforge/app_reproduction.json
   （8300 节点 / 10260 断言，其中应用关系 2800）
```

### 3.3 消费方式

- `SUPPORTED_BY` 把每个榜单行连回 `Evidence`，可逐格回溯到
  `table_extract:N` 与 `paper:<aid>`；
- `USES_METRIC` + `MetricDefinition.direction` 支撑动态 SOTA 重算；
- `DataContract` 给出输入/输出形式与规模，供复现 runner 准备数据；
- `Limitation` / `SourcePaper` 给出失败原因与基线出处，供 R6 阶段回填；
- `application_hints.json` 的 Tool/Formula 线索在此任务里才节点化
  （语义层始终保持「只放客观事实」）。

---

## 4. 任务二：论文生成 generation

### 4.1 思路

写作的判定链是「领域里还有什么问题没解决 → 已有方法做到哪 →
哪些数值/局限可以引用 → 怎么组织叙述」。所以它不需要榜单行，
而是把 `Paper.research_question` 提升为可聚类节点，并与类别、
指标、契约、证据、局限、出处组成素材网。

### 4.2 构建过程

```
输入  batch10_semantic_v4.json（同一份语义层，不重抽）

① mine_all(task="generation")
   ├─ 复制语义层节点 + 断言
   └─ add/rel 只放行 7 类 / 7 关系（不放行 LeaderboardEntry、
      HAS_ENTRY、USES_METRIC）
② 挖掘器：
   questions   ← Paper.research_question → ResearchQuestion(783)
   categories  ← problem_category 聚类 → ProblemCategory(17)
   metrics / contracts / evidence / limitations / source_papers
               ← 与复现任务共用，产出一致（447/604/247/728/26）
③ 建边：FORMULATES / IN_CATEGORY / HAS_METRIC / HAS_CONTRACT /
        SUPPORTED_BY / HAS_LIMITATION / SITUATED_IN
④ 输出到 storage_cf/sciforge/app_generation.json
   （8853 节点 / 11195 断言，其中应用关系 3735）
```

### 4.3 消费方式

- `Paper -FORMULATES-> ResearchQuestion -IN_CATEGORY-> ProblemCategory`
  构成「问题地图」，用于选题与相关工作章节；
- `Evidence` + `MetricDefinition` 提供可引用的数值与指标定义；
- `DataContract` 描述实验设置，`Limitation` 提供「本文动机」素材；
- `SourcePaper` 给出科技树位置，支撑 `Related Work` 叙述；
- 与复现任务**共享底层语义层**，但不共享应用节点，两边互不污染。

### 4.4 两个任务如何共存

```
batch10_semantic_v4.json       ← 唯一事实源（6001/7460）
batch10_app_v1.json            ← 页面默认：纯语义层快照（零应用节点）
app_reproduction.json          ← 任务 A 启动时构建
app_generation.json            ← 任务 B 启动时构建
```

任务层文件各自独立，可单独删除/重建；互不引用对方的应用节点。
`task` 与 `layer` 双标记保证任何消费方都能判断节点归属。

---

## 5. 操作入口

```bash
curl http://127.0.0.1:8091/api/v8/task/specs
curl http://127.0.0.1:8091/api/v8/task/reproduction/status
curl -X POST http://127.0.0.1:8091/api/v8/task/reproduction/build
curl -X POST http://127.0.0.1:8091/api/v8/task/generation/build
curl -X POST http://127.0.0.1:8091/api/v8/task/snapshot/build
```

```python
from capfactory.applayer.builder import build_task_layer
build_task_layer("reproduction")   # → app_reproduction.json
build_task_layer("generation")     # → app_generation.json
from capfactory.web.graph_source import load_task, rebuild
g = load_task("reproduction")      # 未构建时抛清晰错误
rebuild(task=None)                 # 只重建语义层快照
```

## 6. 边界与后续

- **不自动触发**：任务层只在显式调用时构建；pipeline、refresh_all、
  批处理收尾都不会顺带产生应用节点。
- **不重复事实**：所有应用节点带 `derived_from`（语义层节点 id）与 `miner`，
  不允许在应用层手工造事实。
- **Tool/Formula 仍未节点化**：目前只在 `application_hints.json`，
  按设计留给复现任务展开；需要时在 `TASK_SPECS["reproduction"]["classes"]`
  加 `Tool`/`Formula` 并补挖掘器。
- **paper_ids 作用域**：当前任务层基于全量语义层；后续可给
  `build_task_layer(task, paper_ids=[...])` 加子集限定。
- **页面默认图不含应用节点**：前端要展示任务层内容应走
  `/api/v8/task/{task}/...` 或 `load_task(task)`，不要改 `data_api._graph()`。
- **别名映射**：`graph_source.load("application")` 仍把
  `AlgorithmModule → AlgorithmStep`、`research_question → research_problem`，
  这是纯前端兼容，不改变图文件内容；任务层文件不做别名转换。

## 7. 验收

```
783 unittest OK · Phase 81 OK · 冒烟 60/60 · compile OK
页面三库树：论文 12 组 / 算法 9 组 / 数据 6 组
论文树 74 ms · 算法树 118 ms（缓存后；修复前 1019 / 2333 ms）
语义层快照：6001 节点 / 7460 断言 / 0 应用节点
reproduction：8300 节点 / 10260 断言（6 类应用节点，应用关系 2800）
generation  ：8853 节点 / 11195 断言（7 类应用节点，应用关系 3735）
```

测试覆盖：页面默认图零应用节点、复现任务独有 `LeaderboardEntry`、
生成任务独有 `ResearchQuestion`、两任务关系分流、缓存 mtime 失效、
邻接索引正确性。

---

## 8. 相关文档

- `md/EXTRACTION_OVERVIEW.md` — 抽取链路代码级说明
- `md/TBOX_INVENTORY.md` — TBox 清点与精简
- `docs/PROVENANCE_AND_VECTOR_AUDIT.md` — 溯源与向量库审查
- `docs/FRONTEND_PAPER_DIAGNOSIS.md` — 论文库前端问题根因
补记：TASK_SPECS[reproduction] 已新增运行时类 RubricNode 与关系 HAS_SAU（仅进单篇 app_repro_runtime.json，全量应用层图不产生），详见 md/RUBRIC_TREE_LAYER.md。
