# dynamic-tooling · 运行时按需生成、测试与注册缺失工具

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/dynamic-tooling/SKILL.md`（180 行）
> 类型：meta-skill · 横切（2.5 / 6a / 6b / 11） · 代码佐证：`scripts/dep_gate.py`、`scripts/security_scan.py`、`scripts/smoke_gate.py`、`scripts/arb_verify.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `2.5`/`6a`/`6b`/`11` |
| **输入节点（对齐）** | `CodeUnit`(global)；`Dependency`(global) |
| **输出节点（对齐）** | `CodeUnit`(global)；`CodeSymbol`(global) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 global 节点 `ToolRegistration`：`CodeUnit` 描述已有代码，工具注册表需要 `name/version/hash/smoke_test/usage_count` 且需跨 run 复用；不落语义层 |

## 1. 解决的问题

### 1.1 核心问题
当标准沙箱库不足时，运行时生成、测试并注册一个带显式契约的新工具。

### 1.2 具体场景 / 为什么需要
- `Define the tool's contract before writing code:` —— 先写 ToolContract 再写代码。
- `If the gap can be filled by installing a standard library (pip install), do not create a tool — delegate to /dynamic-sandbox with the package list.`
- 工具注册带 hash、smoke test、usage count，避免不可复现与错误传播。

### 1.3 不做的后果
- 遇「tool unavailable」直接死胡同；未测试工具进入流水线会产生系统性错误结果。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Gap` | `What is missing` | 调用方 | 必须 |
| `Gap` | `Why existing tools are insufficient` | 调用方 | 必须 |
| `Gap` | `The tool's scope` | 调用方 | 可选 |
| `Gap` | `Dependencies` | 调用方 | 可选 |
| `ToolInterface` | `Input / Output / Side Effects / Error Modes` | 调用方 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Tool Name / Purpose / Input / Output / Side Effects / Error Modes | 先定义工具契约 | 强制契约先行 |
| 缺口门 | pip install 可填 → 转 `/dynamic-sandbox` | 避免重复造轮子 |
| 契约 | `integration-contract.md`、`skill-config.md`、`output-manifest.md` | 集成/配置/产物清单 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| tool description + interface contract（未给固定路径） | 生成依据 |
| Tool Template Library：`symbolic-reasoner / statistical-modeler / knowledge-graph / formal-verifier / code-synthesizer / data-transformer / text-analyzer` | 7 类模板 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `ToolRegistration` | `name / version / path / hash / description / input_schema / output_schema / created_at / usage_count` |
| `ToolResult` | `status / tool_name / path / entry_point / smoke_test / usage` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `tools/tool_name/tool_name.py` | `__version__` / entry function | 持久工具 |
| `tools/registry.json` | registration | 持久注册 |
| `tools/temp/{session_id}_{tool_name}.py` | temporary | 会话临时，不注册 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `status=created\|updated\|failed` + entry_point + smoke_test + usage 例 | 调用方 | 明确用法 |
| usage 例：`from tools.custom_parser import parse; result = parse(data)` | 调用方 | 可复用 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 缺口门 | skill 内 | pip install 可填 | — | delegate `/dynamic-sandbox` |
| 测试门 | smoke test | `smoke_test=true` | — | fail → traceback + 3 fixes |
| 重试门 | skill 内 | `max_retries=2` | `2` | exceeded → caller decides |
| 注册门 | `py_compile` | pass before registration | — | fail 不注册 |
| 质量门 | skill 内 | ≤200 lines / no outside imports / no shell unless authorized | — | 违者拒绝 |
| 临时门 | skill 内 | `scope=session` | — | do not register |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| 标准沙箱库不足 / 能力缺口 | `/dynamic-tooling` | `/dynamic-sandbox` 执行；`/unified-plotting` 渲染 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `ToolRegistration / ToolContract` | `applayer` 能力扩展节点 | 建议新增 `ToolSpec / ToolRegistration` |
| `hash / smoke_test / registry` | `reprospec` 工具哈希校验 | 否 |
