# 论文复现效果验证方案

> 2026-11-14　配套 `APPLICATION_LAYER_DESIGN.md` 与 `REPRODUCTION_APPLICATION_BLUEPRINT.md`
> 本文定义「怎么算复现成功」、指标口径、判定矩阵、防作弊条款与报告规范。
> 最终实测结果写入 `capfactory/md/REPRODUCTION_VALIDATION_REPORT.md`。

---

## 0. 核心原则：先说清楚验证的是什么

文献（SA-Bench 2608.24252）证明：**能跑 ≠ 复现**。最强配置 SAU 得分仅
0.301/1.0，零分主因是 `implementation mismatch` 与 `stub`。因此本方案的验证
不能是"脚本退出码 0 就 PASS"。

同时必须诚实承认算力边界：当前没有原论文数据集、GPU 权重与完整训练环境，
**不做原论文完整训练复现**。本系统验证的是下面三层，每层都明确标注可判定范围：

| 层 | 验证内容 | 数据来源 | 对应文献 |
|---|---|---|---|
| **L1 规格对齐** | 论文里声明的方法/模块/符号/数据契约/数值，是否被结构化地、可追溯地表示 | 语义层图 + ReproSpec 的 5 类 SAU | PaperBench rubric / SA-Bench SAU |
| **L2 评测协议复现** | 独立脚本从论文表格的**原始抽取行**重算榜单/SOTA/方向/单位，是否与另一条管线（应用层 `LeaderboardEntry`）一致 | `Benchmark.model_results` → `REPRO_SCRIPT.py` | CORE-Bench / Artisan reproduction script |
| **L3 方法可执行性** | 方法模块链能否按 `code_plan.order` 顺序执行、每个符号是否落地、是否 stub | AST `CodeFunction` + 生成的模块函数 | Sci-Replicator reasoning graph / AutoP2C |

**明确不验证**：模型训练精度、原论文实验全量表、跨数据集泛化。
这些在报告里统一标为 `out_of_scope`，不得混进总分。

**L2 的独立性说明（防止"自己验自己"）**：
- 输入 = `Benchmark.attrs.model_results`（PDF 表格经 `table_extract` 得到的原始行，客观事实）
- 脚本 = 独立实现的 `normalize_metric_name / to_float / direction_of / compute_sota`
- 对照组 = 应用层 `LeaderboardEntry`（由 `applayer/miner.py` 的 `leaderboard` 挖掘器产生）
- 两条**不同代码路径**算出的值一致 → 说明评测协议被正确复现；不一致 → 暴露抽取/归一缺陷
- 脚本**不得**把 `LeaderboardEntry.value` 当输入或输出（防循环论证）

---

## 1. 指标体系

### 1.1 主指标（6 项）

| 指标 | 定义 | 取值范围 | 数据来源 |
|---|---|---|---|
| `SAU_score` | `aligned / decidable`，`decidable = 总 SAU − unverified` | 0–1 | `SAU_VERDICTS.json` |
| `coverage` | `decidable / 总 SAU` | 0–1 | 同上 |
| `drift_rate` | `(mismatch + stub + absent) / decidable` | 0–1 | 同上 |
| `Exec Rate` | 成功产出 `raw_results.json` 的实验次数 / 尝试次数 | 0–1 | `events.ndjson` |
| `Perf Gap` | `(1/n)Σ|V_ref − V_run| / max(|V_ref|, |V_run|, ε)` | ≥0 | `S2_LADDER.json` |
| `Symbol Recall` | 命中的 `CodeFunction` 数 / method SAU 数 | 0–1 | `code_plan` + `code_grounding` SAU |

### 1.2 辅助指标（4 项）

