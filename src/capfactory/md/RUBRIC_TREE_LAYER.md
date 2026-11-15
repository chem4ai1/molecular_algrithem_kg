# 层次化 Rubric 树层（2026-11-15 落地）

> 对应蓝图 `md/REPRODUCTION_APPLICATION_BLUEPRINT.md` §1 ③ PaperBench、
> §2.1、§4.3 与 P2-8 的 `align_rubric`。本文记录**实际落地形态**、
> 与 PaperBench 的差异、以及与 PaperCoder 三阶段的关系。

## 1. 为什么建

落地前 `SAU_LIST.json` 是**扁平 74 条**，`SAU_VERDICTS.json` 逐条判定，
但运行时图只有 **5 个按 kind 聚合的 `EvaluationResult`**，
`ALIGN_RUBRIC.json` 是 9 项全局加权分（0.3·paper + 0.7·code）。
结果是只知道「numeric 类分低」，无法下钻到具体模块/具体基准。

树化的收益（都基于当前图结构）：

| 收益 | 落地前 | 落地后 |
|---|---|---|
| 定位失败点 | 按 kind 聚合 | 精确到 `algorithm:midi/algorithmmodule:...:regnn_layer` 这类分支 |
| 权重 | 全局常数 0.3/0.7 | `required` 叶子权重 2.0、可选 1.0，沿路径聚合 |
| 增量重跑 | 整篇 74 条重判 | `failed_branches[]` 只重判失败子树 |
| 边际成本 | — | 复用 `PROPOSES_METHOD / HAS_MODULE / MODULE_IMPLEMENTED_BY / EVALUATED_ON`，零 LLM、零新事实 |
| 跨论文统计 | 只能按 kind | 可按 `path` 前缀聚合（哪个模块类型最常 drift） |

## 2. 关键前提：SAU 是跨两层的

实测 MolMiner 的 172 个 `source_node_ids`：

```
只查语义层图                    命中 111 / 172 = 64.5%
join app_reproduction.json      命中 172 / 172 = 100%
分层：semantic 111 + application 61
```

未命中的 61 个是 `appcontract:` / `applb:` / `appmetric:`（应用层 reproduction 节点）。
语义层 `AlgorithmModule` 的 id 前缀还混用了 `algorithmstep:`(31) 与
`algorithmmodule:`(2825)（迁移遗留），两者都能命中。

**结论：树属于 reproduction 任务层，语义层只提供骨架，语义层 6 类一个都不动。**

## 3. 层次设计

```
L0  ReproTask 根  = paper:<aid>
 ├─ L1 方法子树   ← PROPOSES_METHOD → Algorithm
 │    └─ L2 模块   ← HAS_MODULE → AlgorithmModule
 │         └─ L3 叶子 SAU：method / ordering / code_grounding
 │              （code_grounding 沿 MODULE_IMPLEMENTED_BY 反查 CodeFunction 归属模块）
 └─ L1 评测子树   ← EVALUATED_ON → Benchmark
      └─ L2 叶子 SAU：numeric / protocol
           （applb:/appmetric:/appcontract: 沿 derived_from 反查 Benchmark）
```

挂载规则（`rubric_tree._parents()` / `_pick_anchor()`，确定性）：

| 末位 id 类型 | 父节点 | 深度 |
|---|---|---:|
| `algorithmmodule:` / `algorithmstep:` | 该模块（再沿 HAS_MODULE 找 L1） | 3 |
| `codefunction:` | 沿 MODULE_IMPLEMENTED_BY → 模块 | 3 |
| `benchmark:` | 该 Benchmark | 2 |
| `applb:` / `appmetric:` / `appcontract:` | `derived_from` 里的 Benchmark | 2 |
| `algorithm:` 且无模块 | 该 Algorithm | 2 |
| 兜底 | Paper 根 | 1 |

## 4. 代码与产物

