# 论文生成全过程（当前实现状态版）

> 整合：12 阶段主线 × 6 维分类路由 × B 类图谱 × C 类决策节点 × 门控。
> 标注：✅ 可跑 / ⚠️ 部分 / ❌ 设计中

## 0. 全景

```
                        ┌─────────────────────────────────────┐
                        │  语义层（A 类事实，52 篇已抽）        │
                        │  Paper 28 字段 / Algorithm 10 /      │
                        │  Module 7 / Benchmark 13 / Code 6    │
                        └──────────────┬──────────────────────┘
                                       │ 离线聚合（Leiden + 规则 + LLM）
                        ┌──────────────▼──────────────────────┐
                        │  B 类图谱（物化视图，一次建长期用）    │
                        │  MethodFamily 社区 4 个              │
                        │  EvaluationNorm 4 个（带 rating）    │
                        │  FailureModeLibrary 1（9阴+40局限）  │
                        │  VenueProfile（50% 缺）              │
                        └──────────────┬──────────────────────┘
                                       │ 在线查询（4 条 query_*）
   ┌───────────────────────────────────▼───────────────────────────────────┐
   │                     12 阶段论文生成主线                                │
   │  ① 锚定 → ② 学习 → ③ 检索 → ④ 想法 → ⑤ 新颖 → ⑥ 预注册              │
   │   → ⑦ 素材 → ⑧ 起草 → ⑨ 拒稿 → ⑩ 复审 → ⑪ 反驳 → ⑫ 自检          │
   └───────────────────────────────────┬───────────────────────────────────┘
                                       │ 每阶段产出 C 类决策节点（带 run_id）
                        ┌──────────────▼──────────────────────┐
                        │  C 类决策节点（task 级，可回放）      │
                        │  ProblemAnchor / GapTriple /         │
                        │  IdeaCandidate / Claim / ExecutionRun│
                        │  Evidence / SectionPlan / FigurePlan │
                        │  ReproductionPackage                 │
                        │  + decisions[] append-only ledger    │
                        └─────────────────────────────────────┘
```

**三条数据通路**：
1. **A → B**：离线聚合，一次建好（Leiden + 规则 + LLM）
2. **B → C**：在线查询，`query_*()` 带 `{value, found, source, via}`
3. **C → 门**：三值判定 `SUPPORTED/REFUTED/INSUFFICIENT` + confidence

## 1. 12 阶段详表

| # | 阶段 | 读哪些分类维度 | 调哪些 skill ✅ | 产出 C 类节点 | 门控 | 失败去向 |
|---|---|---|---|---|---|---|
| **01** | 问题锚定 | D4 问题类型<br>D3 研究范式 | `intake-triage`<br>`domain-signature` | `ProblemAnchor`<br>（Q-ID/判据/边界/可行性） | Q-ID 冻结<br>可回答判据非空 | 退回重述问题 |
| **02** | 领域学习 | **D1 方法流派**<br>D2 证据范式<br>D5 venue | `universal-retrieval`<br>`method-registry` | `MethodologyProfile`<br>`EvidenceNorm`(learned) | 六维 profile 齐全 | 补检索/降置信 |
| **03** | 广域检索 | **D1 流派社区**<br>D4 问题类型 | `universal-retrieval` | `LiteratureItem`(candidate)<br>`CitationItem` | 候选 ≥ N 篇<br>每篇带 cite_key | 扩召回 |
| **04** | 想法生成与证伪 | D1 流派<br>D3 范式 | `idea-discovery`<br>`adversarial-falsification` | `GapTriple`<br>`IdeaCandidate`<br>`FalsificationRecord` | mechanism 非空<br>falsification_condition 非空 | 想法重生成 |
| **05** | 新颖性人择 | **D1 流派社区**<br>D2 证据范式 | `novelty-check`<br>`kill-argument` | `Novelty`(判定)<br>`Contributions`(排序) | 碰撞矩阵无重复 | 换角度/放弃 |
| **06** | 预注册方法 | **D2 证据范式**<br>**D3 研究范式** | `method-registry`<br>`invariant-check` | **`Claim`**<br>`AssumptionLedger`<br>`MethodLock`<br>`ExperimentMatrix` | polarity + refutation_condition<br>+ 8段 registry hash | **BLOCKED** |
| **07** | 素材装配 | **D1 流派**（选工具链）<br>D6 交付协议 | `experiment-execution`<br>`experiment-ladder`<br>`ablation-planner` | `ExecutionRun`<br>`Evidence`<br>`AblationLedger`<br>`NegativeResultLog` | 基线同口径复现<br>seeds ≥ 3<br>toy 通过 | 回退 ⑥ 改矩阵 |
| **08** | 起草 | **D5 venue**<br>D2 证据范式（措辞上限） | `paper-writing`<br>`unified-plotting`<br>`citation-audit` | `SectionPlan`<br>`FigurePlan`(claim_ref)<br>`SectionDraft` | 每图绑定 claim<br>每句可追溯<br>措辞不越级 | 重写该节 |
| **09** | 最强拒稿论证 | D2 证据范式<br>**B: FailureModeLibrary** | `kill-argument`<br>`leakage-audit`<br>`result-to-claim` | `ReviewPoint`<br>`ClaimGrading`<br>`AuditVerdict` | 三类泄露为 0<br>结论可推出 | 回退 ⑥/⑦ |
| **10** | 跨模型复审 | D5 venue<br>D2 证据范式 | `auto-review-loop`<br>`quality-gate` | `ReviewPoint`<br>`GateVerdict` | 六维评分 ≥ 阈值 | 修订/降档 |
| **11** | 反驳响应 | — | `rebuttal` | `Rebuttal`<br>`RevisionLog` | 每条攻击有回应 | 补充实验 |
| **12** | 自检核验 | D5 venue<br>D6 交付协议 | `citation-audit`<br>`publishability-score`<br>`paper-compile` | `CitationVerification`<br>`ReproductionPackage`<br>`PublishabilityScore`<br>`FinalDecision` | 三层引用核验<br>verification=pass | **不得投** |

