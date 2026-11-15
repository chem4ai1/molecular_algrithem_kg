# 原论文模型训练复现设计（`effort = full`）

> 2026-11-14　回应「如果要做原论文模型训练复现呢？我目前有 GPU，数据集可尝试通过镜像下载，下载后放到 `/home/zengshuxin/data`」。
> 关联产物：`storage_cf/repro_runs/<arxiv>/TRAIN_FEASIBILITY.json`、`TRAIN_PLAN.json`（CLI `--train-plan` 生成）。
> 关联文档：`REPRODUCTION_IMPLEMENTATION_BLUEPRINT.md` §6/§7、`REPRODUCTION_EVALUATION_DESIGN.md`、`REPRODUCTION_VALIDATION_REPORT.md`。

---

## 0. 结论先行

| 问题 | 答案 |
|---|---|
| 现在能直接跑原论文训练吗 | **不能**。`TRAIN_FEASIBILITY.json → executable=false` |
| 缺什么 | ① PyTorch/CUDA/NCCL 动态库不兼容 ② 缺 `rdkit`/`torch_geometric` ③ 数据集未下载并校验 ④ 原仓库 commit / 训练入口 / 超参 / seed / checkpoint 未确认 |
| GPU 够吗 | **够**。实测 3×`NVIDIA H100 PCIe 81559 MiB`，其中 2 张显存占用 < 3 GiB |
| 数据放哪 | `/home/zengshuxin/data/<arxiv>/<benchmark>/`，镜像下载后登记 `sha256` |
| lite 与 full 的区别 | lite = **评测协议重算**（从论文表格原始行重算榜单）；full = **真正训练模型** |
| 本轮做了什么 | 环境探测 + 训练计划 + 与环境事实绑定的阻塞项；**未下载、未安装、未训练、未改动系统 Python 环境** |
| 为什么不动现有环境 | `/home/zengshuxin/anaconda3` 是 798 项回归的运行时，原地重装 torch 会破坏已通过的链路；必须新建隔离 venv 或容器 |

> 本轮所有验证写入 `storage_cf/repro_runs/` 工作区路径，未使用 `rm -rf` 或任何删除操作。

---

## 1. 三层边界：不要把 lite 当成训练复现

| 层 | 现有实现 | 是否训练模型 |
|---|---|---|
| L1 规格对齐 | `compile_reprospec()` 编译 74 条 SAU | 否 |
| L2 评测协议复现 | `REPRO_SCRIPT.py` 从 `Benchmark.attrs.model_results`（PDF 表格原始行）独立重算 `normalize_model / to_float / compute_sota` | 否 |
| L3 方法可执行性 | 模块链按 `code_plan.order`、符号落地、无 stub | 否（当前是静态 + 子进程脚本） |
| **L4 模型训练复现** | **本设计，`effort=full`** | **是** |

现有 `lite` 拿到 `Perf Gap=0.0` 只说明「榜单重算与另一条抽取管线一致」，**不说明论文模型被训练出来过**。把它写成训练复现成功属于造假，因此 `finalize()` 始终把训练精度列在 `out_of_scope`。

---

## 2. 环境基线（本轮只读实测）

| 项 | 实测值 | 状态 |
|---|---|---|
| Python | 3.12.7（`anaconda3`） | 可用 |
| GPU | 3×H100 PCIe 80GB；`#1` 占 2563 MiB、`#2` 占 5 MiB | 可用 |
| `torch` | `ImportError: libtorch_cuda.so: undefined symbol: ncclCommWindowDeregister` | **阻塞** |
| `numpy` | 1.26.4 | 可用 |
| `pandas` / `scipy` | 存在 | 可用 |
| `rdkit` | `find_spec=None` | **阻塞**（分子生成必需） |
| `/home/zengshuxin/data` | 存在，约 1.8 GiB，含 `paper/` | 未含训练数据集 |
| 原仓库 | 图里有 `coderepository:raulorteg_molminer` 节点，但**没有本地 clone、commit 或训练入口** | **阻塞** |

