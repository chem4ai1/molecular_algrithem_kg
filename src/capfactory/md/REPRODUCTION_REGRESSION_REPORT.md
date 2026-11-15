# 论文复现实际验证报告

> 生成时间：2026-11-14 20:58:13　生成命令：`python3 -m capfactory.reprospec.cli --effort lite`

## 1. 验证范围与边界

本验证覆盖三层（见 `REPRODUCTION_EVALUATION_DESIGN.md` §0）：

| 层 | 内容 |
|---|---|
| L1 规格对齐 | 方法/模块/符号/数据契约/数值是否被结构化且可追溯地表示 |
| L2 评测协议复现 | 独立脚本从论文表格原始行重算榜单/SOTA/方向，与另一条管线的应用层榜单行比对 |
| L3 方法可执行性 | 方法模块链按 code_plan.order 执行、符号落地、无 stub |

**明确不验证（out_of_scope）**：本轮 lite 不训练模型；原论文模型训练精度、原论文实验全量表、跨数据集泛化均不在本次验证范围。训练复现可行性（`effort=full`）见 `TRAIN_FEASIBILITY.json` 与 `FULL_TRAIN_REPRODUCTION_DESIGN.md`。

**L2 独立性**：脚本输入是 `Benchmark.attrs.model_results`（PDF 表格原始抽取行），脚本独立实现 `normalize_model / normalize_metric_name / to_float / compute_sota`；对照组是 `applayer/miner.py` 的 leaderboard 挖掘器产物。脚本不读取 `LeaderboardEntry.value` 或 `sota_by_metric` 等期望值。

## 2. 环境基线

| 项 | 值 |
|---|---|
| Python | 3.12.7 |
| 平台 | Linux-7.0.0-28-generic-x86_64-with-glibc2.39 |
| 执行隔离 | 子进程 + env 白名单 + AST import 白名单 + 超时 |
| 图 `storage_cf/sciforge/app_reproduction.json` | 8300 节点 / 10260 断言 |
| run `storage_cf/repro_runs/regression/2411.06608` | arxiv=2411.06608 effort=lite |
| P3-1 scope | `strict`（源图 10260 断言 → 归一化视图 10259 断言，源图文件不变） |
| spec_hash | `sha256:b3562d3f03436c3299655e49c…` |
| 图 `storage_cf/sciforge/app_reproduction.json` | 8300 节点 / 10260 断言 |
| run `storage_cf/repro_runs/regression/2405.03370` | arxiv=2405.03370 effort=lite |
| P3-1 scope | `strict`（源图 10260 断言 → 归一化视图 10260 断言，源图文件不变） |
| spec_hash | `sha256:1800f74ed5b5af74c8b87c7ee…` |
| 图 `storage_cf/sciforge/app_reproduction.json` | 8300 节点 / 10260 断言 |
| run `storage_cf/repro_runs/regression/2302.09048` | arxiv=2302.09048 effort=lite |
| P3-1 scope | `strict`（源图 10260 断言 → 归一化视图 10258 断言，源图文件不变） |
| spec_hash | `sha256:9443990977927f9e9756e4413…` |
| 图 `storage_cf/sciforge/app_reproduction.json` | 8300 节点 / 10260 断言 |
| run `storage_cf/repro_runs/regression/2611.06237` | arxiv=2611.06237 effort=lite |
| P3-1 scope | `strict`（源图 10260 断言 → 归一化视图 10260 断言，源图文件不变） |
| spec_hash | `sha256:39039fea33a1d3bb5cbefba14…` |

## 3. 主指标表（dry 基线 → lite 实测）

> dry 基线取自 P0-4 阶段实测记录（`tests/Phase/test_repro_p03_p04.py`，legacy 图 71 条 SAU）；lite 列为 `strict` 归一化视图（74 条 SAU）的真实执行结果。两者 spec 集合不同，此表用于趋势对照，不是同一 SAU 集合的逐条对比。