| 位置 | 改动 |
|---|---|
| `reprospec/contract.py` | `SAU` 加 `parent_id / path / depth / weight`；**`stable_key()` 不变**，`spec_hash` 与 `MethodLock` 保持有效 |
| `reprospec/rubric_tree.py` | `build_rubric_tree()` / `tree_score()` / `backfill_all()` / `attach_to_final_evaluation()` |
| `RUBRIC_TREE.json` | 每篇一份：root / branches / leaves / 挂载统计 / depth_max |
| `RUBRIC_TREE_SCORES.json` | `root_score / by_l1 / by_branch / failed_branches` |
| `FINAL_EVALUATION.json` | 新增 `rubric_tree` 字段；原 `evaluation / align_rubric / anchors` 原样保留 |
| `SAU_LIST.json` | 每条 SAU 回写 4 个树字段 |

命令：

```bash
.venv-linux/bin/python -m capfactory.reprospec.rubric_tree   # 全量回填
```

## 5. 实测（5 份已有报告）

| 论文 | 叶 | 分支 | 最大深度 | root_score | 失败分支 |
|---|---:|---:|---:|---:|---:|
| 2411.06608 (MolMiner) | 74 | 17 | 3 | 1.0 | 0 |
| regression/2411.06608 | 74 | 17 | 3 | 1.0 | 0 |
| regression/2302.09048 | 10 | 4 | 3 | 0.5 | 4 |
| regression/2405.03370 | 35 | 19 | 3 | 0.9412 | 2 |
| regression/2611.06237 | 61 | 26 | 3 | 0.982 | 1 |
| **合计** | **254** | — | — | — | — |

挂载率 **254/254 = 100%**。MolMiner 的父节点分布：
`algorithmstep: 25` / `algorithmmodule: 12` / `benchmark: 37`；
按 kind 深度：method/code_grounding/ordering 为 3，numeric/protocol 为 2。

失败分支示例（2302.09048, root=0.5）：

```
paper:2302.09048/algorithm:midi/algorithmmodule:2302.09048:mixed_noise_schedule
paper:2302.09048/algorithm:midi/algorithmmodule:2302.09048:regnn_layer
paper:2302.09048/algorithm:midi/algorithmmodule:2302.09048:transformer_denoising_network
paper:2302.09048/benchmark:kb:geom_drugs
```

这正是扁平列表给不了的粒度。

## 6. 与 PaperBench 的对照（现在的状态）

| | PaperBench | 本实现 |
|---|---|---|
| 层次 | 层次化树，任意深度 | 固定 3 层（根/L1/L2/叶），已够覆盖当前 6 类语义层 |
| 规模 | 8,316 项 / 20 篇 | 254 条 / 5 篇（全量 783 篇约 4 万条） |
| 来源 | 与作者人工共建 | 从图确定性自动编译，零 LLM |
| 打分 | LLM judge 逐叶 | 确定性 verdict 逐叶 + 树加权聚合 |
| 进图 | 不进图 | 单篇 `app_repro_runtime.json` 可挂 RubricNode；全量应用层图暂不常设 |

差异是刻意取舍：PaperBench 的 gold rubric 需要人工，本项目的优势是
「边际成本近零」，代价是深度固定、判定仍是确定性而非 LLM judge。

## 7. 后续

- 给 `TASK_SPECS["reproduction"]` 加 `RubricNode` + `HAS_SAU`，把树写进
  `app_repro_runtime.json`（当前树是独立 JSON 产物）；
- 全量编译 783 篇 ≈ 4 万叶，按 `paper_id + depth` 建索引；
- 接真实执行器后，`RUNSTATE.json` 记录 `failed_branches`，只重判子树；
- 叶判定从 dry 的「声明存在即 aligned」换成实跑/LLM judge 后，树评分才有
  复现质量含义（当前 regression 的 0.5 / 0.9412 已经体现出区分度）。

## 8. 附：当前复现流程是不是 PaperCoder 式「三阶段 + 专用智能体」

