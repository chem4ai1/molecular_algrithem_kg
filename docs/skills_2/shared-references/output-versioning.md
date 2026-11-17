# output-versioning · 结构决策变更的强制版本更新

> 源文件：`skills/shared-references/output-versioning.md`（141 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | schema / 产物声明 |
| **输出节点（对齐）** | 版本号（属性级） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：版本字段已在各 schema 中 |

## 1. 解决的问题
### 1.1 核心问题
规定哪些变更必须更新 SKILL.md version / Output Shape schema / 两者都更新。
### 1.2 为什么需要
防止静默改 schema 导致消费者解错、审计对不上；`Fail immediately if a changed section is not in the declared file list.`
### 1.3 不做的后果
输出格式变了但契约与验证器没变，产生 phantom artifacts。

## 2. 输入
### 2.1 输入知识节点
`changelog.section / change_kind`；`output_shape`；`schema_version`；`manifest-required`；`verdict-required`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `/artifact-registry` 独占输出结构判定。
### 2.3 输入产物
`artifact-registry.md`、`output-manifest.md`。

## 3. 输出
### 3.1 输出知识节点
version bump 规则；4 步流程（定位文件 → 改 → 更新 section → 更新 version）；`List every changed file by relative path`。
### 3.2 输出产物
SKILL.md version / Output Shape schema 变更；changelog。
### 3.3 传递片段
无。

## 4. 判定与门
Output Shape 变 → bump schema；结构/流程变 → bump skill version；生产消费同步；全部受影响文件必须列出。

## 5. 上下游
`/artifact-registry` → 本契约 → 所有 skill 的 version / schema / manifest / verdict 同步。

## 6. 映射
改 `Benchmark.protocol` 等 schema 时，必须同步 `extraction/contracts.py`、`validator.py`、`tbox_v4.py` 版本号。