| 指标 | dry 基线 | lite 实测 | 说明 |
|---|---:|---:|---|
| SAU_score | 0.8947 | 1.0 | aligned/decidable |
| coverage | 0.5352 | 1.0 | decidable/total |
| drift_rate | 0.1053 | 0.0 | 漂移占比 |
| Exec Rate | 0.0 | 1.0 | 真跑成功比例 |
| Perf Gap | — | 0.0 | 相对偏差 |
| Symbol Recall | — | 1.0 | 代码符号命中 |
| Align_mixed | — | 100.0 | 混合级对齐 |
| Anchor Integrity | — | True | 三哈希 + 双跑 |
| SAU_score | 0.8947 | 0.9429 | aligned/decidable |
| coverage | 0.5352 | 1.0 | decidable/total |
| drift_rate | 0.1053 | 0.0571 | 漂移占比 |
| Exec Rate | 0.0 | 1.0 | 真跑成功比例 |
| Perf Gap | — | 0.0 | 相对偏差 |
| Symbol Recall | — | 1.0 | 代码符号命中 |
| Align_mixed | — | 98.8 | 混合级对齐 |
| Anchor Integrity | — | True | 三哈希 + 双跑 |
| SAU_score | 0.8947 | 0.6667 | aligned/decidable |
| coverage | 0.5352 | 0.9 | decidable/total |
| drift_rate | 0.1053 | 0.3333 | 漂移占比 |
| Exec Rate | 0.0 | 1.0 | 真跑成功比例 |
| Perf Gap | — | 0.0 | 相对偏差 |
| Symbol Recall | — | 0.0 | 代码符号命中 |
| Align_mixed | — | 70.5 | 混合级对齐 |
| Anchor Integrity | — | True | 三哈希 + 双跑 |
| SAU_score | 0.8947 | 0.9836 | aligned/decidable |
| coverage | 0.5352 | 1.0 | decidable/total |
| drift_rate | 0.1053 | 0.0164 | 漂移占比 |
| Exec Rate | 0.0 | 1.0 | 真跑成功比例 |
| Perf Gap | — | 0.0 | 相对偏差 |
| Symbol Recall | — | 0.8 | 代码符号命中 |
| Align_mixed | — | 98.8 | 混合级对齐 |
| Anchor Integrity | — | True | 三哈希 + 双跑 |

## 4. 逐类 SAU 判定

| kind | aligned | mismatch | stub | absent | unverified |
|---|---:|---:|---:|---:|---:|
**2411.06608**（74 条 SAU / decidable 74 / score 1.0）

| method | 10 | 0 | 0 | 0 | 0 |
| code_grounding | 18 | 0 | 0 | 0 | 0 |
| protocol | 6 | 0 | 0 | 0 | 0 |
| numeric | 31 | 0 | 0 | 0 | 0 |
| ordering | 9 | 0 | 0 | 0 | 0 |

**2405.03370**（35 条 SAU / decidable 35 / score 0.9429）

| method | 9 | 2 | 0 | 0 | 0 |
| code_grounding | 16 | 0 | 0 | 0 | 0 |
| protocol | 3 | 0 | 0 | 0 | 0 |
| numeric | 3 | 0 | 0 | 0 | 0 |
| ordering | 2 | 0 | 0 | 0 | 0 |

**2302.09048**（10 条 SAU / decidable 9 / score 0.6667）

| method | 0 | 3 | 0 | 0 | 0 |
| code_grounding | 0 | 0 | 0 | 0 | 0 |
| protocol | 1 | 0 | 0 | 0 | 0 |
| numeric | 3 | 0 | 0 | 0 | 1 |
| ordering | 2 | 0 | 0 | 0 | 0 |

**2611.06237**（61 条 SAU / decidable 61 / score 0.9836）

| method | 4 | 1 | 0 | 0 | 0 |
| code_grounding | 4 | 0 | 0 | 0 | 0 |
| protocol | 21 | 0 | 0 | 0 | 0 |
| numeric | 30 | 0 | 0 | 0 | 0 |
| ordering | 1 | 0 | 0 | 0 | 0 |

## 5. 执行证据

### 2411.06608

- 脚本：`storage_cf/repro_runs/regression/2411.06608/REPRO_SCRIPT.py`（纯 stdlib，可独立重跑）
- 执行：{'ok': True, 'status': 'PASS', 'debug_tries': 0, 'duration_s': 0.054, 'n_rows': 31}
- S2 ladder：`PASS` / critic `GOOD` / strict_full=True
- 事件条数：`52`（`storage_cf/repro_runs/regression/2411.06608/.repro/events.ndjson`）
- 三哈希：code `sha256:f0c6bcc6ac2cc…` / inputs `sha256:0cc27f17c0f59…` / outputs `sha256:3c52210b08d10…`
- 双跑一致：`True`（second `sha256:3c52210b08d10…`）

### 2405.03370

