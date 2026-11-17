# discipline-paradigm · 四范式按问题性质选择

> 源文件：`skills/shared-references/discipline-paradigm.md`（90 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 + 阶段2 |
| **SciForge 26 节点** | `1b`/`6` |
| **输入节点（对齐）** | `ResearchQuestion` |
| **输出节点（对齐）** | `DomainProfile.paradigm` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 在 `DomainProfile` 加 `paradigm` 属性（formal/empirical/interpretive/design） |

## 1. 解决的问题
### 1.1 核心问题
定义 formal / empirical / interpretive / design 四种范式，按问题性质而非学科标签选择。
### 1.2 为什么需要
各范式 truth standard / verification / output 不同；`Never hard-code discipline-to-paradigm mapping`；允许运行时切换。
### 1.3 不做的后果
用错真理标准（如用数值证据判解释性论文）。

## 2. 输入
### 2.1 输入知识节点
`Problem.type`；`Verification.method`；`Output.format`；`Paradigm.truth_standard / fidelity_gate / fallback`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`— paradigm: interpretive|formal` 示例；See Also `discipline-context.md`、`discipline-writing.md`、`venue-profiles.md`。
### 2.3 输入产物
`domain-signature.json`。

## 3. 输出
### 3.1 输出知识节点
formal=Proof；empirical=Reproducible experiment；interpretive=Explanatory power/coherence；design=Functional implementation；Paradigm.figure / paper_structure / fallback。
### 3.2 输出产物
无独立 schema；4-paradigm config。
### 3.3 传递片段
Paradigm affects verification method, not idea quality；No paradigm is "better"。

## 4. 判定与门
| 范式 | 保真度 |
|---|---|
| formal | symbolic ≥ numerical |
| empirical | numerical ≥ qualitative |
| interpretive | qualitative |
| design | numerical |
| 失败 | 回退 conjecture+evidence / theoretical prediction / hypothesis / design proposal |

## 5. 上下游
问题输入 → 本契约 → `/auto-pipeline`、验证、绘图、`/paper-writing`。

## 6. 映射
分子项目选 design（prototype/benchmark/ablation）或 empirical（statistical/numerical validation）。