`ncclCommWindowDeregister` 是 NCCL 新 API；报「未定义符号」说明 `libtorch_cuda.so` 编译时链接的 NCCL 版本与运行时加载的 `libnccl.so` 不一致（通常是 conda 里 torch 与 `nvidia-nccl-cu12` 混装或 LD_LIBRARY_PATH 指向了系统旧库）。

---

## 3. P4-1：修复运行环境（隔离，绝不原地改）

### 3.1 先诊断，不动环境

```bash
nvidia-smi
nvcc --version || true
python3 -c "import torch; print(torch.__version__, torch.version.cuda)"  # 预期失败
ldd /home/zengshuxin/anaconda3/lib/python3.12/site-packages/torch/lib/libtorch_cuda.so | grep -i nccl
echo "$LD_LIBRARY_PATH"
```

### 3.2 新建隔离 venv（工作区内）

```bash
cd /home/zengshuxin/xKG-main/xKG-main
python3 -m venv /home/zengshuxin/venvs/repro_full
source /home/zengshuxin/venvs/repro_full/bin/activate
python -m pip install -U pip
# CUDA 版本按 nvidia-smi 的驱动支持上限选择，以下仅为示例
python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
python -m pip install rdkit-pypi torch-geometric numpy pandas scipy pyyaml
python -m pip freeze > storage_cf/repro_runs/env.lock
python -c "import torch, rdkit; print(torch.__version__, torch.cuda.is_available())"
```

### 3.3 容器备选（更干净，推荐）

```bash
docker run --rm --gpus '"device=2"' -v /home/zengshuxin/data:/data \
  -v /home/zengshuxin/xKG-main/xKG-main/storage_cf/repro_runs:/runs \
  pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime \
  python -c "import torch; print(torch.cuda.is_available())"
```

### 3.4 验收门槛（三者全过才允许进 P4-2）

1. `torch.cuda.is_available() == True`；
2. 在 `#2` 卡上 1 个 mini-batch 前向+反向不 OOM、`loss` 有限；
3. `rdkit.Chem.MolFromSmiles("CCO")` 非空。

> **本轮没有执行以上任何安装命令**：它们需要联网下载数 GB 且会改变用户环境，应在用户确认 CUDA 版本与目标论文后单独执行。

---

## 4. P4-2：数据准备（镜像 + 固定布局）

### 4.1 布局

```
/home/zengshuxin/data/
└── 2411.06608/
    ├── zinc/                 # 对应 benchmark:zinc，SMILES→SMILES，论文标 1000M pairs
    ├── unconditional_generation/
    ├── conditional_generation/
    ├── targeted_generation/
    ├── targeted_multi_property/
    ├── canonical_zinc/
    ├── splits/               # train/valid/test 索引，固定 seed 生成
    └── DATASET_MANIFEST.json # 每个子目录的 url / mirror / sha256 / n_rows / license
```

`TRAIN_PLAN.json → datasets[].target_dir` 已按 `data_root/<arxiv>/<benchmark slug>` 生成，与图中 `Benchmark.n_samples / scale / input_form / output_form` 一一对应。

### 4.2 镜像下载（建议命令，本轮未执行）

```bash
# HuggingFace 镜像（国内可达）
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download --repo-type dataset <namespace>/<dataset> \
  --local-dir /home/zengshuxin/data/2411.06608/zinc --local-dir-use-symlinks False

# 或论文/原仓库 README 给出的官方源
# 下载完成后登记哈希，训练前由执行器复核
find /home/zengshuxin/data/2411.06608 -type f -print0 | sort -z | \
  xargs -0 sha256sum > /home/zengshuxin/data/2411.06608/DATASET_MANIFEST.sha256
```

### 4.3 规则

