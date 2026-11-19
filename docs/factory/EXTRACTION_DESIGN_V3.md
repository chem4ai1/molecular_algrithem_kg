# 抽取内容与节点设计 v3（支撑 P0–P11）

> 回答：按真实论文流程，语义层还要抽什么？应用层节点怎么来？哪些单篇可抽、哪些要跨论文聚合？

## 1. 第一原则：三层分工不能混

| 层 | 存什么 | 判据 | 例子 |
|---|---|---|---|
| **语义层**（A） | 论文**写了什么** | 能在原文指到一句话/公式/表格 | MECo 用 `ZINC + ChEMBL35`，去泄漏 `Tanimoto ≥ 0.6` |
| **跨论文图谱**（B） | 多篇**共同的规律** | 单篇抽不出，需聚合 | 编辑序列流派 4 篇的推荐指标集 |
| **应用层**（C） | 本次**决定做什么** | 带 run_id，是选择 | 我这次用 ZINC 子集 10 万条，阈值 0.6 |

**关键错误要避免**：把「MECo 用了 ZINC」当成「我这次要用 ZINC」——前者是事实（语义层），后者是决定（应用层）。

## 2. 语义层：Paper 需新增 11 个字段

当前 28 字段偏「问题/贡献/写作」，**缺「实验怎么做」的一半**。

| 新字段 | 类型 | 从哪抽 | 服务阶段 | 证据 |
|---|---|---|---|---|
| `formal_def` | str | Methods 里的公式（LaTeX 片段或文字描述） | P0 | MECo `Mo=F(Mi,T)` |
| `old_forms` | list[dict] | 「prior work formulates as」段落 | P0 | MECo 3.1 旧式 |
| `method_limits` | list[str] | 「suffers from two key limitations」 | P0 | MECo「编辑不透明/违反化学原则」 |
| `arch_modules` | list[dict] | 方法节的模块描述（名+作用） | P1/P3 | MECo reasoning LLM + code LLM |
| `why_not_other` | str | 对比段落里「instead of / rather than」 | P1 | — |
| `key_challenge` | str | 「the main challenge is」 | P1 | SynFlowNet 3.2 backward path |
| `data_sources` | list[str] | 数据库名（ZINC/ChEMBL/USPTO…） | P2 | MECo 3.3 |
| `dedup_rule` | str | Tanimoto/identity 阈值句 | P2 | MECo 4.1 `≥0.6` |
| `split_spec` | str | train/val/test 比例 | P2 | — |
| `hyperparams` | list[dict] | iterations/temperature/learning rate 等 | P4/P7 | AgentDrug 4.2 迭代次数 |
| `result_tables` | list[dict] | 表格结构（列=方法，行=指标，值） | P6 | MECo Table 1 |

**已实现验证**：`data_sources`/`dedup_rule`/`split_spec` 已能从 52 篇真抽（MECo 抓到 `Tanimoto ≥ 0.6`）。

## 3. 语义层：新增 2 个类（跨论文才能建的不算这里）

| 类 | 为什么必须是节点不是属性 | 服务 |
|---|---|---|
| `ResultTable` | 表格是「方法×指标×值」的矩阵，还要被 P6 直接转 LaTeX；属性装不下多维结构 | P5/P6 |
| `FigureSpec` | 每张图要绑定 claim + 数据源 + 类型，需独立 id | P8 |

> 注：`DatasetSpec`/`Architecture` 不需要在语义层建类——它们用 Paper 属性即可（因为单篇论文只有一份）。

## 4. 应用层：P0–P11 节点从哪来

| 节点 | 来源 | 生成方式 |
|---|---|---|
| `ProblemFormulation` | `Paper.formal_def` + `old_forms` + `method_limits` | 读语义层 → 本次改写 |
| `TechnicalRoute` | `Paper.arch_modules` + `method_family` 社区模板 | 读语义层 + B 类模板 |
| `DatasetSpec` | `Paper.data_sources` + `dedup_rule` + 本次数据盘点 | **本次决定**（可引用语义层） |
| `CodeArtifact` | 本地仓库 AST + `arch_modules` 对齐 | 扫代码 |
| `TrainingRun` | 本次训练日志 + `Paper.hyperparams` 参照 | 跑训练 |
| `BaselineResult` | **B 类**：同 task_type 的方法名 + 本次复现数值 | 查图谱 + 跑实验 |
| `MainResultTable` | 本次 Evidence 聚合 + `Paper.result_tables` 做格式参照 | 生成 |
| `AblationTable` | `Paper.arch_modules` + `hyperparams` 决定消融什么 | 本次跑 |
| `CaseStudy` | 本次挑一个样本 | 本次跑 |
| `FigurePlan` | `FigureSpec` + claim 绑定 | 生成脚本 |
| `SectionPlan` | **B 类** VenueProfile 模板 + `Paper.section_map` | 按流派生成 |
| `CitationVerification` | 本次引用列表逐条核 | 查库 |
| `ReproductionPackage` | 本次产物打包 | 打包 |

