# B 类图谱聚合 / C 类决策边预测：文献映射

> 用户的本质发现：
> **B 类节点 ≈ 图聚合（graph aggregation / community summary）**
> **C 类决策节点和门 ≈ 图的边预测（link prediction），只是用大模型范式实现。**
>
> 这个类比是成立的，而且有直接对应的论文线索。

## 1. 类比是否成立

| 本项目 | 图机器学习对应概念 | 是否成立 |
|---|---|---|
| B 类节点（EvaluationNorm / MethodLineage / FailureModeLibrary / VenueProfile）从 52 篇论文属性聚合 | 图聚合 / 社区发现 / 图摘要（graph aggregation, community detection, graph summarization） | ✅ 完全对应：跨节点聚出「群体规律」再建一个高层节点 |
| B 类节点回指来源论文的边（DERIVED_FROM_PAPERS / LINEAGE_OF） | 聚合后的 hyperedge / community membership | ✅ 对应 |
| C 类节点（GapTriple / Claim / IdeaCandidate）连接 B 类与 A 类 | 边预测 / 链接预测（link prediction）：判断「哪个 norm 支撑哪个 claim」 | ✅ 对应：我们的 `GROUNDED_IN` / `FULFILLS` 就是预测出的边 |
| 门（refutation_condition / verification） | 边的置信度 / 有效性判定（edge scoring, validity gating） | ✅ 对应：BLOCKED 就是预测边不成立 |
| `query_*()` 从 B 类查值注入 C 类 | 消息传递（message passing）：邻居聚合后更新目标节点 | ✅ 高度对应 |

**更精确的说法**：
- B 类 = **离线图聚合 + 物化视图**（materialized view）
- C 类 = **在线边预测 + 条件生成**（conditional link prediction with LLM）
- 门 = **边有效性验证**（edge validity check）

## 2. 对应论文

### 2.1 图聚合 / 社区摘要 → B 类节点

| 论文 | 年份 | 与本项目的对应 |
|---|---:|---|
| **From Local to Global: A Graph RAG Approach to Query-Focused Summarization** (Edge et al., Microsoft Research, arXiv:2404.16130) | 2024 | **最直接对应**。两阶段：① LLM 从文本抽实体关系建图；② Leiden 社区检测 + **社区摘要**。我们的 `EvaluationNorm` 从 32 篇 experimental 论文聚出指标集，就是「社区摘要」的领域特化版。 |
| **GraphRAG Global Community Summary Retriever** (Microsoft) | 2024 | 全局问题靠社区摘要回答，而非单 chunk。对应我们的「领域认什么证据」不能从单篇回答，必须查 Norm 节点。 |
| **Agentic Deep Graph Reasoning Yields Self-Organizing Knowledge Networks** (Buehler, MIT, arXiv:2502.13025; J. Mater. Res. 40, 2025) | 2025 | **领域最近**。LLM agent 迭代构建/精炼自组织知识网络。我们的 B 类图谱从 52 篇分子/材料论文聚合，方法高度同源。 |
| **SEMMA: A Semantic Aware Knowledge Graph Foundation Model** (EMNLP 2025) | 2025 | 跨图迁移的语义模式，对应我们想让 Norm/VenueProfile 跨 run 复用。 |

### 2.2 LLM 做边预测 / 链接预测 → C 类决策节点