- 脚本：`storage_cf/repro_runs/regression/2405.03370/REPRO_SCRIPT.py`（纯 stdlib，可独立重跑）
- 执行：{'ok': True, 'status': 'PASS', 'debug_tries': 0, 'duration_s': 0.052, 'n_rows': 3}
- S2 ladder：`PASS` / critic `GOOD` / strict_full=True
- 事件条数：`52`（`storage_cf/repro_runs/regression/2405.03370/.repro/events.ndjson`）
- 三哈希：code `sha256:512467906c218…` / inputs `sha256:6f762aa5c04a0…` / outputs `sha256:01cff95cf0e05…`
- 双跑一致：`True`（second `sha256:01cff95cf0e05…`）

### 2302.09048

- 脚本：`storage_cf/repro_runs/regression/2302.09048/REPRO_SCRIPT.py`（纯 stdlib，可独立重跑）
- 执行：{'ok': True, 'status': 'PASS', 'debug_tries': 0, 'duration_s': 0.048, 'n_rows': 3}
- S2 ladder：`PASS` / critic `GOOD` / strict_full=True
- 事件条数：`52`（`storage_cf/repro_runs/regression/2302.09048/.repro/events.ndjson`）
- 三哈希：code `sha256:8e9e377fa4cd3…` / inputs `sha256:a00ad8918e422…` / outputs `sha256:d638ca56f2be0…`
- 双跑一致：`True`（second `sha256:d638ca56f2be0…`）

### 2611.06237

- 脚本：`storage_cf/repro_runs/regression/2611.06237/REPRO_SCRIPT.py`（纯 stdlib，可独立重跑）
- 执行：{'ok': True, 'status': 'PASS', 'debug_tries': 0, 'duration_s': 0.043, 'n_rows': 30}
- S2 ladder：`PASS` / critic `GOOD` / strict_full=True
- 事件条数：`52`（`storage_cf/repro_runs/regression/2611.06237/.repro/events.ndjson`）
- 三哈希：code `sha256:f9ea11ae3d436…` / inputs `sha256:92d17f43a694c…` / outputs `sha256:8dc1985517e67…`
- 双跑一致：`True`（second `sha256:8dc1985517e67…`）

## 6. 失败与漂移归因

### 2411.06608

- 最终判定：**PASS**
- 漂移分布：`{'numerical': 0, 'methodological': 0, 'protocol': 0, 'ordering': 0}`
- 降级原因：无
- unverified 0 条（原因示例）：
- 数据缺口（P1-7 静态词表口径）：shape 未登记形式 4 处；lineage 带逐字证据 0/3 条
- P3-1 范围归一化：剔除跨论文模块 4 个、误挂基线算法 3 个，共删边 7 条（跨论文 `HAS_MODULE` + 基线算法 `PROPOSES_METHOD`）；证据化补 `MODULE_IMPLEMENTED_BY` 边 6 条；无可证据化映射而保持缺口的模块 0 个
  - 补边 `fragment_coarse_graining` → `get_all_possible_attachments`，命中 ['grain', 'attachment']；证据 purpose=「Compute all possible attachment points for a grain」（purpose_keyword_inference (非 AST 直接落地)）
  - 补边 `fragment_coarse_graining` → `compute_possible_remaps`，命中 ['remap']；证据 purpose=「Compute all valid remappings between atoms in two equivalent molecules」（purpose_keyword_inference (非 AST 直接落地)）
  - 补边 `fragment_coarse_graining` → `get_canonicalization_map`，命中 ['remap', 'canonicalization']；证据 purpose=「Return a canonical remapping from the list of possible remaps」（purpose_keyword_inference (非 AST 直接落地)）
  - 补边 `fragment_predictor` → `init`，命中 ['starter']；证据 purpose=「Initialize and load pretrained components: MolMiner, FragmentStarter, 」（purpose_keyword_inference (非 AST 直接落地)）
  - 补边 `fragment_predictor` → `sample`，命中 ['seed']；证据 purpose=「Core sampling routine: seed selection + autoregressive fragment genera」（purpose_keyword_inference (非 AST 直接落地)）
  - 补边 `conditional_sampling` → `init`，命中 ['gmm']；证据 purpose=「Initialize and load pretrained components: MolMiner, FragmentStarter, 」（purpose_keyword_inference (非 AST 直接落地)）