## 2. 与 10 阶段表的对应

| 10 阶段（你之前的版本） | 12 阶段（仓库版） | 说明 |
|---|---|---|
| ① 问题锚定 | **01** | 1:1 |
| ② 领域定位 | **02 + 03** | 拆成「学习规范」和「检索文献」 |
| ③ 想法生成与筛选 | **04** | 1:1（含证伪） |
| ④ 主张形式化与承诺 | **06** | 关键：对应「预注册方法」 |
| ⑤ 实现与最小验证 | **07 前半** | ExecutionRun + toy |
| ⑥ 正式证据生产 | **07 后半** | Evidence + 消融 |
| ⑦ 证据审计与定档 | **09 + 10** | 拆成「自我拒稿」和「跨模型复审」 |
| ⑧ 叙事设计与结构 | **08 前半** | SectionPlan + FigurePlan |
| ⑨ 起草与内部对抗 | **08 后半 + 09** | 起草 + 自检 |
| ⑩ 终检与复现交付 | **10 + 11 + 12** | 复审 + 反驳 + 自检 |

**12 阶段比 10 阶段多出的拆分是合理的**：
- 02/03 拆开是因为「读论文建规范」和「检索候选」用的知识不同（前者 B 类，后者向量）
- 09/10 拆开是因为「自己当审稿人」和「换模型审」防的是不同偏差
- 11/12 拆开是因为「回应质疑」和「最终核验」是不同动作

## 3. 三个必须独立的阶段（最容易合并、也最容易崩）

### ④/06 主张形式化

```
❌ 错误：想法 = 主张。跑完实验再挑好看的指标。
✅ 正确：Claim 必须有 polarity + refutation_condition + locked_at
         expected_fidelity 从 EvaluationNorm 查，不许 LLM 自判
```

**已实现**：`ctx.formalize_claim()`，无 `refutation_condition` → 直接 **BLOCKED**（实测触发）。

### ⑧ 叙事设计

```
❌ 错误：一边写句子一边想结构，结构服从已写段落。
✅ 正确：先定 SectionPlan + FigurePlan（每图绑定 claim），再起草。
```

**已实现**：`ctx.design_narrative()`，`FigurePlan.claim_ref` 必填。

### ⑩/12 复现交付

```
❌ 错误：附录写一句「代码将开源」。
✅ 正确：ReproductionPackage 独立节点，verification != pass 不得投。
```

**已实现**：`ctx.deliver()`，`verification="pending"` → **BLOCKED**（实测触发）。

## 4. 6 维分类在各阶段的使用

| 维度 | 覆盖率 | 主要服务阶段 | 没它会怎样 |
|---|---|---|---|
| **D1 方法流派** | 100% | 02/03/04/07 | ②找不到该借鉴谁（SynCraft 混在 13 篇泛 optimization 里） |
| **D2 证据范式** | 100% | 02/05/06/08/09 | ⑥无法定保真度，⑧措辞会越级 |
| **D3 研究范式** | 100% | 01/06 | ④主张结构错（把 design 写成 theorem） |
| **D4 问题类型** | 98% | 01/03 | ①问题分类粗 |
| **D5 venue** | 50% | 08/10/12 | ⑧⑩⑫只能按默认惯例，无法 venue 定制 |
| **D6 交付协议** | 100% | 07/12 | ⑫不知道该不该做复现包 |

## 5. 门控的三层结构

```
第一层：契约门（阶段内）
  Claim 无 refutation_condition → BLOCKED
  FigurePlan 无 claim_ref → BLOCKED
  ReproductionPackage verification≠pass → BLOCKED

第二层：证据门（跨阶段）
  Claim expected_fidelity ← EvaluationNorm（不许自判）
  grade ← FailureModeLibrary 查询 + 三值判定
  edge_verdict: SUPPORTED / REFUTED / INSUFFICIENT + confidence

第三层：一致性门（全局）
  PROBLEM_HASH / method_hash 不漂移
  Claim → Evidence → SectionDraft 三级可追溯
```

## 6. 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| A 类抽取（52 篇） | ✅ | 0 失败，355 节点/317 断言 |
| 6 维分类 | ✅ 5/6 | 100/100/100/98/**50**/100 |
| B 类图谱（Leiden） | ✅ | 4 个流派社区 + rating + design_hint |
| B→C 查询（4 条） | ✅ | 带 `{found, source, via}` |
| C 类接口（6 个） | ✅ | `formulate_gap`/`formalize_claim`/... |
| 三值门 | ✅ | `SUPPORTED conf=0.885 supporting=[assertion:0430]` |
| Decision ledger | ✅ | `ctx.decisions` append-only |
| 阶段路由 | ⚠️ | 支持 phase 2/3/5/4/8/9/10，其他待补 |
| 12 阶段编排器 | ❌ | 目前是手工串，无缝编排引擎 |
| venue 元数据 | ⚠️ | 50%，需 DBLP/S2 API |
| 真实实验执行 | ❌ | ⑤⑦ 仍是演示数据，未接真实跑实验 |

## 7. 一句话

**12 个阶段，每个阶段只读它需要的分类维度、只调对应的 skill、只产出一类 C 节点、只过它自己的门。**
分类不是标签，是路由；C 节点不是记录，是承诺；门不是提示，是阻断。

当前最关键的三个待补：**阶段编排器**（把 12 阶段串成可执行流水线）、**venue 元数据**（接 DBLP/S2）、**真实实验执行**（⑤⑦ 接真实跑）。
