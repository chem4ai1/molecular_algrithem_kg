# 标准化方案：B 类图聚合 / C 类边预测 / 门有效性验证

> 基于下载的 6 篇论文 + 4 个开源仓库的源码提炼。
> 目标：把「B=聚合、C=边预测、门=验证」从类比变成可执行的工程规范。

## 0. 参考资料（已下载到 `docs/factory/references/`）

### 论文（papers/）

| 文件 | 论文 | 用在哪 |
|---|---|---|
| `2404.16130.pdf` | From Local to Global: GraphRAG (Edge et al., 2024) | B 类社区摘要 |
| `2403.07311.pdf` | KG-LLM for Link Prediction (Shu et al.) | C 类边预测 |
| `2402.11804.pdf` | LLM as Prompter: Low-resource Inductive Reasoning on KGs | 小样本归纳 |
| `2502.13025.pdf` | Agentic Deep Graph Reasoning (Buehler, MIT 2025) | 自组织图构建 |
| `2507.17209.pdf` | HypoChainer (IEEE VIS 2025) | 知识锚定假说链 |
| `2505.14599.pdf` | TruthHypo / Hypothesis Hallucination (IJCAI 2025) | 门验证 |

### 代码（code/）

| 仓库 | 提炼的机制 |
|---|---|
| `microsoft_graphrag` | 社区报告结构（title/summary/findings/rating/rating_explanation）+ 动态社区选择 |
| `rutgerswiselab_KG-LLM` | DFS 2–N 跳路径采样、正负样本平衡、`Is node A connected with node B?` prompt |
| `gzxiong_TruthHypo` | `KGVerifier.verify_claim()`：claim→抽实体→检索节点→取边→LLM 验证 |
| `HKUDS_LightRAG` | high-level/low-level 双关键词检索 |

## 1. 三层标准定义

### B 层 · 图聚合（离线，物化视图）

**电源自 GraphRAG 社区报告结构**：

```python
# 标准 B 节点属性（对齐 GraphRAG FindingModel + CommunityReportResponse）
{
  "title": str,                    # 社区标题（如 "simulational 证据规范"）
  "summary": str,                  # 一句话摘要
  "findings": [                    # 结构化发现列表（不是自由文本）
      {"summary": str, "explanation": str}
  ],
  "rating": float,                 # GraphRAG 有 rating！→ 置信度
  "rating_explanation": str,       # 置信度理由
  "source_papers": [paper_id],     # 回指来源（community membership）
  "community_level": int,          # 社区层级（Leiden 层级）
  "n_papers": int,                 # 支持度
}
```

**构建流程标准化（5 步）**：

```
1. 构图    A 类属性 → 特征向量/边（Paper --evidence_type--> Norm）
2. 社区发现 Leiden/Louvain 按 {evidence_type, metrics, venue} 聚社区
           ← GraphRAG 用 Leiden；替代我们现在的 Counter 硬聚合
3. 报告抽取 LLM 对每个社区产出 title/summary/findings/rating
           ← GraphRAG `CommunityReportsExtractor`
4. 物化    写 B 类节点 + DERIVED_FROM_PAPERS 边（community membership）
5. 更新     增量语料 → 只重算受影响社区（GraphRAG `update_community_reports`）
```

**关键改进（vs 当前）**：
- 当前：预设 5 类 B 节点 + Counter 聚合 → 类别数靠人拍脑袋
- 标准：**社区算法自动发现类别数** + LLM 写报告 + 自带 rating

### C 层 · LLM 边预测（在线，条件生成）

**源自 KG-LLM 的多跳路径 + TruthHypo 的知识锚定**：

```python
# 标准 C 节点 = 一条被 LLM「预测」出的边 + 端点
{
  "run_id": str,
  "edge_spec": {                   # 预测的目标边（KG-LLM 范式）
      "source": node_id,
      "relation": "GROUNDED_IN | FULFILLS | IDEA_FOR",
      "target": B_node_id,
      "confidence": float,         # ← GraphRAG rating 迁移过来
      "negative_evidence": [...],  # ← KG-LLM 负样本迁移
  },
  "path": [node_id, ...],          # KG-LLM DFS 2-N 跳路径（可解释）
  "prompt_ref": str,               # 实际 prompt hash（回放用）
  "verdict": "CREATED|LOCKED|BLOCKED",
  "source": node_id, "via": relation,
}
```

**构建流程标准化（KG-LLM 4 步）**：

```
1. DFS 路径采样   从 C 节点出发，在 A/B 图上做 2–N 跳 DFS，收集子图
                  ← KG-LLM `dfs(graph, size)`；size 随机 2..N 增加多样性
2. 子图序列化     把路径转成自然语言（"A --PROTOCOL--> B --METRIC--> C"）
                  ← KG-LLM 的 `input_text`
3. 条件生成       prompt = 子图 + 任务 + 候选 B 节点规范
                  ← 我们的 query_*() 结果注入（不是让 LLM 自由选）
4. 正负样本       正例=有边，负例=同类型但无边；用于校验/训练
                  ← KG-LLM writer_pos/writer_neg 平衡
```

