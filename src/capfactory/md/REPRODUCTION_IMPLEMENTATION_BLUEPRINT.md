# GGR 实现蓝图：核心设计思路（P0-1 → P2-9 全量落地）

> 2026-11-14　本文汇总本轮全部实现的设计决策，供后续智能体接手时理解「为什么这样写」。
> 概念与文献依据见 `REPRODUCTION_APPLICATION_BLUEPRINT.md`；
> 应用层定位见 `APPLICATION_LAYER_DESIGN.md`；
> 验证口径见 `REPRODUCTION_EVALUATION_DESIGN.md`；
> 实测结果见 `REPRODUCTION_VALIDATION_REPORT.md`。

---

## 1. 一句话架构

**从语义层客观事实出发，编译可验证规格，在隔离工作区真跑，用逐条语义对齐判定代替「退出码 0 就算复现」。**

```
语义层(只读) → 任务派生层 → ReproSpec(71 SAU) → R0–R6 状态机
                                    ↓
                    REPRO_SCRIPT.py (独立可重跑)
                                    ↓
              raw_results → SAU 复判 → 三哈希锚 → 报告
```

---

## 2. 九个核心设计决策

### D1｜关系名单一真相源，而不是散落的字典

`phasegraph.json` 曾用 `REALIZED_BY`/`IMPLEMENTS_MODULE`（语义层根本不存在），
`planner.py` 又读 `relation_index.json` 的派生链名。`reprospec/relations.py`
把 **9 语义关系 + 9 应用关系 + 4 复现运行时关系**收在一处，历史别名只做
解析不回写，派生链单独登记。`validate_phasegraph()` 让 CI 能抓到任何新漂移。

### D2｜「升级 8 类」不能改既有 tbox 计数

`test_layered_tbox.py` 锁定应用层 8/9、legacy 46/105。直接塞类会让 798 项回归退化，
因此采用「**扩展声明 + 独立运行时图**」：`TaskSpec` 声明允许这些类，但挖掘器不产生它们；
`materialize_runtime_nodes()` 只写 `<run>/app_repro_runtime.json`，节点带
`layer/task/derived_from/miner/run_id`。

**并如实修正**：`reserved_status()` 实测只有 7 类真在 legacy reserved，
`EvaluationResult` 是 SA-Bench 逐 SAU 判定所需的**新增应用类**，没有伪装成升级。

### D3｜SAU 从图确定性编译，零 LLM

PaperBench 靠作者共建 8316 项 rubric、SA-Bench 人工标 1491 条 SAU，最贵的就是这步。
我方 2856 个 `AlgorithmModule` + 758 条代码落地边 + 604 个 `Benchmark` 让它可自动编译。
`compile_reprospec()` 只读图、不写图，`spec_hash` 幂等，每条 SAU 带
`source_node_ids`/`evidence_ids` 可回溯。

五类：`method / code_grounding / protocol / numeric / ordering`。

### D4｜真实数据缺陷必须修，不能绕过

实现时踩到三个坑，都固化成测试：
1. `inputs/outputs` 有时是中文字符串 `"分子片段"`，`set(map(str,...))` 会拆成
   `['分','子']` 产生虚假顺序依赖 → `_as_list()` 按分隔符切词。
2. O(n²) 依赖闭包在 14 模块上生成 44 条 ordering SAU → 每个 `after` 只留最近直接前驱（3 条）。
3. 剩余 3 条里出现 `Graph Encoder ↔ Hierarchical Decoder` 环 → DFS 环检测，
   环内降 `required=False`/`provenance=inferred` 并告警，避免 R6 拿矛盾门。

### D5｜dry 永远诚实，lite 才允许非 BLOCKED

`test_p1_repro.py:150` 锁定 dry 的 R6=BLOCKED。本轮所有改动都保持该行为：
P0-4 的 SAU 判定是**辅助证据**（`phasegraph.auxiliary.note` 明写不参与门）；
P1-5 只在 `effort ∈ {lite, full}` 且 `allow_execution=True` 时调用执行器；
P2-9 的语义门只在真跑成功时参与。

### D6｜执行的是「评测协议复现」，不是伪造训练

没有数据集/GPU/原仓库权重，因此**明确不做原论文完整训练复现**。
`REPRO_SCRIPT.py` 的输入是 `Benchmark.attrs.model_results`（PDF 表格原始抽取行），
独立实现 `normalize_model / normalize_metric_name / to_float / compute_sota`，
对照组是 `applayer/miner.py` 的 leaderboard 产物。两条不同代码路径一致 →
说明评测协议被正确复现；不一致 → 暴露抽取/归一缺陷。