- P3-2 真实 mini-batch 实测（batch_size=4）：6/6 个探针 runtime_verified，同族继承表单 4 处，残留 unknown 0 处；脚本 `MINIBATCH_SCRIPT.py` 可独立重跑
  - 表单继承 `benchmark:canonical:zinc` 的 `input_form`：unknown → `SMILES`（exact_label，来源 `benchmark:zinc`，非论文原文声明）
  - 表单继承 `benchmark:canonical:zinc` 的 `output_form`：unknown → `SMILES`（exact_label，来源 `benchmark:zinc`，非论文原文声明）
  - 表单继承 `benchmark:targeted_multi_property` 的 `input_form`：unknown → `向量`（label_prefix，来源 `benchmark:targeted_generation`，非论文原文声明）
  - 表单继承 `benchmark:targeted_multi_property` 的 `output_form`：unknown → `SMILES`（label_prefix，来源 `benchmark:targeted_generation`，非论文原文声明）
- P3-3 lineage 证据分级：逐字引文 0/3 条，书目证据 3 条，完全无证据 0 条；标题不是 quote，故 0 条属实。修复路径：Stage2/Stage3 抽取 related_work 段落时保存引文原句，建成 Evidence(kind='citation', quote=...) 并以 SUPPORTED_BY 连到 SourcePaper；本模块会自动升级为

### 2405.03370

- 最终判定：**PARTIAL**
- 漂移分布：`{'numerical': 0, 'methodological': 2, 'protocol': 0, 'ordering': 0}`
- 降级原因：['drift_rate 0.0571 > 0.05']
  - `sau:240503370:method:001` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
  - `sau:240503370:method:002` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
- unverified 0 条（原因示例）：
- 数据缺口（P1-7 静态词表口径）：shape 未登记形式 4 处；lineage 带逐字证据 0/3 条
- P3-1 范围归一化：剔除跨论文模块 0 个、误挂基线算法 0 个，共删边 0 条（跨论文 `HAS_MODULE` + 基线算法 `PROPOSES_METHOD`）；证据化补 `MODULE_IMPLEMENTED_BY` 边 0 条；无可证据化映射而保持缺口的模块 2 个
- P3-2 真实 mini-batch 实测（batch_size=4）：1/3 个探针 runtime_verified，同族继承表单 2 处，残留 unknown 4 处；脚本 `MINIBATCH_SCRIPT.py` 可独立重跑
  - 表单继承 `benchmark:canonical:antibody_cdrh3_test_set` 的 `input_form`：unknown → `蛋白口袋+配体`（exact_label，来源 `benchmark:antibody_cdrh3_test_set`，非论文原文声明）
  - 表单继承 `benchmark:canonical:antibody_cdrh3_test_set` 的 `output_form`：unknown → `3D 构象/对接分数`（exact_label，来源 `benchmark:antibody_cdrh3_test_set`，非论文原文声明）
- P3-3 lineage 证据分级：逐字引文 0/3 条，书目证据 0 条，完全无证据 3 条；标题不是 quote，故 0 条属实。修复路径：Stage2/Stage3 抽取 related_work 段落时保存引文原句，建成 Evidence(kind='citation', quote=...) 并以 SUPPORTED_BY 连到 SourcePaper；本模块会自动升级为

### 2302.09048

- 最终判定：**PARTIAL**
- 漂移分布：`{'numerical': 0, 'methodological': 3, 'protocol': 0, 'ordering': 0}`
- 降级原因：['SAU_score 0.6667 < 0.90', 'drift_rate 0.3333 > 0.05', 'Align_mixed 70.5 < 80']
  - `sau:230209048:method:000` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
  - `sau:230209048:method:001` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
  - `sau:230209048:method:002` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
- unverified 1 条（原因示例）：
  - `sau:230209048:numeric:001` numeric: results 中无该榜单行/指标的实跑值
- 数据缺口（P1-7 静态词表口径）：shape 未登记形式 0 处；lineage 带逐字证据 0/3 条
- P3-1 范围归一化：剔除跨论文模块 0 个、误挂基线算法 2 个，共删边 2 条（跨论文 `HAS_MODULE` + 基线算法 `PROPOSES_METHOD`）；证据化补 `MODULE_IMPLEMENTED_BY` 边 0 条；无可证据化映射而保持缺口的模块 3 个
- P3-2 真实 mini-batch 实测（batch_size=4）：1/1 个探针 runtime_verified，同族继承表单 0 处，残留 unknown 0 处；脚本 `MINIBATCH_SCRIPT.py` 可独立重跑
- P3-3 lineage 证据分级：逐字引文 0/3 条，书目证据 0 条，完全无证据 3 条；标题不是 quote，故 0 条属实。修复路径：Stage2/Stage3 抽取 related_work 段落时保存引文原句，建成 Evidence(kind='citation', quote=...) 并以 SUPPORTED_BY 连到 SourcePaper；本模块会自动升级为

### 2611.06237