**关键改进（vs 当前）**：
- 当前：`query_evaluation_norm(g, et)` 直接返回单一 B 节点 → 没有路径、没有置信度、没有负例
- 标准：返回 `top-k 候选 B 节点 + 各自 rating + 支持路径 + 负证据`，LLM 在约束下选

### 门 · 边有效性验证（TruthHypo 范式）

**源自 `KGVerifier.verify_claim()` 的 5 步验证**：

```
1. 抽实体      从 C 节点 statement 抽关键实体（LLM）
               ← TruthHypo: "Extract key entities from the claim..."
2. 检索节点     用实体在 A/B 图上检索相关节点（BM25/向量）
               ← TruthHypo: kg_retriever.retrieve_nodes(text, k=node_k)
3. 取边+限额    取这些节点之间的边，超过 max_n_edges 则随机采样
               ← TruthHypo: `if len(edges) > max_n_edges: random.sample(...)`
4. 一致性检查   边文本化后交 LLM 验证 claim 是否被支持
               ← TruthHypo: edge2text(e) + verify_claim
5. 三值判定     SUPPORTED / REFUTED / INSUFFICIENT + confidence
               ← 替代我们当前的二值 BLOCKED/PASS
```

**门的三层检查（标准化）**：

| 检查 | 方法 | 失败判定 |
|---|---|---|
| **置信度** | B 节点 `rating` × 支持度 `n_papers/N` | < threshold → INSUFFICIENT |
| **负证据** | FailureModeLibrary 中与该边矛盾的 findings | 命中 → REFUTED |
| **一致性** | KGVerifier 式：claim 实体能否在图中找到支持边 | 找不到 → INSUFFICIENT |

**verdict 从二值升级为三值 + score**：

```python
{"verdict": "SUPPORTED|REFUTED|INSUFFICIENT",
 "confidence": 0.82,
 "supporting_edges": [...],
 "contradicting_edges": [...],
 "path": [node_ids],
 "verifier": "kg_verifier_v1"}
```

## 2. 标准化 API（对接 WritingContext）

```python
class WritingContext:
    # B 层已由离线 pipeline 建好；C 层只读 B
    def formulate_gap(...)  -> GapTriple   # KG-LLM 路径采样 + top-k 候选
    def propose_idea(...)   -> IdeaCandidate
    def formalize_claim(...) -> Claim       # 从 B.rating 取 confidence
    def grade_claim(...)    -> Verdict      # 三层门，三值判定
    def design_narrative(...)-> SectionPlan + FigurePlan
    def deliver(...)        -> ReproductionPackage

    # 新增：标准化边预测查询
    def predict_edge(self, source, relation, *, top_k=5,
                     max_hops=4, candidate_type=None) -> List[EdgeCandidate]:
        """KG-LLM 范式：DFS 采样 → 子图序列化 → top-k 候选 + rating"""
```

`EdgeCandidate` 数据类：

```python
@dataclass
class EdgeCandidate:
    target: str
    relation: str
    confidence: float          # B.rating × support
    path: List[str]            # DFS 路径
    supporting: List[str]      # 正证据 edge ids
    contradicting: List[str]   # 负证据 edge ids
    source_report: str         # 来自哪个 B 社区报告
```

## 3. 与当前实现的差异清单

| 维度 | 当前 | 标准（本方案） | 优先级 |
|---|---|---|---|
| B 节点类别数 | 人工预设 5 类 | Leiden 自动发现 | P1 |
| B 节点属性 | 手工字段 | title/summary/findings/rating/rating_explanation | **P0** |
| B 置信度 | 无 | `rating` + `rating_explanation`（GraphRAG） | **P0** |
| C 查询 | 返回单个 B 节点 | top-k 候选 + path + confidence | P1 |
| C 负样本 | 无 | 同类型无边负例（KG-LLM） | P2 |
| 门判定 | 二值 BLOCKED/PASS | 三值 + score（TruthHypo） | **P0** |
| 门流程 | 硬规则 `len<10` | 抽实体→检索→取边→LLM 验证 | P1 |
| 回放 | decisions log | + prompt_ref + path | P1 |

**P0 是本轮要落地的**——改动小、收益直接：给 B 节点加 rating，把门变三值。

## 4. 一句话

```
GraphRAG 给了 B 层的「社区报告 + rating」结构；
KG-LLM 给了 C 层的「多跳路径 → 条件边预测」流程；
TruthHypo 给了门的「抽实体 → 检索边 → 验证claim」三值判定。
三层拼起来就是：离线聚合出带置信度的规范，在线用路径预测边，用 KG 验证器定档。
```
