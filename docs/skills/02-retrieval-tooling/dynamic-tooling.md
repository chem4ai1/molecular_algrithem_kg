# PT · `dynamic-tooling` — 运行时即时造工具

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/dynamic-tooling/SKILL.md`（v1.7.2，179 行）
> **功能批次**：② 检索与工具层
> **机械对应代码**：`scripts/dep_gate.py`、`scripts/detect_device.py`、`scripts/security_scan.py`、`scripts/smoke_gate.py`、`scripts/ci_check.py`、`scripts/arb_verify.py`
> **性质判断**：**能力扩展型 skill**（`type: reference-skill` / `role: tool-builder`）。它不绑定某个 Phase，而是被任意阶段按需调用，产出「工具」这一等产物。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `dynamic-tooling` / `1.7.2` |
| `type` / `role` | `reference-skill` / `tool-builder` |
| 管线阶段 | **无固定 Phase**（横切）。典型触发：Phase 2.5、6a（SymPy）、6b/6c（实验）、11（绘图适配） |
| 定位 | 官方称 **force multiplier meta-skill**：让系统在运行中扩展自身能力，杜绝「工具不可用」死胡同 |
| 输入 | 工具描述 + 接口契约 |
| 输出 | 可执行 Python 模块 + `tools/registry.json` 注册项 |
| 配置 | `scope=session` / `language=python` / `smoke_test=true` / `max_retries=2` |

---

## 2. 解决什么问题

研究过程中总会遇到沙箱标准库覆盖不到的任务：特定数据格式解析（如分子式）、领域专用计算、沙箱输出到绘图引擎的桥接、临时 CLI 适配器。若没有统一机制，agent 会在各阶段散乱地写一次性脚本，既不可复现也不受依赖/安全约束。

本 skill 把「造工具」变成一个**有契约、有测试、有注册、有哈希**的标准流程，并明确一条分流规则：

> 若缺口可以用 `pip install` 标准库解决，**不要造工具**，转交 `/dynamic-sandbox` 处理包列表。

这条规则避免了「重新发明一个已被成熟库实现的东西」。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | 横切；orchestrator 的 26 节点表里**没有独立节点**，它是被 `/experiment-execution`、`/theory-derivation`、`/unified-plotting` 内联调用的支撑能力 |
| 典型调用点 | ① Phase 2.5 反例构造需要专用生成器；② Phase 6a 需要 SymPy 逐步验证器；③ Phase 6b/6c 需要数据格式转换器；④ Phase 11 需要 sandbox → renderer 的桥接 |
| 后继 | `/dynamic-sandbox`（执行新工具）、`/unified-plotting`（把工具输出渲染成图） |
| 门 | smoke test 必须通过 + `py_compile` 必须通过，才允许注册 |
| 回退 | 失败最多 `max_retries=2` 轮；返回 traceback + 3 条修复建议，由调用方决定是否重试 |

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | 可复现性声明 | 工具哈希、版本、输入输出 schema | 为 Reproducibility / Data Availability 段落提供可列举的工具清单 |
| **算法层** | 验证 / 推导工具 | `symbolic-reasoner`、`formal-verifier` 模板 | 支撑 Phase 6a 的 SymPy 推导与逐步机器验证 |
| **算法层** | 统计分析 | `statistical-modeler` 模板 | 假设检验 / 回归 / 因果推断的检验统计量、p 值、效应量 |
| **算法层** | 知识结构 | `knowledge-graph` 模板 | 概念映射、文献网络 → JSON/GraphML |
| **代码层** | **工具本体** | `tools/{name}/{name}.py`、`tools/registry.json` | 一等代码产物，带 `__version__`、类型注解、docstring、错误处理 |
| **代码层** | 依赖面 | 工具 import 的库 | 必须能被 `dep_gate.py` 的 `dependencies.json` 放行 |
| **代码层** | 安全面 | 是否执行 shell / 网络 / 硬编码路径 | 必须过 `security_scan.py` 静态扫描 |
| **数据层** | 数据转换 | `data-transformer` 模板（多源格式 → 目标格式） | 把异构实验数据归一成 `RESULT.json` / 绘图输入 |
| **数据层** | 文本分析 | `text-analyzer` 模板 | 关键词 / 主题模型，服务文献与稿件分析 |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  能力缺口描述 + 接口契约
  ↓
Step 1  识别缺口（缺什么 / 为何现有不足 / 作用域 / 依赖）→ 若 pip 可解 → 转 dynamic-sandbox
Step 2  设计接口契约：Purpose / Input schema / Output schema / Side Effects / Error Modes
Step 2b 模板匹配（7 选 1），命中则直接载入预定义 schema + 测试用例 + 错误处理
Step 3  生成实现（自包含模块，≤200 行，类型注解，docstring 带示例，无硬编码路径/凭证）
Step 4  Smoke Test（已知输入 → 期望输出，浮点容差）→ PASS 则算 SHA-256 并注册；FAIL 返回 traceback + 3 建议
Step 5  注册：persistent → registry.json；session → tools/temp/{session_id}_{name}.py（不注册）
Step 6  返回 {status, tool_name, path, entry_point, smoke_test, usage}
输出  工具模块 + registry 项 + 结构化返回
```