| 论文 | 年份 | 与本项目的对应 |
|---|---:|---|
| **Knowledge Graph Large Language Model (KG-LLM) for Link Prediction** (Shu et al., arXiv:2403.07311, v9 2025) | 2024–25 | **最直接对应**。多跳链接预测：把子图结构序列化给 LLM，让 LLM 预测缺失链接。我们的 `formulate_gap()` 从 MethodLineage 查 frontier、`formalize_claim()` 从 EvaluationNorm 查 fidelity，本质就是「LLM 看着子图预测一条新边」（GapTriple→Norm, Claim→Norm）。 |
| **LLM as Prompter: Low-resource Inductive Reasoning on Arbitrary Knowledge Graphs** (arXiv:2402.11804) | 2024 | 低资源 KG 上的归纳推理。对应我们只有 6 篇时 Norm 不可信、52 篇时才稳定。 |
| **Filling the Gaps: LLMs for Causal Hypothesis Generation** (Sheth et al., ICLR 2025) | 2025 | 从因果图补缺失变量/边。对应 `GapTriple.why_not_before` 的推导。 |
| **Improving Scientific Hypothesis Generation with Knowledge Grounded LLMs / KG-CoI** (Xiong et al., 2024) | 2024 | **关键对应**：用 KG 锚定 LLM 假说生成，防「看似合理实则错误」。这正是我们做的事——Claim 的 fidelity 不许 LLM 自己判，必须从 EvaluationNorm 查。 |
| **HypoChainer: LLMs + KGs for Hypothesis-Driven Scientific Discovery** (Jiang et al., IEEE VIS 2025, arXiv:2507.17209) | 2025 | 人机协作的假说链，药物发现场景。对应我们的「决策链 + 溯源 + 案例」。 |
| **Toward Reliable Scientific Hypothesis Generation: Evaluating Truthfulness and Hallucination** (Xiong et al., IJCAI 2025) | 2025 | 假说的 truthfulness/hallucination 评估。对应我们的门控（BLOCKED）——防止无证据的 Claim。 |

### 2.3 动态图谱 / 状态转移 → 决策链与门

| 论文 | 年份 | 与本项目的对应 |
|---|---:|---|
| **Agentic-KGR: co-evolutionary knowledge graph construction through multi-agent RL** (arXiv:2510.09156, 2025) | 2025 | 图谱与 agent 决策共同演化。对应我们「每次 run 产生的 C 节点+边会回流影响后续查询」。 |
| **SAG-Agent: Long-Horizon Reasoning via Dynamic Knowledge Graphs** | 2025 | 动态图支撑长程推理。对应我们的 10 阶段决策链。 |
| **Decision Log / Agent Ledger 模式**（Agent Patterns Catalog / LedgerMind / Tenet AI） | 2024–25 | 不是单篇论文但是标准模式。对应我们 `ctx.decisions` 的 append-only ledger（intent+source+via+verdict）。 |

## 3. 这个类比带来的三个具体启发

### 3.1 B 类 = 图聚合 → 可以用图算法而非 LLM 重算

GraphRAG 用 Leiden 社区检测。我们的 Norm/VenueProfile 目前是 `Counter` + `set` 聚合，
下一步可以：
- 用 Leiden/Louvain 对 `Paper` 按 `evidence_type + metrics + venue` 聚社区
- 每个社区产一个 B 类节点（自动发现，而非我们预设 5 类）
- 社区摘要由 LLM 生成（GraphRAG 范式），但社区边界由确定性图算法定

**好处**：B 类节点数量不再靠人工拍脑袋，能随语料增长自动分裂/合并。

### 3.2 C 类 = 边预测 → 应该有负样本与置信度

KG-LLM 做 link prediction 会输出分数。我们的 `query_*()` 返回 `{found, source, via}`，
但**没有 confidence**。可以补：
- `confidence` = norm 的 n_papers / 总论文数（支持度）
- `negative evidence` = `FailureModeLibrary` 中与该边矛盾的条目
- `verdict` 从二值（BLOCKED/PASS）变成三值 + score

这样门控就不是硬编码 `len(checks)<10`，而是有统计依据。

### 3.3 门 = 边有效性 → 可引入 GNN 式的消息传递验证

当前 `Claim → Norm` 边是 `GROUNDED_IN`，但没有验证「这个 Norm 真的支撑这个 Claim」。
可以借鉴 GNN 消息传递：
- 从 Claim 的 evidence_type 出发，沿 `GROUNDED_IN` 到 Norm
- 检查 Norm 的 accepted_metrics 是否覆盖 Claim 的 expected_fidelity
- 不覆盖 → 边无效 → BLOCKED（比现在的规则更严谨）

## 4. 一句话结论

你的类比不仅成立，而且指向一条清晰的技术路线：

```
B 类 = 图聚合（GraphRAG 社区摘要 + 物化视图）
C 类 = LLM 边预测（KG-LLM + KG-CoI 的知识锚定）
门   = 边有效性验证（置信度 + 负证据 + 一致性检查）
```

我们的实现已经踩在这条路上了（`query_*()` 返回 provenance、`ctx.decisions` 是 ledger、
门控用 verdict），缺的是**图算法定社区**和**边置信度**这两块——正好是上述论文能补的。
