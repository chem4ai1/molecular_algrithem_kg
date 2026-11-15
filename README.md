# molecular_algrithem_design

**从论文知识抽取到论文复现**的最小可运行工程。
内含 4 篇论文的完整切片（抽取报告、语义层图、应用层任务图、复现规格与 rubric 树）、
后端实现、五个阶段的入口脚本，以及可交互的前端页面。

> 本仓库是 `xKG-main`（783 篇全量）的**结构化切片**：
> 代码完整迁移、数据裁剪到 4 篇、路径改为仓库内自包含。

## 目录架构

```
molecular_algrithem_design/
├── README.md                  # 本文件
├── requirements.txt
├── src/capfactory/            # 后端实现（Python 包，231 个模块）
│   ├── po/                    # 图存储：Concept / Assertion / POGraph
│   ├── ontology/              # legacy TBox（tbox.py 单一权威入口）
│   ├── semantic/              # 语义层：tbox_v4 / extraction / apply / refresh /
│   │                          #   provenance / vector_sync / enrich / batch_extract
│   ├── applayer/              # 应用层：tbox / miner / tasks / builder
│   ├── reprospec/             # 复现规格：contract / compiler / scoring /
│   │                          #   application / relations / rubric_tree / rubric_runtime
│   ├── sciforge/              # 编排：repro/ assembly/ relation_layer / table_extract /
│   │                          #   leaderboard / algorithm_* / benchmark_fill / core
│   ├── web/                   # FastAPI：server / data_api / relation_api /
│   │                          #   provenance_api / tbox_api / static 页面
│   ├── llm/                   # 后端客户端（vllm / ollama / openrouter）
│   └── md/                    # 设计文档（抽取总览、语义层架构、任务层…）
├── stages/                    # 按实现阶段组织的入口（每个阶段含 README + 可跑脚本）
│   ├── 1_extraction/          #   NER→槽位→关系→模块追踪，E1–E6 + 范式层
│   ├── 2_semantic_layer/      #   回填 6 类 / 9 关系 + 重建索引
│   ├── 3_app_layer/           #   任务驱动构建应用层（reproduction / generation）
│   ├── 4_reproduction/        #   ReproSpec / SAU / rubric 树 / R0–R6 门控
│   └── 5_frontend/            #   FastAPI 页面与 API
├── data/
│   ├── docx/                  # 783 篇论文 markdown（抽取输入）
│   ├── papers/{pdf,abstracts}/ # 783 份 PDF 原文 + 摘要
│   ├── papers.csv             # 6385 行权威元数据（领域码校准）
│   └── repos/                 # 90 个代码仓库（AST / 代码联系）
├── storage/                   # 运行产物（storage_cf 软链指向此处，兼容代码内相对路径）
│   ├── sciforge/
│   │   ├── batch10_semantic_v4.json    # 语义层：6001 节点 / 7460 断言
│   │   ├── app_reproduction.json       # 复现任务层：8300 节点
│   │   ├── app_generation.json         # 生成任务层：8853 节点
│   │   ├── batch10_app_v1.json         # 页面快照：纯语义层（0 应用节点）
│   │   ├── relation_index.json         # 关系浏览器索引
│   │   ├── provenance/                 # 溯源索引 + 缺失论文 CSV
│   │   └── semantic_extraction/        # 783 份抽取报告（含 paradigm 范式层）
│   ├── repro_runs/            # 5 套复现产物
│   ├── repro_test/molminer/   # 本次实测工作区（含 RUBRIC_TREE_SCORES）
│   └── semantic/vector/       # 6001×1024 向量索引
├── tests/                     # 69 项测试（基线 / 词表 / 范式 / rubric / 复现 E2E）
├── docs/                      # 设计与调研文档
└── scripts/                   # serve.sh / rebuild.sh / smoke.sh
```

## 五个阶段与代码映射