### 5.1 7 个工具模板（知识节点的核心词表）

| 模板 | 用例 | 输入 → 输出 | 技术栈 |
|---|---|---|---|
| `symbolic-reasoner` | 数学定理证明 / 逻辑推导验证 | 数学命题 + 假设集 → 证明步骤 + 验证状态 | SymPy / symengine |
| `statistical-modeler` | 假设检验 / 回归 / 因果推断 | 数据 + 检验类型 → 统计量 + p 值 + 效应量 | scipy.stats / statsmodels |
| `knowledge-graph` | 概念映射 / 文献网络 | 概念表 + 关系类型 → KG（JSON/GraphML） | networkx |
| `formal-verifier` | 逻辑命题验证 / 模型检查 | 命题 + 推理规则 → 通过 / 反例 | Z3 / pysat |
| `code-synthesizer` | 自动生成验证/仿真代码 | 问题描述 + 参数 → 可执行 Python | AST 模板 + jinja2 |
| `data-transformer` | 多源数据格式转换 | 源数据 + 目标格式 → 转换后数据 | pandas |
| `text-analyzer` | 关键词抽取 / 主题模型 | 文本 + 分析类型 → 结构化结果 | sklearn / nltk |

> 模板优先于从零生成：模板自带 schema、测试用例、错误处理，是「少写少错」的结构化手段。

### 5.2 代码质量硬规则

- 单一入口函数或带 `__call__` 的类；参数与返回值类型注解；docstring 含使用示例
- 覆盖所有已识别 error mode；**无硬编码路径 / 凭证**；带 `__version__`
- ≤200 行（超出拆子模块）；注册前必须 `py_compile`
- 不 import 沙箱外或已安装库之外的东西；未经授权不执行 shell 命令

### 5.3 注册项 schema

```json
{"name": "...", "version": "1.0.0", "path": "tools/tool_name/tool_name.py",
 "hash": "sha256:...", "description": "...", "input_schema": "...",
 "output_schema": "...", "created_at": "...", "usage_count": 0}
```

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `CapabilityGap` | `missing`, `why_insufficient`, `scope`, `dependencies[]` | `TRIGGERS →` `Tool` 或 `DELEGATES_TO →` `dynamic-sandbox`（pip 可解时） |
| `ToolTemplate`（7 值枚举） | `input_schema`, `output_schema`, `test_cases[]`, `tech_stack` | `INSTANTIATES →` `Tool` |
| `Tool` | `name`, `version`, `path`, `sha256`, `entry_point`, `scope(session/persistent)`, `usage_count` | `REGISTERED_IN →` `ToolRegistry`；`USED_BY →` `SandboxSession` / `FigureRenderer` |
| `ToolContract` | `purpose`, `input_schema`, `output_schema`, `side_effects`, `error_modes[]` | `DESCRIBES →` `Tool` |
| `SmokeTest` | `known_input`, `expected_output`, `tolerance`, `passed` | `GATES →` `ToolRegistration` |
| `DependencyRoot` | `root`, `declared_in_dependencies.json` | `ALLOWS →` `Tool.import` |
| `SecurityFinding` | `kind`, `line`, `severity` | `BLOCKS →` `ToolRegistration` |

**核心约束**：`Registration ⇒ SmokeTest.passed ∧ py_compile.ok ∧ dep_gate.PASS ∧ security_scan.PASS`。注册表里每一项都是可复核的工具，不是随手写的一段代码。

---

## 7. 对应 `scripts/` 代码

本 skill 描述「造工具」，scripts 负责给造出来的工具**发通行证**。注意：仓库中**没有** `tools/` 自动生成器；`dynamic-tooling` 是模型行为契约，工具由模型写出，由以下脚本判定。