脚本**不得**读 `LeaderboardEntry.value`/`sota_by_metric` 等期望值（防循环论证，
已写成测试断言）。out_of_scope 在报告里逐条列出。

### D7｜脚本生成必须是纯 stdlib 且可独立重跑

最初把 `json.dumps(...)` 直接嵌进 Python 源码，结果 `false`/`null` 触发
`NameError: name 'false' is not defined`。修法是把 JSON 文本作为字符串嵌入再
`json.loads(...)`（Artisan 式独立脚本）。执行前做 AST 安全检查：
import 白名单 + 禁止 `eval/exec/open/system/popen/run` 等裸名与属性调用。

另修相对路径 bug：`subprocess(cwd=run目录)` 时脚本路径必须 `.resolve()`，
否则工作区相对路径会失效（临时目录是绝对路径，早期测试没暴露）。

### D8｜失败修复是 `EDIT N M` 定点替换，不是整文件重生成

AutoReproduce 消融显示去掉 Debug+Refine 后 Perf Gap 从 19.72% 恶化到 88.78%。
`executor.py` 实现 `diagnose → make_patch → edit_lines(6,6) → 重跑`，
预算 `debug_tries ≤ 20`，每次写 `EDIT_LOG.jsonl` 与 events。
**能力由注入 `NameError` 的负例测试验证，生产路径 `debug_tries=0`** —— 不伪造失败。

### D9｜验证靠多重独立证据，不看单一分数

6 项主指标：`SAU_score / coverage / drift_rate / Exec Rate / Perf Gap / Symbol Recall`；
4 项辅助：`by_drift / Anchor Integrity / Align-Score(3 层) / API Recall`。
`unverified` 不进 `SAU_score` 分母、只影响 `coverage`；三哈希任一变化即判 drift；
双跑 `outputs_sha` 必须一致；S2 ladder 三态 Critic 且 ties fail。

---

## 3. 写权限矩阵（防止污染）

| 生产者 | 允许写 | 禁止写 |
|---|---|---|
| `semantic/` / `applayer/` | 图 | run 目录 |
| `compile_reprospec` | 只返回对象，可选写 `REPRO_SPEC.json` | 图（一个节点都不改） |
| `application.materialize_runtime_nodes` | `<run>/app_repro_runtime.json` | `app_reproduction.json` |
| `executor` | `REPRO_SCRIPT.py` / `raw_results.json` / `.repro/events.ndjson` / `EDIT_LOG.jsonl` | 图 |
| `runner` | `REPRO_VERDICTS.json` / `REPRO_REPORT.md` / `RUNSTATE.json` | 图 |
| `scoring` / `cli` | `FINAL_EVALUATION.json` / `ALIGN_RUBRIC.json` / `CLAIM_ANCHORS.json` / md 报告 | 图 |

`events.ndjson` 只有一份（`.repro/events.ndjson`），`RUNSTATE.json` 是它的派生快照。

---

## 4. 实现位置速查

| 阶段 | 文件 | 关键入口 |
|---|---|---|
| P0-1 关系统一 | `reprospec/relations.py` | `resolve_relation` / `validate_phasegraph` |
| P0-2 规格编译 | `reprospec/contract.py`, `compiler.py` | `compile_reprospec` |
| P0-3 运行时节点 | `reprospec/application.py` | `materialize_runtime_nodes` |
| P0-4 静态判定 | `reprospec/verdict.py` | `evaluate_sau` / `sau_drift_acceptable` |
| P1-5 真跑 | `reprospec/executor.py` | `execute_repro` / `edit_lines` |
| P1-6 阶梯 | `reprospec/ladder.py` | `run_ladder` / `decide` |
| P1-7 探针 | `reprospec/probe.py` | `write_probes` |
| P2-8 评分锚定 | `reprospec/scoring.py` | `finalize` / `claim_anchors` |
| P2-9 门与 CLI | `sciforge/repro/runner.py`, `reprospec/cli.py` | `run_repro` / `main` |
| 测试 | `tests/Phase/test_reprospec.py`, `test_repro_p03_p04.py`, `test_repro_p1_p2.py` | 76 项 |

---

## 5. 实测结果摘要（MolMiner `2411.06608`）

| 项 | dry | P2-9 lite（原图） | P3 lite（strict 归一化视图） |
|---|---:|---:|---:|
| SAU_score | 0.8947 | 0.9420 | **1.0** |
| coverage | 0.5352 | 0.9718 | **1.0** |
| drift_rate | 0.1053 | 0.0580 | **0.0** |
| numeric unverified | 31 | 0 | **0** |
| ordering unverified | 2 | 2 | **0** |
| R6 verdict | BLOCKED | PASS | **PASS** |
| overall（门链 / 最终评估） | BLOCKED / — | PARTIAL / PARTIAL | **PASS / PASS** |
| mini-batch runtime_verified | — | — | **6/6** |
| residual unknown_forms | — | 4 | **0** |

