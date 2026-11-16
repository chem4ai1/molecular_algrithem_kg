# 节点 Schema（27 份）

> 每类一份，自动从 `tbox_v4` / `applayer/tbox.py` 提取属性、关系、填充率；
> 手工补「抽取来源 / 使用场景 / 边界」。

```
docs/schema/
├── README.md            本文件（分层 + 抽取/使用全链路）
├── semantic/            语义层 6 类（客观事实）
│   ├── Paper.md  Algorithm.md  AlgorithmModule.md
│   └── CodeRepository.md  CodeFunction.md  Benchmark.md
└── application/         应用层 21 类
    ├── 论文域    ProblemCategory  Contribution  ResearchGap
    ├── 方法域    Assumption  FailureMode  EvidenceNorm
    ├── 实验域    ExperimentArm  LeaderboardEntry  MetricDefinition
    ├── 证据域    Evidence  Limitation  CitedPaper  SourcePaper
    └── 写作域    SectionPlan  SectionDraft  FigureAsset
                  ReviewPoint  FailureCheck  ConsultedPaper  DataContract
```

## 1. 分层原则

| | 语义层（6） | 应用层（21） |
|---|---|---|
| 内容 | 论文里**客观写了什么** | 面向任务**派生/判定/选择**的东西 |
| 依据 | 可在原文找到文字/表格 | 需要聚合、判定或选择 |
| 生命周期 | 永久（随抽取增量） | global / task-w / task-r |
| 改动的代价 | 高（动 `stable_key` 会让历史 `spec_hash` 失效） | 低（可重算） |

**判据**：一句话能说清且不需被引用 → 属性；只描述一对对象 → 边属性；需独立 id / 跨论文聚合 / 作为评分单位 → 节点。

## 2. 抽取链路（一次 + 二次）

```
原论文 md
   │
   ├─ E1  Paper        → paradigm / evidence_type / contributions / gaps / figures / section_map
   ├─ E2  Algorithm    → assumptions / novelty_basis / modules[]（AlgorithmModule）
   ├─ E3  Benchmark    → protocol / metrics[].contribution_link
   ├─ E4  values       → model_results[]（outcome_class / seeds）
   ├─ E5  relations    → module→tool / module→formula
   └─ E6  lineage      → SUBCLASS_OF（assumption_delta）
          │
          ▼  写入语义层（6 类 / 9 关系）
   ┌──────────────────────────────────────────┐
   │ batch10_semantic_v4.json  6001 节点       │
   └──────────────────────────────────────────┘
          │
          ├─ 规则挖掘（mine_all，13 个）→ 应用层 global 节点
          │    contributions / experiment_arms / assumptions / failure_modes
          │    evidence_norms / figures / section_plans / review_points
          │    metrics / contracts / evidence / limitations / source_papers
          │
          └─ 二次抽取（refine R1–R6）→ 补充语义层缺的字段
               R1 Contribution  R2 ExperimentArm  R3 Assumption
               R4 FigureAsset   R5 CitedPaper     R6 ResearchGap
```

## 3. 使用链路（复现 + 写作）

| 用途 | 读取哪些节点 | 产出 |
|---|---|---|
| **复现** | Algorithm / Module / CodeFunction / Benchmark | 5 类 SAU → R0–R6 门控 → verdict |
| **写作** | Contribution / ResearchGap / ExperimentArm / EvidenceNorm / FailureMode | 章节计划 + 素材 + 措辞约束 |
| **审计** | 全部 + `Evidence.char_span` | 四类泄露 / 逻辑一致性 / 引用三层 |

**任务级实例**（`WritingContext`，见 `application/ResearchGap.md`）：
只在使用时建，id 带 `run_id`，永不写回全量图。

## 4. 生命周期

| 类型 | 类 | 存储 |
|---|---|---|
| global（15 语义 + 15 应用） | 客观事实与领域知识 | `batch10_semantic_v4.json` / `app_writing.json` |
| task-w（4） | ResearchGap / CitedPaper / ReviewPoint / SectionDraft | `storage/writing_runs/<run_id>.json` |
| task-r（2） | FailureCheck / ConsultedPaper | 同上 |

## 5. 重新生成

```bash
PYTHONPATH=src python3 scripts/gen_schema_docs.py
```

改属性/关系后重跑即可；「使用场景」与「边界」在脚本的 `USAGE` / `NOTE` 字典里维护。