| 脚本 | 保障点 | 关键实现 |
|---|---|---|
| `scripts/dep_gate.py` | 工具 import 必须已声明 | `ast.parse` 收集 `src/**.py`、`figures/**/render.py` 的 import root（L53-68）；`sys.stdlib_module_names` 自动放行（L39）；`kernel/config/dependencies.json` 为唯一真相源；`always_forbidden`（pip/setuptools）即便列在 tier 也 FAIL；未声明 → `exit 2`。docstring 明说与 `security_scan.py` 的分工：一个管 **import 什么**，一个管 **代码怎么行为** |
| `scripts/detect_device.py` | 工具选 backend 之前先探设备 | 探测顺序 `nvidia-smi → rocminfo → npu-smi → torch.backends.mps → cpu`；docstring 强调「**没有 CPU-first / GPU-first 默认，domain + box 决定**」；输出 `.sciforge/DEVICE.json`，供 `experiment-execution` 与 `dynamic-sandbox` 消费，也供 INSTALL 决定装哪个 compute extra |
| `scripts/security_scan.py` | 静态安全扫描（不执行代码） | `.py` 用 `ast.walk` + 正则行扫（抓嵌入 shell 字符串），`.sh/.bash` 只做正则；纯 Python 3.12 stdlib；`--self-test`；退出码 `0 PASS / 1 WARN(--strict) / 2 usage-or-unparseable`。**必须在 Step 5.0 smoke gate 之前跑**，因为 smoke 会真的执行脚本 |
| `scripts/smoke_gate.py` | 「smoke 是承重证据」 | 契约原话：「a full dispatch that completes without first writing `.SMOKE.json` is invalid regardless of whether the experiment ultimately succeeded」；检查每个 `DISPATCH.json/STATUS.json` 组是否有同级 `{id}.SMOKE.json` 且 `smoke_result=PASS`；**smoke 比最后一次 STATUS 更新还新 → WARN**（说明脚本被改过） |
| `scripts/ci_check.py` | 仓库级 CI 一致性 | 工具/产物进入仓库前的静态检查 |
| `scripts/arb_verify.py` | `formal-verifier` 模板的认证区间 | 把点值 claim（"slope 4.94"）变成可认证区间（"slope ∈ [4.93,4.95]"）；`lo<=hi` 且能用 arb 解析；可选 `recompute` 表达式在 Arb 精度下求值并验证区间包含计算球；**OPTIONAL gate**，无 `arb_claims` → SKIP |

> **一处真实口径差异**：SKILL.md 的 "On demand (auto-installed when detected in code)" 列出 `rdkit / torch / transformers` 等可自动安装；但 `dep_gate.py` 要求所有 import root 必须**预先声明**在 `dependencies.json` 且同步 `requirements.txt`。两者不矛盾但必须按顺序：先加白名单 → 再安装 → 再写工具，否则 dep_gate 会 FAIL。

---

## 8. 产物与契约

| 产物 | 位置 | 说明 |
|---|---|---|
| 工具模块 | `tools/{name}/{name}.py` 或 `tools/temp/{session_id}_{name}.py` | 自包含、≤200 行、带 `__version__` |
| 注册表 | `tools/registry.json` | persistent 工具才写，含 sha256 与 schema |
| 返回体 | （调用方） | `{status, tool_name, path, entry_point, smoke_test, usage}` |

---

## 9. 边界与反模式

- ❌ pip 能解决却造轮子；❌ 未过 smoke / py_compile / dep_gate / security_scan 就注册
- ❌ 硬编码路径或凭证；❌ 擅自执行 shell；❌ 超过 200 行不拆分
- ❌ 工具失败静默重试（必须返回 traceback + 3 建议，由调用方决定）
- ✅ 优先命中 7 模板；✅ 每个工具都有明确的 error modes 与接口契约

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **模板词表可直接复用**：分子场景里 `symbolic-reasoner`（反应式配平）、`knowledge-graph`（分子-反应图）、`data-transformer`（SMILES/SDF/CSV 转换）、`statistical-modeler`（多 seed 显著性）几乎覆盖主要临时工具需求。
2. **工具注册表 = 代码层 ABox**：`Tool(sha256, input_schema, output_schema)` 可直接作为 capfactory `CodeFunction` 的扩展属性，`USED_BY` 边连到 `ExperimentNode`。
3. **声明式依赖先行**：与上一轮 GGR 的 `dep_gate` 思路一致 —— 训练复现环境必须先把 `rdkit/torch_geometric` 加入 `dependencies.json`，再装，再写代码。
4. **认证区间**：`arb_verify.py` 的「点值 → 区间」思想可迁移到 Perf Gap 与指标报导，避免「报一个裸均值」。