* 数据集**必须**带 `dataset_sha256` 与 `n_rows`，否则不进 `full`；
* 图里的占位 `"unknown"` 表单不能直接当数据契约用 —— 先用 P3-2 的 mini-batch 实测把形状固定下来；
* `1000M pairs` 级别全量集不适合先下载，阶梯里 `smoke` / `subset` 只用采样子集；
* 不删除任何已有文件，不写到 `/tmp`。

---

## 5. P4-3：原仓库与训练配置（必须人工确认，不得由 LLM 编造）

`TRAIN_PLAN.json → required_config_fields` 共 14 项，全部非空才允许启动：

| 字段 | 来源 | 为什么必须固定 |
|---|---|---|
| `repo_url` / `commit` | 论文脚注 / GitHub release | 不同 commit 的模型定义不等价 |
| `entrypoint` / `config_path` | 仓库 README | 决定跑的是训练还是推理 |
| `seed` / `split` | 论文实验章节或 config | 影响所有可复现性判定 |
| `batch_size` / `epochs` / `optimizer` / `learning_rate` / `scheduler` / `amp` | 论文附录 + 官方 config | 超参偏差会让 Perf Gap 失去意义 |
| `checkpoint_path` | 官方权重或训练产物 | 用于 `ckpt_sha` |
| `metric_names` | 图上 `MetricDefinition` | 验收口径对齐 |

当前 `TRAIN_PLAN.config = {}`（**故意留空**）。编译器不会猜超参；`blocking` 里会明确写「训练配置未确认：repo_url」。

---

## 6. P4-4：执行阶梯（smoke → subset → full）

| 阶段 | 样本 | epoch | 超时 | GPU | 验收 |
|---|---|---|---|---|---|
| `smoke` | 8 | 1 | 10 min | `#2`（5 MiB 占用） | 无 OOM / 无 shape 错误 / loss 有限 |
| `subset` | 1000 | 1 | 120 min | `#1` 或 `#2` | 指标方向正确、seed 可复现、日志完整 |
| `full` | 论文设定 | 论文设定 | 不设硬上限，人工值守 | 1–2 卡 | 主指标相对偏差 ≤ 5%，六哈希一致 |

执行约束：

```bash
CUDA_VISIBLE_DEVICES=2 PYTHONHASHSEED=0 \
  python <entrypoint> --config <config_path> --seed <seed> \
  --out /home/zengshuxin/xKG-main/xKG-main/storage_cf/repro_runs/2411.06608/train
```

* 每个阶段写 `.repro/events.ndjson`（durable truth）与 `RUNSTATE` 派生快照，可崩溃恢复；
* 失败仍走 `diagnose → EDIT N M → 重跑`，`debug_tries ≤ 20`；OOM 只允许改 batch 不改模型；
* `ties fail`：subset 不严格优于 baseline 就停，不进 full；
* 训练日志、`metrics.json`、`checkpoint.sha256`、`env.lock` 全部落在 run 目录。

---

## 7. P4-5：验收与防作弊

| 检查 | 口径 |
|---|---|
| 指标来源 | 论文表格原始行 `model_results`，**禁止**读 `LeaderboardEntry.value` / `sota_by_metric` 期望值 |
| Perf Gap | `(1/n)Σ|V_ref−V_run| / max(|V_ref|,|V_run|,eps) ≤ 0.05` |
| 逐 SAU 语义门 | R6 仍用 `SAUReport`，训练成功≠实现对齐（SA-Bench semantic drift） |
| **六哈希** | 现有 `code_sha / inputs_sha / outputs_sha` **+** `dataset_sha / ckpt_sha / seed_sha` |
| 双跑一致 | 两次独立 `full` 的 `outputs_sha` 必须相同；不一致即判 drift |
| 失败诚实 | 环境/数据/配置任一阻塞 → `BLOCKED`，绝不伪造指标 |

`ClaimAnchor` 需要从 3 哈希扩展为 6 哈希；`finalize()` 的 `out_of_scope` 在 `full` 且六哈希齐备时才允许移除「训练精度」一项。

---

## 8. 与现有 GGR 管线的接线

