# plugin-router · 外部可复用插件注册表

> 源文件：`skills/shared-references/plugin-router.md`（108 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `CodeUnit`；`Dependency` |
| **输出节点（对齐）** | 插件调用（无节点） |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `ToolRegistration`，插件本身不进论文图 |

## 1. 解决的问题
### 1.1 核心问题
记录 12 个外部可复用插件的入口、deps、状态与降级路径，避免插件变更污染核心。
### 1.2 为什么需要
`all are EXTERNAL and REUSABLE`；`plugin changes do not alter the skill's internal logic`；plugin 缺失时按 Adaptive Degradation 处理。
### 1.3 不做的后果
把外部插件当内置硬依赖，插件不可用时整链崩。

## 2. 输入
### 2.1 输入知识节点
`plugin.name / trigger / entry / deps / status`；`capability`；`SourcePriority`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 orchestrator / universal-retrieval / unified-plotting 消费。
### 2.3 输入产物
`pipeline-adaptive-degradation.md`、`mcts-search-protocol.md`。

## 3. 输出
### 3.1 输出知识节点
`plugin_registry.13 项`；`PluginEntry.name/capability/trigger`；`external_status REUSABLE`。
### 3.2 输出产物
无新增文件；插件触发时按 Registry 条目调用。
### 3.3 传递片段
无。

## 4. 判定与门
`EXTERNAL AND REUSABLE`；缺失 → degradation（非静默 skip）；所有条目在 Registry 中有 entry。

## 5. 上下游
orchestrator / retrieval / plotting / review → 本注册表 → 插件调用与 fallback。

## 6. 映射
外部 RDKit / xtb / 分子可视化插件应作为 EXTERNAL REUSABLE，缺失走降级而非硬失败。