| 阶段 | 做什么 | 关键实现 | 产物 |
|---|---|---|---|
| **1 抽取** | 切片 → paper_type → E1–E6（LLM）→ 校验 → 范式层（NER/规范化/关系逐字落地/模块追踪/槽位审计） | `semantic/extraction/{runner,contracts,prompts,validator,guides,paradigm,vocab}.py` | `storage/sciforge/semantic_extraction/<aid>.json` |
| **2 语义层** | 回填 6 类 / 9 关系（含 `MODULE_IMPLEMENTED_BY` 代码联系、`SUBCLASS_OF` 谱系）→ 重建关系索引 / 溯源索引 / 缺失 CSV / 向量 / 页面快照 | `semantic/{apply,refresh,provenance,vector_sync,tbox_v4}.py` | `batch10_semantic_v4.json`、`relation_index.json`、`provenance/` |
| **3 应用层** | **任务驱动**：reproduction 出榜单/指标/契约/证据/局限/出处，generation 出研究问题/类别 + 共享 5 类 | `applayer/{tasks,builder,miner,tbox}.py` | `app_reproduction.json`、`app_generation.json` |
| **4 复现** | 编译 ReproSpec（5 类 SAU）→ 层次化 rubric 树 → R0–R6 门控（零 LLM）→ 逐 SAU 判定 → 三层对齐评分 | `reprospec/{contract,compiler,scoring,application,rubric_tree,rubric_runtime}.py`、`sciforge/repro/` | `storage/repro_runs/<aid>/` 全套 |
| **5 前端** | 三库树、节点卡片、关系浏览器 + 溯源卡片 + 单元格级溯源、任务层 API、抽取进度 | `web/{server,data_api,relation_api,provenance_api,tbox_api}.py`、`web/static/*` | HTTP 服务 |

## 数据说明（全量）

仓库内含**全量数据**（约 5.9G），非切片：

| 数据 | 规模 |
|---|---|
| `data/docx/*.md` | 783 篇论文 markdown（抽取输入） |
| `data/papers/pdf/*.pdf` | 783 份 PDF 原文（4.7G） |
| `data/papers.csv` | 6385 行权威元数据（领域码校准） |
| `data/repos/src/` | 90 个代码仓库（962M，AST/代码联系来源） |
| `storage/sciforge/semantic_extraction/` | **783 份抽取报告**（含 `paradigm` 范式层） |
| `storage/sciforge/batch10_semantic_v4.json` | 语义层 **6001 节点 / 7460 断言** |
| `storage/sciforge/app_reproduction.json` | 复现任务层 8300 节点 |
| `storage/sciforge/app_generation.json` | 生成任务层 8853 节点 |
| `storage/sciforge/batch10_app_v1.json` | 页面快照（纯语义层，0 应用节点） |
| `storage/semantic/vector/` | 6001×1024 BGE 向量索引（25M） |
| `storage/repro_runs/` | 5 套复现产物（2411 主 + 4 regression） |

规模与前端实测：

```
论文树 12 组 / 808 Paper    算法树 9 组    数据树 6 组
关系实例 808（paper）       批跑状态 783/783（ok 764）
溯源覆盖 Algorithm 100% / Benchmark 97.7%
```

## 快速开始

```bash
cd molecular_algrithem_design
pip install -r requirements.txt

# 起服务（三库 / 关系浏览器 / 溯源 / 任务层）
bash scripts/serve.sh 8091
# → http://127.0.0.1:8091       首页
# → http://127.0.0.1:8091/data     三库树
# → http://127.0.0.1:8091/relations 关系 + 溯源卡片

# 冒烟（另开终端）
bash scripts/smoke.sh http://127.0.0.1:8091

# 重建索引（改了图或报告后）
bash scripts/rebuild.sh
```

单独跑各阶段：

```bash
# 1 抽取（会调 LLM，需配置后端）
python stages/1_extraction/run_one.py 2411.06608
python stages/1_extraction/run_batch.py --limit 3
python stages/1_extraction/run_batch.py --status

# 2 回填 + 重建
python stages/2_semantic_layer/apply_refresh.py

# 3 任务层
python stages/3_app_layer/build_task.py reproduction
python stages/3_app_layer/build_task.py generation

# 4 复现（零 LLM）
python stages/4_reproduction/compile_run.py paper:2411.06608 lite

# 5 前端
python stages/5_frontend/serve.py 8091
```

测试：

```bash
PYTHONPATH=src python -m unittest discover -s tests
# 69 项：基线 / 词表标准 / 范式层 / rubric 树与运行时图 / MolMiner 复现 E2E
```

