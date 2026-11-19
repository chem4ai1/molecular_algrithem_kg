# 节点作用映射与 data3 代码节点补全（小样本）

## 1. 已确认：每个节点类型都有作用/来源/阶段

新增 `data/node_roles.yaml`，登记：

- 语义层 6 类
- 应用层 54 类

每条包含：

```yaml
role:    这个节点是干什么的
source:  从哪里来（抽取 / B类聚合 / 代码 AST / WritingContext / miner）
phases:  服务哪些 P0–P11 阶段
note:    补充说明
```

新增 `scripts/check_node_roles.py`，并接入 `.git/hooks/pre-commit`：

```
✅ 节点作用登记完整：语义层 6 / 应用层 54
```

这一步回答了“每个语义层节点都有其作用、每个应用层节点都有其来源和作用”。

## 2. data3 新数据

`data/data3` 中发现：

| 内容 | 数量 |
|---|---:|
| manifest 论文 | 31 |
| manifest 仓库 | 50 |
| 本地代码仓库目录 | 48 |
| paper/ 下 PDF | 31 左右 |
| 代码仓库中的示例 PDF | 74 左右 |
| Python 文件 | 1669 |

manifest 的关键结构：

```json
paper.reason = "AutoSchemaKG (2025) [everyoneelse/AutoSchemaKG]"
repo.repo    = "everyoneelse/AutoSchemaKG"
repo.local   = "everyoneelse__AutoSchemaKG"
```

所以可以用 `[owner/repo]` 精确把论文关联到代码仓库，补 `Paper --HAS_CODE--> CodeRepository`。

## 3. 代码节点抽取小样本

新增 `stages/2_knowledge/extract_code_nodes.py`：

### 语义层

```
Paper --HAS_CODE--> CodeRepository --HAS_FUNCTION--> CodeFunction
```

### 应用层

```
CodeArtifact
CodeUnit        （一个 .py 文件）
CodeSymbol      （类/函数）
Dependency      （import 的第三方包）
EntryPoint      （main/train/run 或含 __main__）
EnvSpec         （requirements/environment/pyproject/setup）
TestUnit        （test_*.py）
```

关系：

```
CodeUnit --CONTAINS--> CodeSymbol
CodeUnit --DEPENDS_ON--> Dependency
EntryPoint --IN_UNIT--> CodeUnit
EntryPoint --USES_ENV--> EnvSpec
TestUnit --TEST_IN--> CodeUnit
```

### 小样本结果（`--limit 5 --max-files 12`）

```json
{
  "before": {"nodes": 374, "assertions": 433},
  "after":  {"nodes": 923, "assertions": 938},
  "stat": {
    "papers": 4,
    "repos": 4,
    "functions": 204,
    "codeunits": 41,
    "symbols": 204,
    "deps": 69,
    "entrypoints": 13,
    "env": 2
  }
}
```

成功关联的论文—仓库：

```
2505.23628 → everyoneelse/AutoSchemaKG
2201.11147 → zjunlp/OntoProtein
2104.07396 → daiquocnguyen/GNN-NoGE
1906.12089 → nheist/Cat2Ax
```

所有新增代码节点都带 `source` 和 `miner=code_extract`，可追溯。

## 4. 节点到阶段的映射（摘要）

| 阶段 | 主要语义层节点 | 主要应用层节点 |
|---|---|---|
| P0 选题与形式化 | Paper | ProblemAnchor, ProblemTaxonomy, ProblemFormulation, ResearchQuestion |
| P1 技术路线 | Algorithm, AlgorithmModule | TechnicalRoute, MethodLineage, GapTriple, IdeaCandidate |
| P2 数据构造 | Paper/Benchmark | DatasetSpec, DataContract, EvaluationNorm |
| P3 代码实现 | CodeRepository, CodeFunction | CodeArtifact, CodeUnit, CodeSymbol, Dependency, EntryPoint |
| P4 训练 | AlgorithmModule/CodeFunction | TrainingRun, RunArtifact, ExecutionRun |
| P5 Baseline | Benchmark, Algorithm | BaselineResult, LeaderboardEntry, MetricDefinition |
| P6 主实验 | Benchmark, Paper.result_tables | MainResultTable, ResultTable, Evidence |
| P7 消融分析 | AlgorithmModule, Benchmark | AblationTable, CaseStudy, FailureMode, Limitation |
| P8 图表 | Paper.figures | FigurePlan, FigureAsset |
| P9 写作 | Paper.section_map | SectionPlan, SectionDraft |
| P10 引用 | Paper.references | CitationVerification, CitedPaper, SourcePaper |
| P11 复现包 | CodeRepository, CodeFunction | ReproductionPackage, EnvSpec, EntryPoint |

完整 60 个节点类型见 `data/node_roles.yaml`。

## 5. 为什么不现在直接全量

**建议先更新修正，再小样本看效果，再做全量。**

原因：

1. E1/E2 的 LLM/规则分层刚改完，A/B 只验证了 4 篇
2. `research_question` 和 `arch_modules` 两个模板问题还没修：
   - research_question 过短
   - arch_modules 粒度太粗
3. 代码节点抽取刚在小样本跑通，还没覆盖：
   - 非 Python 实现（Java/RDF/OWL 仓库）
   - 仓库与论文的 1:N 关系
   - `CodeFunction → AlgorithmModule` 的自动对齐
4. data3 的 31 篇论文还没做语义抽取，只补了代码节点
5. 全量跑会把“未验证的模板 + 未对齐的代码节点”固化为大图，返工成本高

## 6. 建议顺序

```
① 修两个模板问题（research_question 长度、arch_modules 不合并）
② 再跑 4–6 篇新数据（含 2 篇 data3 图/本体论文）看效果
③ 确认字段稳定后，全量跑 52 篇 + data3 31 篇
④ 合并 B 类图谱与代码图谱
⑤ 再做统一主图和完整决策链
```

## 7. 复现

```bash
PYTHONPATH=src python3 scripts/check_node_roles.py
PYTHONPATH=src python3 stages/2_knowledge/extract_code_nodes.py --limit 5 --max-files 12
```
