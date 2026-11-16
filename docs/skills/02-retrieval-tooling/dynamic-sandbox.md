# PE · `dynamic-sandbox` — 可复现的数值/符号执行沙箱

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/dynamic-sandbox/SKILL.md`（v1.7.2，151 行）
> **功能批次**：② 检索与工具层
> **机械对应代码**：`scripts/security_scan.py`、`scripts/smoke_gate.py`、`scripts/leakage_scan.py`、`scripts/workspace_hygiene.py`、`scripts/detect_device.py`、`scripts/validate_verdicts.py`
> **性质判断**：**执行型 skill**（`type: reference-skill` / `role: computation-sandbox`）。它是「传统跑实验」的替代品：任何学科问题最终归约为方程 / 矩阵 / 统计分析，都由它执行。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `dynamic-sandbox` / `1.7.2` |
| `type` / `role` | `reference-skill` / `computation-sandbox` |
| 管线阶段 | **无固定 Phase**；主力在 Phase 6a（符号验证）、6b（toy）、6c（full 的 smoke/数值切片）、2.5（反例数值检验） |
| 定位 | "**The skill does not understand science — it only runs code and returns data.**" |
| 输入 | 验证脚本 + 参数 + `input.json` |
| 输出 | `output.json` / CSV / SVG + `code.py` + SHA-256 三元组哈希 |
| 配置 | `language=python` / `timeout=300s` / `seed=42` / `packages=[]` / `output_format=json` |

---

## 2. 解决什么问题

| 目标 | 机制 |
|---|---|
| **可复现** | 代码 + 随机种子 + 输入数据全部保留；`seed=42` 默认写在脚本顶部 |
| **可验证** | 输出必须结构化（JSON/CSV），不能只打印到终端 |
| **错误不被吞** | 失败返回完整 traceback + 3 条修复建议，不静默重试 |
| **无学科偏见** | PDE 求解与统计检验一视同仁；库选择只看域上下文，不参与逻辑判断 |
| **资源预算对齐** | `timeout=300s`（v2.1）：与 `experiment-execution` toy 的 5min 前台预算一致，避免沙箱 120s 误杀 toy；>5min 的任务按 orchestrator 规则走 background dispatch |

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | 横切；orchestrator 26 节点表中无独立节点，由 `/experiment-execution`（6b/6c）与 `/theory-derivation`（6a）调用 |
| 前置 | `security_scan.py` 静态扫描通过（Step 5.00 Security Gate）→ 才能进 Step 5.0 smoke |
| 后继 | `/theory-derivation`（先推导后数值验证）、`/result-to-claim`（结果进 claim 门）、`/unified-plotting`（SVG 产物） |
| 门 | `.SMOKE.json` 必须存在且 `smoke_result=PASS`（`smoke_gate.py` 在 6c 边界硬查） |
| 回退 | TIMEOUT/ERROR → 1 次重试；INCONCLUSIVE → 1 次重设计；toy FAIL → **kill idea**（非 BA） |

> orchestrator §Boundaries 明确：单 agent 配置里，`/theory-derivation` + `/dynamic-sandbox` 共同承担「领域特定方法论」，OSS **不按学科分叉**成 4 条并行管线。

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | Reproducibility / Data Availability 声明 | `code.py` + `input.json` + `output.json` + 三哈希 | 直接提供「代码与数据可获取」的机器证据 |
| **论文层** | Result 段落数值 | `output.json` 的结构化数值 | 为表格/图提供唯一数据源，禁止从散文里编数字 |
| **算法层** | 符号推导验证 | SymPy 逐步验证、公式数值核对 | 支撑 Phase 6a 与 `PROOF_AUDIT.json` |
| **算法层** | 反例检验 | 生成 synthetic data 测假设 | 支撑 Phase 2.5 adversarial-falsification 的 counterexample 攻击 |
| **代码层** | **执行单元** | `sandbox/session_{ts}/code.py` | 自包含脚本、seed 置顶、无硬编码路径、函数带 docstring 且至少一个 error case |
| **代码层** | 安全与冒烟 | 静态扫描 → smoke → 正式 dispatch | 与 `security_scan.py` / `smoke_gate.py` 串成执行链 |
| **代码层** | 设备后端 | CPU / CUDA / ROCm / NPU / MPS | 由 `detect_device.py` 的 `DEVICE.json` 决定，而非硬编码 |
| **数据层** | 输入输出 | `input.json` / `output.json` / `artifacts/*.svg` | 结构化、形状可校验（矩阵=2D、标量=数值、图=非空 SVG） |
| **数据层** | 会话清单 | `sandbox/MANIFEST.json` | 记录每次会话的 code+input+output 联合哈希 |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  计算请求（域上下文 / 计算类型 / 输入数据 / 期望输出形状）
  ↓
Step 1  解析请求；过于含糊（"explore this data"）→ 要求调用方给具体计算计划
Step 2  生成沙箱代码：seed 置顶 → import → 读 input.json → 计算 → 写 output.json
        → 处理边界（空输入 / 除零 / 不收敛）→ 内联注释
Step 3  隔离子进程执行：mkdir sandbox/session_{ts}/ → 写 code.py + input.json
        → subprocess.run(timeout=300) → 捕获 stdout/stderr/returncode
        成功：读 output.json，算 SHA-256(code+input+output)，写 MANIFEST.json
        失败：完整 traceback + 3 条可能修复（缺库/语法/逻辑），不静默重试
Step 4  输出形状校验（矩阵 2D / 标量数值 / 图 SVG 非空）
Step 5  返回 {status, session_id, output, artifacts, code_hash, execution_time_ms, error}
输出  sandbox/session_{ts}/{code.py, output.json, artifacts/*.svg} + MANIFEST.json
```

### 5.1 预装库与按需库

| 类别 | 库 |
|---|---|
| Python 默认 | `numpy, scipy, sympy, matplotlib, pandas, statsmodels, sklearn, networkx` + stdlib（`itertools/functools/math/cmath/random/json/csv`） |
| On demand（检测到代码里用到时自动装） | `biopython, rdkit, astropy, qiskit, tensorflow, torch, transformers` |

### 5.2 代码质量硬规则

- 无交互式绘图（必须 `plt.savefig()` 矢量格式）；无硬编码路径
- 每个非平凡函数有 docstring，且至少处理一个错误情形
- **输出结构必须可解析，不允许自由文本 print**
- 边界情况显式处理：空输入、除零、收敛失败

### 5.3 返回体 schema

```json
{"status": "success|error|partial", "session_id": "session_...",
 "output": {}, "artifacts": ["artifacts/plot.svg"],
 "code_hash": "sha256:...", "execution_time_ms": 1234, "error": null}
```

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `ComputationRequest` | `domain_context`, `computation_type`, `input_data`, `expected_output_shape` | `COMPILES_TO →` `SandboxCode` |
| `SandboxSession` | `session_id`, `timestamp`, `seed`, `timeout`, `language`, `packages[]` | `CONTAINS →` `SandboxCode` / `InputData` / `OutputData` / `Artifact` |
| `SandboxCode` | `code.py`, `sha256`, `py_compile_ok`, `security_scan_ok` | `PRODUCES →` `OutputData` |
| `OutputData` | `output.json`, `shape_validated`, `schema` | `FEEDS →` `RESULT.json` → `Claim` |
| `TripleHash` | `sha256(code + input + output)` | `ANCHORS →` `Result` / `ClaimAnchor` |
| `DeviceProfile` | `backend ∈ {cuda, rocm, npu, mps, cpu}`, `device_count`, `name` | `SELECTS_BACKEND_FOR →` `SandboxSession` |
| `SmokeEvidence` | `.SMOKE.json`, `smoke_result=PASS`, `executed_at` | `GATES →` `FullDispatch` |
| `SecurityFinding` | 静态扫描命中 | `BLOCKS →` `subprocess.run` |
| `Manifest` | `sandbox/MANIFEST.json` | `INDEXES →` 所有 session |

**核心约束**：`Execute ⇒ SecurityScan.PASS`（先扫描后执行）；`FullDispatch ⇒ SmokeEvidence.PASS`；`Result ⇒ TripleHash` 且 `shape_validated=true`；`OutputData` 必须结构化。

---

## 7. 对应 `scripts/` 代码

沙箱本身是模型契约（仓库里没有 `sandbox/` 运行时实现），但**围绕执行的前后门全部脚本化**：

| 脚本 | 保障点 | 关键实现 |
|---|---|---|
| `scripts/security_scan.py` | **执行前**静态安全门 | 填补 P1-8 缺口：「full-mode 脚本是 agent 写的、直接在宿主机跑，而 toy 已在 sandbox 内」。纯静态、**不执行代码**；`.py` = `ast.walk` + 正则行扫（抓嵌入式 shell 字符串），`.sh` = 正则；Python 3.12 stdlib only；必须在 `experiment-execution` Step 5.0 smoke 之前跑，因为 smoke 会真正执行 |
| `scripts/smoke_gate.py` | **执行后**冒烟承重证据 | 曾真实观察到 Q-SGD-BS-GAP 跑了 184s 却没有 smoke。检查每个 `experiments/full/**/DISPATCH.json` / `STATUS.json` 组是否有同级 `{id}.SMOKE.json` 且 `smoke_result=PASS`；**smoke 时间晚于最后一次 STATUS 更新 → WARN**（说明脚本在 smoke 之后被改动）；无 dispatch → SKIP |
| `scripts/leakage_scan.py` | 结果写进正文时不泄漏管线痕迹 | 8(+1) 类正则；A/B 两类（如 `derivations/`、`src/`、`.py`、`MCTS`、`DAG`、`background dispatch`、`effort:lite` 等）；**Class J = AIGC 痕迹词**（"delve"/"tapestry"/"It is worth noting that"）；写 `LEAKAGE_SCRUB.json` verdict，Phase 13 边界据此拒绝推进 |
| `scripts/workspace_hygiene.py` | 会话产物不污染工作区 | 5 查：无顶层 stray `*.log`、无 stray JSON/TXT、无 `__pycache__`/`.pytest_cache`/`.DS_Store`、无空目录、有 run README；ARC-Bench 两轮评估发现 cwd 相对垃圾泄漏后加的 |
| `scripts/detect_device.py` | 后端选择的事实来源 | `nvidia-smi / rocminfo / npu-smi / mps / cpu` 依次探测，输出 `DEVICE.json`；**无 CPU-first/GPU-first 默认** |
| `scripts/validate_verdicts.py` | 会话 verdict schema | 每个 Phase 边界 `--strict --require-complete`，PENDING → BLOCKED |
| `scripts/arb_verify.py` | 数值 claim 的认证区间 | 可选 gate，把点值 claim 升级为带严格误差界的区间声明 |

> **两处值得记录的口径张力**：
> ① SKILL.md 的 Quick Reference 写「**no GPU**, numerical sanity checks only」，而 `detect_device.py` 与 on-demand 库列表（`tensorflow/torch/qiskit`）明显支持加速后端。合理解读是「沙箱默认做轻量数值合理性检验，不默认占 GPU」；真正的 GPU 训练走 `experiment-execution` 的 full+background 路径。
> ② SKILL.md 说按需库「auto-installed when detected in code」，`dep_gate.py` 却要求 import 必须**预先声明**。正确顺序是：先改 `dependencies.json` + `requirements.txt` → 再安装 → 再写代码 → 再过 dep_gate。

---

## 8. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `code.py` | `sandbox/session_{ts}/` | 复现 / 审计 |
| `output.json` | 同上 | `RESULT.json` → result-to-claim → 表格/图 |
| `artifacts/*.svg` | 同上 | unified-plotting |
| `MANIFEST.json` | `sandbox/` | 会话索引 |
| `.SMOKE.json` | `experiments/full/**/` | `smoke_gate.py` 硬门 |
| `DEVICE.json` | `.sciforge/` | backend 选择 / INSTALL |

---

## 9. 边界与反模式

- ❌ 只 print 不写结构化输出；❌ 交互式绘图；❌ 硬编码路径
- ❌ 静默吞异常或自动重试（必须交还调用方决定）
- ❌ 未经 security_scan 就执行 agent 代码；❌ 无 `.SMOKE.json` 就宣称 full dispatch 成功
- ❌ 输出形状不校验（期望矩阵却给了一维）
- ✅ seed 置顶、函数带 docstring 与 error case、三哈希留痕

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **三哈希 `sha256(code+input+output)`** 与上一轮 GGR 的 `ClaimAnchor.code_sha / inputs_sha / outputs_sha` 完全同构；加上 `DEVICE.json` 与 `seed` 即可扩成训练复现所需的六哈希。
2. **shape 校验前置**：本 skill 的「矩阵=2D / 标量=数值 / 图=非空 SVG」正是 GGR `MINIBATCH_PROBE` 的原型；可把它升级为真实 mini-batch 的 `runtime_verified` 判据。
3. **先扫描后执行**：GGR 的 `check_script_safety()` 与 `security_scan.py` 是同一条防线，可合并为统一 AST 白名单。
4. **设备画像作为节点**：`DEVICE.json` 应成为 `ExperimentNode` 的属性（backend / device_count / VRAM），训练复现的可行性探测可直接复用。