| 指标 | 说明 |
|---|---|
| `by_drift` | 四类语义漂移分布：numerical / methodological / protocol / ordering（SA-Bench 口径） |
| `Anchor Integrity` | `code_sha` / `inputs_sha` / `outputs_sha` 三哈希一致且双跑一致 |
| `Align-Score` | 三层：paper-level（5 个关键点）/ code-level（4 维×25 分）/ mixed-level（联合，与人类相关性 0.81–0.83，以它为主） |
| `API Recall` | 仓库依赖/符号检索命中率（Sci-Replicator 口径） |

### 1.3 为什么 `unverified` 不进分母

dry 模式有 31 条 numeric SAU 无实跑值。若把它们算作失败，`SAU_score` 会被
无意义地压低；若算作成功，就是造假。因此：
- `unverified` 单独统计，只影响 `coverage`
- `coverage < 0.5` 时最终判定**不得高于 PARTIAL**
- 报告必须逐条列出 unverified 的原因（无实跑值 / 环依赖 / 声明顺序）

---

## 2. 判定矩阵

### 2.1 逐 SAU 判定（5 态）

| 状态 | 含义 | 计入 drift |
|---|---|---|
| `aligned` | 静态/数值证据与规格一致 | 否 |
| `mismatch` | 有实现但与规格不符 | 是 |
| `stub` | 空实现 / TODO / placeholder | 是 |
| `absent` | 节点或字段缺失 | 是 |
| `unverified` | 需要执行或人工才能判 | 否，只影响 coverage |

### 2.2 阶段门（R0–R6）

| 门 | PASS 条件 | 失败动作 |
|---|---|---|
| `paper_core_present` | `research_problem` + `domain` 非空 | BLOCKED |
| `method_grounded` | 有 `PROPOSES_METHOD` 且每个方法有 `mechanism` | PARTIAL/BLOCKED |
| `code_located` | 有算法→代码链 | BLOCKED（L1 回退 R2，预算 1） |
| `data_bound` | 有可用 `Benchmark` 且 input/output_form 齐 | PARTIAL |
| `metrics_comparable` | 指标 direction ∈ {min,max} 且非启发式 | PARTIAL（启发式需人工） |
| `verdicts_valid` | R0–R5 verdict 均合法；**lite 时**额外要求执行成功 + ladder 通过 | BLOCKED |
| `reproduction_close` | `rows` 非空，且每条偏差 ≤ 5% | **dry 无 rows → BLOCKED**；有偏差 → PARTIAL（L2 回退 R5，预算 1） |

### 2.3 最终判定（`overall`）

```
BLOCKED  任一阶段 BLOCKED  /  Exec Rate = 0
PARTIAL  SAU_score ≥ 0.8 且 drift_rate ≤ 0.20 且 coverage ≥ 0.50
         且 Anchor Integrity = True 且 无阶段 BLOCKED
         但存在：启发式方向 / 未解决环 / 人工确认项 / L2 小偏差
PASS     上述全部满足，且 coverage ≥ 0.90、drift_rate ≤ 0.05、
         三哈希双跑一致、Align_mixed ≥ 0.80
否则     PARTIAL（附 reasons），绝不低于 BLOCKED 的诚实底线
```

**硬约束**：`dry` 模式永远 BLOCKED；只有 `effort ∈ {lite, full}` 且
`REPRO_SCRIPT.py` 真的被 subprocess 执行过，才允许非 BLOCKED。

---

## 3. 验证流程（8 步）

