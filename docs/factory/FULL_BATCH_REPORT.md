# 52 篇全量抽取 · 图谱与决策链实测报告

> 后端：Ernie (`baidu/ernie-5.5-flash-preview:free`) 优先 + 本地 vLLM 兜底（429 限流时自动切换）。
> 论文：52 篇 PDF（seed + A/B/C/D/E/F 六类）。

## 1. 抽取结果

```
52 篇全部成功（ok=48, skip=4, fail=0），耗时 1222s（约 20 分钟）
语义图：355 节点 / 317 断言
完整知识图：374 节点 / 429 断言
```

**paradigm 分布**：design 32 / empirical 9 / formal 4 / interpretive 2 / 未判 5
**evidence_type 分布**：experimental 32 / simulational 7 / derivational 6 / interpretive 2 / 未判 5

## 2. B 类图谱（从 52 篇聚合，有统计意义）

| 节点 | 数量 | 实例 |
|---|---|---|
| MethodLineage | 6 | reaction_prediction(10 方法) / molecule_generation(9) / other(8) … |
| EvaluationNorm | 4 | experimental/simulational/derivational/interpretive |
| FailureModeLibrary | 1 | **9 条阴性结果 + 40 条局限**（6 篇时是 0 条阴性） |
| VenueProfile | 1 | unknown（PDF 未抽 venue，如实记录） |

**从论文聚出的领域规范（非硬编码）**：

```
experimental    → optimization quality / round-trip consistency / logP / template adherence
simulational    → oracle budget / synthetic complexity / SA / property scores
derivational    → docking / universality / toxicity / efficacy
```

## 3. 实际使用尝试（三条查询）

### 3.1 按领域查规范
```
query_evaluation_norm(g, "experimental")
  → n_papers=32, fidelity=numerical,
    metrics=[optimization quality, round-trip consistency, logP]
```
用途：④ 主张形式化时，Claim.expected_fidelity 从这条规范查出，不手写。

### 3.2 按 task_type 查前沿基线
```
query_frontier_baseline(g, "reaction_prediction")
  → ASKCOS / Double-Ended Synthesis Planning (DESP) / Disconnect…
query_frontier_baseline(g, "molecule_generation")
  → Field-based Molecule Generation (FMG) / SynFlowNet / RGFN
query_frontier_baseline(g, "synthesizability")
  → found=False（该类 task_type 未出现，如实回落）
```
用途：② 领域定位时，GapTriple.frontier_baseline 从真实方法族谱查出。

### 3.3 失败模式检查
```
query_failure_checks(g) → 9 negative + 40 limitations
  样例："仅覆盖 SHACL 的一个子集，未给出完整形式语义"
        "仅考虑无否定的 datalog 规则…"
```
用途：⑦ 证据审计时，grade 依据真实失败模式计算。

## 4. 决策链（8 阶段 + 4 次查询）

```
seed 2512.20333
  ① ProblemAnchor (Q-ID 冻结)
  ② GapTriple    ← query_frontier_baseline → lineage:factory:molecule_optimization
                    frontier = "Saturn / AgentDrug / MultiMol"
  ③ IdeaCandidate (mechanism + falsification_condition)
  ④ Claim         ← query_evaluation_norm → norm:factory:derivational
                    fidelity = "qualitative"   ⚠️ 见下方发现
  ⑦ grade         ← query_failure_checks → failurelib:factory (9 neg + 40 lim)
  ⑧ SectionPlan + FigurePlan(claim_ref) ← query_venue_profile → found=False（诚实）
  ⑩ ReproductionPackage (verification=pending)
```

## 5. 关键发现与问题

### ✅ 全量让 B 类图谱真正有了统计意义
- 6 篇时 FailureModeLibrary 的 negative_results=0；52 篇时 **9 条**
- MethodLineage 从 3 组增到 6 组，能按 task_type 查出具体前沿方法
- EvaluationNorm 的 accepted_metrics 从几个增到 12 个/类

### ⚠️ 发现 1（已修）：evidence_type 判定有偏
seed 论文 (2512.20333, SynCraft) 被判为 `derivational`，导致 Claim fidelity 查出
`qualitative`——但这篇论文有 benchmark。已在 `build_factory_graph.py` 加交叉校验：
有 `Benchmark.metrics` 且被判 derivational/interpretive 时纠正为 experimental
（trace 记录 original=derivational → used=experimental, corrected=True），
Claim fidelity 随之变为 `numerical`。

### ⚠️ 发现 2：venue 仍然全缺失
52 篇 PDF 都没抽出 venue。VenueProfile 是空壳。需外部元数据（DBLP/S2）补全。

### ⚠️ 发现 3：Ernie 限流
纯 Ernie 跑到第 4 篇就 HTTP 429；加 vLLM 兜底后 0 失败。
**结论**：Ernie 适合小批量/单篇调试，全量必须配兜底。

### ⚠️ 发现 4：category 没进图
52 篇的 A-F 类别在 papers.yaml 里有，但没写进 Paper 节点属性。
影响：无法按「合成性/逆合成/agent」等主题切片检索。建议补。

## 6. 产物与复现

```
data/extract_target/batch/          6 个抽取对象配置（papers + B1/B2/B3 + C1/C2）
data/docx/                          52 篇 md
storage/sciforge/semantic_extraction/  52 份抽取报告
storage/sciforge/semantic_factory_52.json    语义层图 355/317
storage/sciforge/factory_knowledge.json       完整知识图 374/429
storage/sciforge/factory_decision_trace.json  8 阶段 + 4 查询
```

```bash
PYTHONPATH=src python3 stages/1_extraction/run_batch_ernie.py
PYTHONPATH=src python3 stages/2_knowledge/build_factory_graph.py
```