## 图引擎：自研 POGraph + networkx 适配

图谱**不是**图数据库，也**不是** networkx 存储：

| | 说明 |
|---|---|
| 存储 | 自研 `po/store.py::POGraph`（JSON，6001 节点 / 7460 断言），带惰性邻接索引 |
| 适配 | `po/nx_adapter.py` → `nx.MultiDiGraph`，可往返 |
| 能力 | 统计（连通分量/密度/度分布）、多跳邻居、最短路、GraphML/GEXF 导出 |
| API | `/api/v9/graph/nx/{stats,neighbors,shortest,export}` |

实测（语义层）：**260** 个弱连通分量、密度 `2.07e-4`、度均值 2.49、最大 33、**DAG=True**、
GraphML 导出 9.47MB（可被 Gephi 直接打开）。详见
[src/capfactory/md/GRAPH_ENGINE.md](src/capfactory/md/GRAPH_ENGINE.md)。

## 复现控制台：四环节生命周期（`/repro`）

在 SAU 之上把复现拆成**可单环节触发、可校验**的四步（零 LLM）：

| 环节 | 做什么 | 产物 | 关键校验 |
|---|---|---|---|
| ① 方法锁定 | 逐条 method SAU 指纹 + 集合 hash | `METHOD_LOCK.json` | 漂移 SAU 列表，漂移即不通过 |
| ② 代码生成 | `ordering` 依赖 → DAG → 任务化 → `REPRO_SCRIPT.py` | `CODE_PLAN.json` | 脚本安全 / 符号召回 / 顺序单调；依赖环降级为告警 |
| ③ 复现执行 | subset→full 阶梯 + 双跑 | `EXECUTION_LOG.json` | 覆盖率、可重复性、失败定位到 SAU |
| ④ 主张锚定 | claim → 表格单元格 → 图节点 三级链 | `CLAIM_ANCHORS.json` | 每条 claim 4 hash + `verified` |

MolMiner 实测：14 条方法 SAU、14 个生成任务、**方法覆盖 100%**、
31 条 claim（30 条三级命中）、`integrity true`、`verify ok`。

```bash
# 页面
# http://127.0.0.1:8091/repro
# API
curl http://127.0.0.1:8091/api/v9/repro/papers
curl -X POST "http://127.0.0.1:8091/api/v9/repro/2411.06608/run?stage=all"
curl http://127.0.0.1:8091/api/v9/repro/2411.06608/verify
# 单独重跑某一环节
curl -X POST "http://127.0.0.1:8091/api/v9/repro/2411.06608/run?stage=codegen"
```

设计细节见 [src/capfactory/md/REPRO_LIFECYCLE.md](src/capfactory/md/REPRO_LIFECYCLE.md)。

## 复现实测：MolMiner（2411.06608）

工作区：`storage/repro_test/molminer/`（23 个产物文件）。

```bash
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from capfactory.po import POGraph
from capfactory.reprospec.compiler import compile_reprospec
from capfactory.sciforge.repro import run_repro
ws = Path("storage/repro_test/molminer")
g = POGraph.load("storage_cf/sciforge/app_reproduction.json")
spec = compile_reprospec(paper_id="paper:2411.06608", out_dir=ws)
r = run_repro(g, "paper:2411.06608", ws=ws, effort="lite")
print(spec.spec_hash, r["overall"])
PY
```

### 实测结果

| 指标 | 值 |
|---|---|
| SAU 条数 | **71**（method 14 / code_grounding 17 / protocol 6 / numeric 31 / ordering 3） |
| spec_hash | `sha256:0f1f79f23800ac4e5…` |
| 总判定 | **PARTIAL**，原因 `drift_rate 0.058 > 0.05` |
| sau_score / coverage | 0.942 / 0.9718 |
| exec_rate / symbol_recall | **1.0 / 1.0** |
| perf_gap | 0.0 |
| align_mixed | 98.2 |
| rubric 树 | 71 叶、深度 3、`root_score 0.916`、**6 个失败分支** |
| 运行时图 | RubricNode **95**（24 分支 + 71 叶）、HAS_SAU 71 |

未对齐明细（真实质量信号，不是脚本缺陷）：