P2-9 的 `PARTIAL` 来自 4 条 `method` SAU（缺 `MODULE_IMPLEMENTED_BY`）。P3-1 诊断后发现
其中 1 个模块属于另一篇论文 `2608.06956`，另外 2 条 ordering 环也源于同批跨论文模块，
因此**不能盲目补 4 条边**：改为范围归一化（剔除 4 个跨论文模块 + 3 个误挂基线算法）
+ 6 条带 `purpose` 文本证据的补边，全部记在 `NORMALIZATION.json`，源图文件不变。

完整报告：`REPRODUCTION_VALIDATION_REPORT.md`；多篇回归：`REPRODUCTION_REGRESSION_REPORT.md`；
训练复现设计：`FULL_TRAIN_REPRODUCTION_DESIGN.md`。

---

## 6. 已知限制（P3 之后更新）

| # | 状态 | 说明 |
|---|---|---|
| 1 | **已解决** | 4 条 `method mismatch` 经归一化 + 证据化补边清零；补边标 `analyst_inference`，与 AST 边区分 |
| 2 | **已解决** | 2 条 ordering 环来自跨论文自编码模块，scope 隔离后消失；余下 9 条声明顺序为 `aligned` 但带 `declaration_only` / `execution_unverified` |
| 3 | **已解决** | P3-2 真实 mini-batch 子进程实测 6/6 `runtime_verified`；4 处表单来自同族继承并标 `paper_declared=False` |
| 4 | **已解释** | lineage 0/3 逐字证据：`SourcePaper.title` 是书目证据不是 `quote`；P3-3 分级为 3 条 bibliographic，并给出 `SUPPORTED_BY → Evidence.quote` 修复路径 |
| 5 | **仍存在** | 不做原论文模型训练复现：GPU 有 3×H100，但 torch/NCCL 不兼容、无 rdkit、数据集与训练配置未就绪。见 `FULL_TRAIN_REPRODUCTION_DESIGN.md` |
| 6 | **仍存在** | Align-Score 是确定性规则实现，未调 LLM judge |
| 7 | **仍存在** | 双跑在 CLI 层做，`anchor_integrity` 基于首次执行 |
| 8 | **仍存在** | Web 复现任务页未实现 |
| 9 | **仍存在** | `--effort full` 目前只生成训练计划，未接真实训练执行器（刻意保留的诚实状态） |

---

## 7. 下一步建议（按价值排序）

| 优先级 | 任务 | 状态 | 实测结果 |
|---|---|---|---|
| P3-1 | 补齐 4 个 `AlgorithmModule` 的 `MODULE_IMPLEMENTED_BY` 边 | **完成（改为范围归一化）** | drift_rate 0，门链 overall PASS |
| P3-2 | shape probe 改成真实 mini-batch 执行 | **完成** | 6/6 runtime_verified，unknown 4→0 |
| P3-3 | lineage 补 `Evidence.quote` | **完成（分级 + 修复路径）** | 0 verbatim / 3 bibliographic，如实报告 |
| P3-4 | 多篇回归 | **完成** | 4 篇：PASS / PARTIAL(R4) / BLOCKED(R0,R2 无仓库) / BLOCKED(R4) |
| P4-1 | 隔离 venv 修 torch+NCCL，装 rdkit | 待执行 | 设计见训练文档 §3 |
| P4-2 | 镜像下载数据集到 `/home/zengshuxin/data` | 待执行 | 布局/命令见训练文档 §4 |
| P4-3 | 固定原仓库 commit 与 14 项训练配置 | 待执行 | `TRAIN_PLAN.config={}` |
| P4-4 | 实现 `effort=full` 真实训练执行器 | 待实现 | 训练文档 §8 |
| P4-5 | 六哈希 ClaimAnchor + 动态 out_of_scope | 待实现 | 训练文档 §7 |
| P3-5 | Web 复现任务页 + SAU 检查单 | 未开始 | 人可读 |
| P3-6 | 接 LLM judge 做 mixed-level 复核 | 未开始 | 对齐文献口径 |

---

## 8. 复现本次验证

```bash
cd /home/zengshuxin/xKG-main/xKG-main
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
    --arxiv 2411.06608 --effort lite \
    --out storage_cf/repro_runs \
    --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md

PYTHONPATH=. python3 -m unittest discover -s tests/Phase -p "test_*.py"
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py"
PYTHONPATH=. python3 deploy/smoke_test.py
```