```
V1  固定基线
    记录 semantic 6001/7460、app 8300/10260、spec_hash、代码 commit/时间
    跑一次 dry，确认 R6=BLOCKED 且 31 条 numeric=unverified（防回归）

V2  编译规格
    compile_reprospec(paper_id) → 71 条 SAU、5 类计数、spec_hash 稳定

V3  静态判定（离线可复算）
    evaluate_sau(spec, graph, results=None)
    预期：method 10 aligned / 4 mismatch，code 17 aligned，
          protocol 6 aligned，numeric 31 unverified，ordering 1 aligned + 2 unverified
    这一步是「不依赖执行也能发现的问题清单」

V4  生成独立可重跑脚本
    REPRO_SCRIPT.py 只依赖 stdlib；输入 FIXTURE = 论文表格原始行；
    逐模块函数按 code_plan.order 串行；输出单一 JSON 到 stdout

V5  沙箱执行 + 调试循环
    subprocess（隔离 env、cwd=run 目录、timeout 60s）
    失败 → 解析 traceback → EDIT N M 定点替换 → 重跑（debug_tries ≤ 20）
    每次写 events.ndjson 与 EDIT_LOG.jsonl

V6  阶梯与三态 Critic
    subset（少量行）复现 baseline → candidate → GOOD/ENGINEER(≤2)/BAD
    GOOD 才进 full；full 必须严格优于（ties fail）

V7  结果回填与复判
    raw_results → results 映射（宿主按 (benchmark,model,metric) 对齐 entry_id）
    重新 evaluate_sau(spec, graph, results=...)
    numeric 从 unverified → aligned/mismatch
    计算 SAU_score / coverage / drift_rate / Perf Gap

V8  锚定与报告
    三哈希（code/inputs/outputs）+ 双跑一致性
    Align-Score 三层 → ALIGN_RUBRIC.json
    汇总 → REPRO_REPORT.md → capfactory/md/REPRODUCTION_VALIDATION_REPORT.md
```

---

## 4. 黄金用例与预期

### 4.1 MolMiner `2411.06608`（主用例）

| 项 | 基线（P0-4 实测） | lite 预期 |
|---|---|---|
| SAU 总数 | 71 | 71 |
| method | 10 aligned / 4 mismatch | 不变（静态） |
| code_grounding | 17 aligned | 不变 |
| protocol | 6 aligned | 6 aligned + shape_probe 有值 |
| numeric | **31 unverified** | 31 aligned 或少量 mismatch（取决于两条管线是否一致） |
| ordering | 1 aligned / 2 unverified | 不变（环保留） |
| `SAU_score` | 0.8947 | ≥ 0.89 |
| `coverage` | 0.5352 | ≈ 0.97（仅 2 条环仍 unverified） |
| `drift_rate` | 0.1053 | ≤ 0.11 |
| R6 dry | BLOCKED | lite → PASS / PARTIAL |

### 4.2 负例（必须能识别）

| 负例 | 期望 |
|---|---|
| 把某个 `CodeFunction.purpose` 改成 `TODO: implement` | 对应 SAU 判 `stub`，drift +1 |
| 删掉一条 `MODULE_IMPLEMENTED_BY` | 对应 method SAU 判 `mismatch` |
| 篡改 `raw_results.json` 一个数值 | `outputs_sha` 变化 → Anchor Integrity=False |
| 让脚本抛 `NameError` | EDIT 循环应修复；修不好则 Exec Rate<1、整体 BLOCKED |
| dry 传 `results` 伪造值 | 判定层应拒绝（effort 与 events 交叉校验） |

### 4.3 多篇回归（P2）

至少 3 篇：有代码仓库的、无仓库的、表格结构异常的。
批量报告给出每篇的 6 项主指标与失败归因分布。

---

## 5. 防作弊条款（硬性）

1. **不许抄期望值**：`REPRO_SCRIPT.py` 的输入只能是 `model_results` 原始行，
   不得读取 `LeaderboardEntry` / `sota_by_metric` / `REPRO_SPEC.json` 的期望值字段
2. **dry 不许伪装**：`results` 非空但 `effort="dry"` 或 `events` 无 `exec` 事件 → 判 BLOCKED
3. **双跑一致**：同一 `spec_hash` 连续跑两次，`outputs_sha` 必须一致
4. **三哈希绑定变更**：`code_sha / inputs_sha / outputs_sha` 任一变化，
   `CLAIM_ANCHORS.json` 标 `drift`，历史报告的结论作废