- 最终判定：**PASS**
- 漂移分布：`{'numerical': 0, 'methodological': 1, 'protocol': 0, 'ordering': 0}`
- 降级原因：无
  - `sau:261106237:method:002` method/mismatch: 模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边
- unverified 0 条（原因示例）：
- 数据缺口（P1-7 静态词表口径）：shape 未登记形式 32 处；lineage 带逐字证据 0/3 条
- P3-1 范围归一化：剔除跨论文模块 0 个、误挂基线算法 0 个，共删边 0 条（跨论文 `HAS_MODULE` + 基线算法 `PROPOSES_METHOD`）；证据化补 `MODULE_IMPLEMENTED_BY` 边 0 条；无可证据化映射而保持缺口的模块 1 个
- P3-2 真实 mini-batch 实测（batch_size=4）：5/21 个探针 runtime_verified，同族继承表单 18 处，残留 unknown 28 处；脚本 `MINIBATCH_SCRIPT.py` 可独立重跑
  - 表单继承 `benchmark:canonical:sapt10k` 的 `input_form`：unknown → `原子坐标`（exact_label，来源 `benchmark:sapt10k`，非论文原文声明）
  - 表单继承 `benchmark:canonical:sapt10k` 的 `output_form`：unknown → `能量/力`（exact_label，来源 `benchmark:sapt10k`，非论文原文声明）
  - 表单继承 `benchmark:canonical:quid` 的 `input_form`：unknown → `原子坐标`（exact_label，来源 `benchmark:quid`，非论文原文声明）
  - 表单继承 `benchmark:canonical:quid` 的 `output_form`：unknown → `能量/力`（exact_label，来源 `benchmark:quid`，非论文原文声明）
  - 表单继承 `benchmark:canonical:jsch_2005` 的 `input_form`：unknown → `原子坐标`（exact_label，来源 `benchmark:jsch_2005`，非论文原文声明）
  - 表单继承 `benchmark:canonical:jsch_2005` 的 `output_form`：unknown → `能量/力`（exact_label，来源 `benchmark:jsch_2005`，非论文原文声明）
- P3-3 lineage 证据分级：逐字引文 0/3 条，书目证据 3 条，完全无证据 0 条；标题不是 quote，故 0 条属实。修复路径：Stage2/Stage3 抽取 related_work 段落时保存引文原句，建成 Evidence(kind='citation', quote=...) 并以 SUPPORTED_BY 连到 SourcePaper；本模块会自动升级为

## 7. 结论与可复现命令

- **2411.06608**：`PASS` — SAU_score 1.0 / coverage 1.0 / Perf Gap 0.0
- **2405.03370**：`PARTIAL` — SAU_score 0.9429 / coverage 1.0 / Perf Gap 0.0
- **2302.09048**：`PARTIAL` — SAU_score 0.6667 / coverage 0.9 / Perf Gap 0.0
- **2611.06237**：`PASS` — SAU_score 0.9836 / coverage 1.0 / Perf Gap 0.0

```bash
cd /home/zengshuxin/xKG-main/xKG-main
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
    --arxiv 2411.06608 --effort lite \
    --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md
PYTHONPATH=. python3 -m unittest discover -s tests/Phase -p 'test_*.py'
```

## 8. 多篇回归结论

| arxiv | 门链 overall | 最终评估 | R6 | 主要降级原因 | mini-batch 实测 |
|---|---|---|---|---|---|
| 2411.06608 | `PASS` | `PASS` | `PASS` | 无 | 6/6 |
| 2405.03370 | `PARTIAL` | `PARTIAL` | `PASS` | drift_rate 0.0571 > 0.05 | 1/3 |
| 2302.09048 | `BLOCKED` | `PARTIAL` | `PARTIAL` | SAU_score 0.6667 < 0.90; drift_rate 0.3333 > 0.05; Align_mixed 70.5 < 80 | 1/1 |
| 2611.06237 | `BLOCKED` | `PASS` | `PASS` | R4 | 5/21 |

所有降级均由**真实数据缺陷**触发，不是系统故障：

- 无 `HAS_CODE` 仓库 → R0/R2 BLOCKED
- `MetricDefinition.direction` 未知/启发式 → R4 BLOCKED 或 PARTIAL
- 表单为占位 `unknown` 且同族无可继承声明 → mini-batch 如实保留 unknown
- 缺 `MODULE_IMPLEMENTED_BY` 且无可证据化映射 → method mismatch 如实保留

回归结论：范围归一化只对**存在跨论文误挂**的论文生效，对数据本身缺失的论文不会人为抬分。