**关键**：P5 的 baseline 名字来自 **B 类图谱**（同 task_type 的方法池），不是语义层——因为「哪些是同类 SOTA」需要跨论文比较。

## 5. 跨论文图谱：新增 1 个

| 节点 | 从哪聚合 | 服务 |
|---|---|---|
| `BaselinePool` | 按 `task_type` 聚合 `Algorithm`，带出现次数与指标 | P5/P6 |

现有的 `MethodLineage`/`EvaluationNorm`/`FailureModeLibrary`/`VenueProfile` 继续用，不新增。

## 6. 抽取方式分三类（实施要靠这个分）

| 类型 | 抽什么 | 能否自动化 | 当前状态 |
|---|---|---|---|
| **① 规则可抽** | `data_sources` / `dedup_rule` / `hyperparams` / `split_spec` | ✅ 完全自动 | ✅ 已实现（52 篇） |
| **② LLM 抽** | `formal_def` / `old_forms` / `method_limits` / `arch_modules` / `why_not_other` | ✅ 需 LLM | ⚠️ 部分（E1 有 claims/gaps，缺这些） |
| **③ 跨论文聚合** | `BaselinePool` / `EvaluationNorm` / `VenueProfile` | ✅ 可自动（Leiden + 统计） | ⚠️ 部分 |

**② 是最大缺口**：`formal_def`/`arch_modules` 这些是论文方法节的核心，现在完全没抽。

## 7. 建议的抽取实施顺序

```
第 1 步（规则，零成本）：data_sources / dedup_rule / hyperparams / split_spec
        → 已在 52 篇上验证，直接写入 E1 契约
第 2 步（LLM，中等成本）：arch_modules / formal_def / method_limits
        → 在 E2（算法阶段）加，因为方法节信息最密
        → 用 compact prompt（Ernie 长 prompt 会返回空）
第 3 步（聚合）：BaselinePool
        → 从 Algorithm.task_type 聚合，一次建好
第 4 步（表格）：ResultTable
        → 表格是结构化数据，用规则解析 md 表格 + LLM 补表头
```

## 8. 为什么这样设计（三个判断）

### 8.1 语义层不要建 DatasetSpec 类

因为一篇论文只有一份数据构造，是「1:1 属性」而非「1:N 关系」。
建类会让图谱变成「每篇一个 DatasetSpec 节点」，没有查询价值。

### 8.2 P5 baseline 必须走 B 类图谱

「MECo 的 baseline 是 Qwen2.5」这是事实，但「做编辑序列该对比哪几个」是**跨论文规律**——
需要看 4 篇编辑序列论文都用谁对比。单篇抽不出来。

### 8.3 表格要单独建类

`ResultTable` 是「方法×指标」矩阵，属性装不下；而且 P6 要把它直接转 LaTeX，
需要独立 id 做 claim 绑定（`table_ref`）。

## 9. 当前已完成 vs 待做

| 项 | 状态 |
|---|---|
| 10 个 P0–P11 节点类 | ✅ 已建（53 类） |
| 3 个字段扩展（Evidence/FigurePlan/SectionPlan） | ✅ |
| D7 数据模态（34 篇重判） | ✅ |
| 超参级消融（37 篇） | ✅ |
| baseline 候选（50 篇） | ✅ |
| P2 去泄漏真跑（RDKit Tanimoto） | ✅ |
| P6 表格 → LaTeX | ✅ |
| P9 章节骨架（按流派） | ✅ |
| P8 绘图脚本（真出 PDF） | ✅ |
| **语义层 11 个新字段** | ❌ 未抽（第 1/2 步） |
| **ResultTable / FigureSpec 类** | ❌ 未建 |
| **BaselinePool 聚合** | ❌ 未建 |

**下一步最该做**：第 1 步（规则抽 4 个字段，零成本）+ 建 `ResultTable` 类。
这两项做完，P2 和 P6 就能端到端跑通（从论文抽规则 → 生成表格）。