5. **判定与执行分离**：`evaluate_sau` 不得调用执行器；执行器不得写 SAU verdict
6. **环依赖降级**：ordering 环不得被算作 aligned，只能 `unverified`
7. **ties fail**：full 阶段与 baseline 打平不算赢（SciForge S2 硬规则）
8. **失败可追溯**：每次 EDIT 必须记 `EDIT_LOG.jsonl`（行号区间 + 原因 + 新代码哈希）
9. **报告不得省略 out_of_scope**：训练精度未验证必须显式写出
10. **不因测试变绿而放宽门**：`test_p1_repro.py:150` 的 dry BLOCKED 断言必须保持

---

## 6. 报告规范

### 6.1 run 目录产物（`storage_cf/repro_runs/<aid>/`）

| 文件 | 内容 |
|---|---|
| `REPRO_SPEC.json` / `SAU_LIST.json` | 规格与逐条 SAU |
| `REPRO_SCRIPT.py` | 可独立重跑的纯 stdlib 脚本 |
| `raw_results.json` | 脚本 stdout 的结构化结果 |
| `S2_LADDER.json` | subset/full 两阶段 + 三态 Critic |
| `EDIT_LOG.jsonl` | 每次定点修复 |
| `events.ndjson` / `RUNSTATE.json` | durable truth + 派生快照 |
| `SHAPE_PROBE.json` / `LINEAGE.json` | P1-7 结果 |
| `SAU_VERDICTS.json` | 逐条判定 + 汇总 |
| `ALIGN_RUBRIC.json` | 三层对齐评分 |
| `CLAIM_ANCHORS.json` | 三哈希 + drift |
| `app_repro_runtime.json` | 8 类运行时节点（独立图） |
| `REPRO_VERDICTS.json` / `REPRO_REPORT.md` | 门判定与人读报告 |

### 6.2 汇总报告（`capfactory/md/REPRODUCTION_VALIDATION_REPORT.md`）

必须包含 7 节：
1. **验证范围与边界**（含 out_of_scope 明确声明）
2. **环境基线**（Python/Docker/图规模/spec_hash/代码版本/时间）
3. **主指标表**（6 项主指标 + 4 项辅助，dry→lite 前后对照）
4. **逐类 SAU 判定**（5 类 × 5 态矩阵，含 mismatch 归因）
5. **执行证据**（脚本路径、命令、退出码、耗时、debug_tries、events 条数、三哈希）
6. **失败与漂移归因**（哪些 SAU 未对齐、为什么、是否 out_of_scope）
7. **结论与可复现命令**（一条命令重跑本次验证）

---

## 7. 与门系统的关系

- `SAU_score` / `drift_rate` **先作为辅助证据**（P0-4 已实现），
  P2-9 才接进 `reproduction_close` 成为正式门
- 接线前必须保证：lite 真跑能稳定产出 `rows`，否则门会把所有合法 run 判 BLOCKED
- 接线后保留 dry 分支不动；`sau_drift_acceptable()` 只在
  `effort ∈ {lite, full}` 且 `Exec Rate = 1` 时参与
- 任何门改动都要跑 `tests/test_p1_repro.py` 确认 dry 仍 BLOCKED

---

## 8. 持续验证（回归）

```bash
cd /home/zengshuxin/xKG-main/xKG-main

# 单元测试：规格/判定/执行/阶梯/评分
PYTHONPATH=. python3 -m unittest discover -s tests/Phase -p "test_*.py"

# 全仓回归
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py"

# 端到端 lite 验证（产出汇总报告）
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
    --arxiv 2411.06608 --effort lite \
    --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md

# 负例注入（验证判定层能抓到 drift）
PYTHONPATH=. python3 tests/Phase/test_repro_evaluation.py
```

**验收门槛**：全仓 798+ 项测试全绿、冒烟 60/60、MolMiner lite 产出
`coverage ≥ 0.90` 且 `Anchor Integrity=True`，报告 7 节齐全。