```
语义层(只读) → P3-1 归一化视图 → ReproSpec → R0–R4（不变）
                                      ↓
                    R5 执行器【full 替换点】
              lite: REPRO_SCRIPT.py（评测协议重算）
              full: 原仓库 entrypoint（真实训练）
                                      ↓
        raw_results / metrics.json / checkpoint → R6 语义门（不变）
                                      ↓
              六哈希 ClaimAnchor → FINAL_EVALUATION / 报告
```

具体改动点：

1. `reprospec/executor.py`：`effort == "full"` 分支改为调用 `TRAIN_PLAN.json` 描述的入口（子进程 + GPU 绑定 + 超时），`lite` 分支保持原样；
2. `reprospec/scoring.py`：`claim_anchors()` 增加 `dataset_sha / ckpt_sha / seed_sha`；`finalize()` 的 `out_of_scope` 按 `effort` 与六哈希状态动态生成；
3. `reprospec/cli.py`：`--effort full --train-plan` 先检查 `TRAIN_FEASIBILITY.executable`，为 false 时直接 `BLOCKED`，不允许跳过；
4. `phasegraph.json`：R5 增加 `full_train` 声明，但不改 7 个门的判定契约；
5. `tests/Phase/`：新增 full 分支测试，用 mock 入口验证「阻塞时不得执行」和六哈希。

> **当前状态**：`--effort full` 仍走 `execute_repro()` 的 lite 脚本路径，也就是**只生成计划、不训练**。这是刻意保留的诚实状态；接真实训练执行器属于 P4-4，需在阻塞项清空后进行。

---

## 9. 分阶段落地清单

| 阶段 | 内容 | 前置 | 本轮状态 |
|---|---|---|---|
| P4-1 | 隔离 venv / 容器修好 torch+NCCL、装 rdkit、冻结 `env.lock` | 用户确认 CUDA 版本 | 设计完成，未执行 |
| P4-2 | 镜像下载数据集到 `/home/zengshuxin/data/<arxiv>/`、登记 sha256 | P4-1 | 布局与命令已生成，未下载 |
| P4-3 | clone 原仓库、固定 commit、人工确认 14 项 config | 确定目标论文 | `TRAIN_PLAN.config={}` |
| P4-4 | 实现 full 执行器与 smoke/subset/full 阶梯 | P4-1~P4-3 | 待实现 |
| P4-5 | 六哈希 ClaimAnchor + 动态 out_of_scope | P4-4 | 待实现 |
| P4-6 | full 全量训练 + 报告 | 全部通过 | 待执行 |

---

## 10. 风险与明确不做的事

1. **不原地改 `anaconda3`**：798 项回归依赖它，必须隔离。
2. **不下载 GB 级数据集到系统目录**：只写 `/home/zengshuxin/data`，且不删除既有内容。
3. **不让 LLM 猜超参**：`config` 留空即阻塞，避免「看起来能跑但和论文不是一回事」。
4. **不把评测协议重算写成训练复现**：这是 SA-Bench 指出的 semantic drift 变体。
5. **不在阻塞未清时启动 full**：`TRAIN_FEASIBILITY.executable=false` 是硬门。
6. 多卡 DDP 会引入 NCCL 复杂度，建议 `smoke/subset` 单卡；`full` 再评估是否多卡。
7. 官方权重若缺失，需区分「从头训练复现」与「加载权重复现评测」，两者验收口径不同，必须写进 `TRAIN_PLAN.config`。

---

## 11. 本轮可复现命令

```bash
cd /home/zengshuxin/xKG-main/xKG-main
PYTHONPATH=. python3 -m capfactory.reprospec.cli \
  --arxiv 2411.06608 --effort lite --scope strict \
  --out storage_cf/repro_runs \
  --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md \
  --train-plan

# 查看训练可行性（不执行训练）
cat storage_cf/repro_runs/2411.06608/TRAIN_FEASIBILITY.json
cat storage_cf/repro_runs/2411.06608/TRAIN_PLAN.json
```