**结论：阶段划分形似，机制神不似。** 当前是**图驱动的门控流水线**，
不是「多智能体协作、自顶向下生成完整仓库」。

PaperCoder（蓝图 §1 ④）：
`Planning`（路线图 → 架构图 → 文件依赖 → 配置） →
`Analysis`（逐文件实现细节） →
`Generation`（按依赖顺序模块化生成代码），多智能体协作，**不执行、不 debug**。

我方 `capfactory/sciforge/repro/phasegraph.json` 的 R0–R6：

| 阶段 | 名称 | 产物 | 对应 PaperCoder |
|---|---|---|---|
| R0 | intake-paper | RUN_BUDGET / REPRO_SPEC | 输入准备 |
| R1 | resolve-method | METHOD_CARD / METHOD_LOCK / LINEAGE | ≈ Planning（方法规格） |
| R2 | ground-code | CODE_PLAN / STATIC_CHECKS | ≈ Planning（文件依赖）+ 部分 Analysis |
| R3 | bind-data | DATA_PLAN / SHAPE_PROBE | ≈ Analysis（数据/形状细节） |
| R4 | fix-metrics | METRIC_PLAN / SOTA_BASELINE / ALIGN_RUBRIC | ≈ Analysis（指标细节） |
| R5 | execute | RUNSTATE / events.ndjson / raw_results | **PaperCoder 没有**（它明确不执行） |
| R6 | verify-and-replay | REPRO_REPORT / REPRO_VERDICTS / SAU_VERDICTS | **PaperCoder 没有**（它不 debug） |

五个关键差别：

1. **没有专用智能体**。`repro/planner.py` 首行写「从 POGraph 节点属性 + 关系链生成
   ReproPlan（**不调 LLM、不编造**）」，`repro/runner.py` 写「规格层（只读图、**零 LLM**）」；
   `reprospec/compiler.py::compile_reprospec` 同样是确定性编译。没有 agent 角色、
   没有多轮协作、没有 LLM 生成实现细节。
2. **不生成完整仓库**。产物是 `REPRO_SCRIPT.py` / `MINIBATCH_SCRIPT.py` 这类
   **单篇复现脚本**，不是带目录结构、config、逐文件实现的仓库。
   `CODE_PLAN.json` 有「依赖有序模块图」的形状，但由 `HAS_MODULE` /
   `inputs→outputs` 依赖闭包确定性导出，不是 LLM 规划出来的架构图。
3. **执行与验证是我方的主干**（R5/R6），PaperCoder 恰好明确跳过这两步。
4. **驱动源不同**：PaperCoder 是「论文全文 → 自顶向下规划 → 生成」；
   我方是「已建好的语义层/应用层图 → 编译规格 → 门控执行 → 逐 SAU 判定」。
5. **更接近的参照**是蓝图里的 AutoReproduce（`<summary, code>` lineage 元组 +
   mixed-level rubric）与 SA-Bench（逐 SAU 判定），加上 Stage3 装配那套
   `PASS/PARTIAL/BLOCKED` 门与 `events.ndjson` durable truth。

所以「Planning / Analysis」的**职能**在 R1–R4 里能看到，
但「专用智能体 + 自顶向下生成代码」这套**机制**没有采用；
这也是本项目能与 783 篇全量抽取、确定性溯源闭环衔接的原因——
如果引入多智能体生成，溯源链会断在 LLM 的自由输出上。
补记：RubricNode + HAS_SAU 已加入 TASK_SPECS[reproduction]、REPRO_APP_CLASSES、REPRO_APP_RELATIONS；reprospec/rubric_runtime.py 把树编译进单篇 app_repro_runtime.json（5 篇共 88 分支节点 / 254 叶 / 254 条 HAS_SAU），application.py 保存后自动建树并 attach。三张全量图均 0 个 RubricNode。
另：本文 §7「后续」第 1 条（把树写进 app_repro_runtime.json）与 §4 代码表已按上述补记落地；全量编译 783 篇与 RUNSTATE 子树重跑仍待后续。