- `method` 4 条 `mismatch`：模块没有 `MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE` 边（模块存在但未定位到实现函数）
- `ordering` 2 条 `unverified`：模块依赖链缺输入，无法判定顺序

`REPRO_SCRIPT.py` 自包含（表格行内嵌、不读应用层期望值），可独立执行：

```bash
cd storage/repro_test/molminer && python REPRO_SCRIPT.py
# exit 0，status=PASS，14 步执行，24 行、3 个基准
# baseline 2.4516 vs candidate 0.0，raw_results.json 23950 B
```

### 测试代码：`tests/test_reproduction_molminer.py`（21 项）

| 组 | 断言 |
|---|---|
| `TestReproSpec` | 5 类 SAU 齐备、数量 >60、**spec_hash 两次编译一致**、id 唯一、**每条 source_node_ids 都能回溯到两层图** |
| `TestRubricTree` | 挂载率 100%、深度 3、叶数一致、root_score ∈ [0,1]、failed == (score<1) |
| `TestRuntimeGraph` | root/branch/leaf 三种角色、HAS_SAU 数 == 叶数、**全量图里 0 个 RubricNode** |
| `TestReproScriptExecution` | **真跑脚本**：exit 0、subset/full 两阶段、n_rows>0、steps_executed>0、symbol_trace 指向模块、与 raw_results 同源 |
| `TestVerdictsAndEvaluation` | 每条 SAU 都有判定、verdict 合法、overall 合法、mismatch 必须带 note/drift_type、三哈希齐全 |
| `TestNumericHelpers` | to_float("0.90±0.01") / "1,234" / "98%" / "n/a"；normalize_model("MolMiner (ours)")、normalize_metric_name("Validity (%)") |

```bash
PYTHONPATH=src python -m unittest tests.test_reproduction_molminer -v
```

## 三条设计约束（读代码前必看）

1. **语义层只放客观事实**：6 类（Paper / Algorithm / AlgorithmModule /
   CodeRepository / CodeFunction / Benchmark）、9 条关系。
   被删的 9 个类各有落点（属性化或上移应用层），见 `src/capfactory/md/SEMANTIC_LAYER_ARCHITECTURE.md`。
2. **应用层只在任务时构建**：抽取与回填期不产生任何应用节点；
   页面默认图是纯语义层快照（`batch10_app_v1.json` 里 0 个 `layer=application`）。
3. **复现链路零 LLM**：`reprospec` 与 `sciforge/repro` 全为确定性编译与门控，
   每条判定都能回溯到图节点（`source_node_ids`）与表格单元格（`table_extract:N`）。

## 已知限制

- 抽取需 LLM 后端（vllm/ollama/openrouter），本仓未内置模型；
  不配也可直接读已有 4 份报告跑阶段 2–5。
- `storage_cf` 是指向 `storage/` 的软链（代码内路径为 `storage_cf/...`）。
  拷贝仓库请用 `cp -a` 保留软链，或改代码内相对路径。
- 数据为全量（5.9G），`data/papers/pdf` 占 4.7G、`data/repos` 占 962M；如需瘦身可删 pdf 与未引用的仓库。
- 复现产物为 `lite`/`dry` 档：`SAU_VERDICTS` 里 `aligned` 表示「声明在代码/图中成立」，
  不代表真实执行通过；接真实执行器后才有复现质量含义。
- rubric 树深度固定 3 层（根 / 方法或基准 / 模块或叶子），未做 PaperBench 式的任意深树。

## 相关文档

| 文档 | 内容 |
|---|---|
| `src/capfactory/md/EXTRACTION_OVERVIEW.md` | 抽取链路代码级说明（E1–E6、范式层、成本优化） |
| `src/capfactory/md/SEMANTIC_LAYER_ARCHITECTURE.md` | 语义层 6 类 / 9 关系逐字段与实例 |
| `src/capfactory/md/APPLICATION_TASK_LAYERS.md` | 复现 / 生成两种任务的应用层 |
| `src/capfactory/md/RUBRIC_TREE_LAYER.md` | 层次化 rubric 树（含与 PaperBench 对照） |
| `src/capfactory/md/TBOX_INVENTORY.md` | TBox 清点与精简方案 |
| `docs/` | 复现蓝图、范式调研、全量运行说明、溯源审查 |
