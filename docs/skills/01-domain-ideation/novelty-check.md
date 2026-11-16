# P3 · `novelty-check` — 前沿定位与碰撞审计的收敛门

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/novelty-check/SKILL.md`（v1.7.2，211 行）
> **功能批次**：① 领域与选题层
> **机械对应代码**：`scripts/gap_gate.py`、`scripts/doi_gate.py`、`scripts/citation_support.py`、`scripts/fantasy_gate.py`、`scripts/claim_anchor_gate.py`、`scripts/s2_integrity_gate.py`
> **性质判断**：**LLM 判断型 skill**（frontmatter 写的是 `type: reference-skill`，与其余 7 个 `meta-skill` 不同）；脚本不判新颖性，只保证它所依赖的证据链是真的。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `novelty-check` / `1.7.2` |
| `type` / `role` | **`reference-skill`** / `novelty-verifier` |
| 管线阶段 | **Phase 3**（DAG 的 prune gate；2.5/2.5b 之后、4targeted 之前） |
| 阶段模式 | **`[MUST]`**，且是 **forced human checkpoint**（Phase 3→4） |
| 输入 | `IDEA_DAG.json` + `GAP_ANCHOR_LOG.md` + `FRONTIER_MAP` 素材 + 检索结果 |
| 输出 | `novelty_report.json`、`novelty_{idea_id}.md`、`survivor.md`、`FRONTIER_GAP.md`、`FRONTIER_MAP.json`、`differentiation.md` |
| 非协商目标 | **至多 1 个 idea 存活**，DAG 收敛为单一路径 |

---

## 2. 解决什么问题

### 2.1 二元新颖性不够用

旧版只判「有没有人做过」（binary novelty 1–10），但 Q1 期刊 Introduction 前三段要求的是**前沿推进定位**：当前 SOTA 到哪、本文推进了多少、为什么以前做不到。若 novelty-check 不产出这个三元组，paper-writing 只能临场编，这正是「AI 写的 Intro 空洞、没有具体前沿锚点」的根因（v3.2 的立项理由）。

### 2.2 「有没有人做过」的盲区

实践观察到：ideation 没和已有工作逐篇比对，文献综述也漏检。v5.0 因此加入**强制碰撞审计**（per-paper collision check），而不是笼统说「查过了」。

### 2.3 gap 锚点可能失效

v6.0 把 `FRONTIER_MAP.json` 的未解节点与 `GAP_REPORT.md` 的 gap-id 交叉链接；idea 引用的 gap-id 若不存在 → `gap_anchor_invalid` 直接 FAIL，杜绝「引用一个自己编的空白」。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | `2 → 2.5(证伪) → 2.5b(EG) → **3** → [人工选定] → 4targeted(逐 idea 定向检索) → 5` |
| 前置 | 4broad 的 `GAP_REPORT.md`、4targeted 的 `TARGETED_WAVE_LOG.md` 碰撞预检 |
| 后继 | `/method-registry`（读 survivor）、`/paper-writing`（Intro 用 frontier 三元组 + differentiation） |
| 门 | 复合分 ≥0.6 且 DAG 收敛到 1 survivor；`score` 不足 → 放宽 strictness 1 级、重评 1 次 → 仍无 → `BLOCKED` |
| 人工检查点 | **Phase 3→4 强制**：agent 不能自己选最终 idea |
| 回退 | L3（无 survivor → 放宽严格度重评 1 轮 → BLOCKED） |

> **一个易忽略的分工**：`/idea-discovery` 的 6 轴预筛已经算过，本 skill **不重算**这 6 轴（R1 convergence note, L152），它只对已进 MCTS 的节点做 4 轴复合排序与存活裁决。若发现本该被 BLOCKED 的轴仍出现在 DAG，标记 `inconsistent_pre-screen` 并上报，而不是悄悄重打分。

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | **Introduction 前三段** | frontier baseline / delta claim / why-not-before | 直接生成 Q1 Intro 的贡献定位，且可溯源到 `FRONTIER_GAP.md` |
| **论文层** | Related Work 的差异化句 | `differentiation.md` 的 "Unlike X, we ..." | 让 Intro 的比较句可核验，不是空话 |
| **论文层** | 核心 claim 可证伪性 | delta claim 必须 falsifiable | 为 Phase 14 kill-argument 预设靶子 |
| **算法层** | 方法身份 | collision matrix 的 `same_method` 维 | 判断「只是换了超参」还是「机理层不同」 |
| **算法层** | 假设合理性 | feasibility 四查（工具/时间/skill/风险） | 决定 `feasible / risky / infeasible` |
| **代码层** | 实现可行性 | EG 分（取自 `IDEA_DAG.json` 的 `engineering_grounding.eg_average`，÷10 归一化） | 占复合分 15%；纯人文全 N/A 时 EG=1.0 不惩罚 |
| **数据层** | 数据集同一性 | collision matrix 的 `same_data` 维 | 「同问题+同方法」但数据不同 → 需说明数据差异带来的**科学问题差异**，否则仍 FAIL |
| **数据层** | 检索时效 | recency check（TOP-5 是否含近 2 年工作） | 无近作 → `recency_gap`：重检索或扣 relevance |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  IDEA_DAG.json（含 6 轴预筛结果、EG）、GAP_ANCHOR_LOG.md、
      landscape_report.md + references.bib + TARGETED_WAVE_LOG.md
  ↓
Step 1  载入所有 idea 节点（id/title/hypothesis/methodology/perspective）
Step 2  4 维评价：
        ├─ novelty = 0.5×binary_novelty + 0.5×frontier_advance
        ├─ frontier 三元组 → FRONTIER_GAP.md
        ├─ FRONTIER_MAP.json（近 2 年高引论文节点 + claims + open problems）
        ├─ gap_anchor 解析（无效 → FAIL；命中未解节点 → gap_consistent）
        └─ collision audit（TOP-5 → 3 维矩阵 → 冲突解决树 → differentiation.md）
        + feasibility / relevance / EG
Step 3  判定矩阵 → PASS / FAIL / REVISE / PENDING
Step 4  复合分排序，选唯一 survivor
Step 5  写 DAG 状态（status=converged, eliminated[], survivor{}, next_skill）
输出  novelty_report.json / survivor.md / FRONTIER_GAP.md / FRONTIER_MAP.json / differentiation.md
```

### 5.1 复合分

```
score = novelty × 0.45 + feasibility × 0.25 + relevance × 0.15 + engineering_grounding × 0.15
```
`< 0.6` 淘汰。EG 归一化：`eg_average / 10`；全部 N/A（纯人文）→ `EG = 1.0`。

### 5.2 前沿推进三元组（v3.2，MANDATORY，缺任一 → WARN 且不得进 3→4 检查点）

| 项 | 要求 |
|---|---|
| **Frontier baseline** | 显式列出当前 SOTA / 最强结果 / 最新开放问题；每条至少 1 个近 2 年引用。禁止写 "no research exists to our knowledge"，必须具体："[Smith2024] reached X, [Lee2025] improved to Y, but Z remains unsolved" |
| **Delta claim** | 一句话增量（"we propose mechanism W, advancing Z from unsolvable to conditionally solvable / improving by Δ% on benchmark K"），**必须可证伪**；delta 为 0 或负 → Phase 14 kill-argument 捕获 |
| **Why-not-before** | 3 条理由，覆盖「技术限制 / 理论盲点 / 数据可得性」至少 2 类；凑不齐 → `why_not_before_weak` 且 novelty 扣 2 分 |

`novelty_final = 0.5 × binary_novelty + 0.5 × frontier_advance`，`frontier_advance ∈ [1,10]`：三件套齐全=10；缺 baseline ≤4；delta 不可证伪 −3；落在已解节点 = 1。

### 5.3 `FRONTIER_MAP.json`

节点 = 近 2 年 1 篇高引论文 + 其 claims + open problems。每个「未解节点」与 `GAP_REPORT.md` 的 gap-id 交叉链接。idea 必须落在**未解节点**上；落在已解节点或空白无意义区域 → `not_novel` / `trivial_novel`。该图同时被 `/paper-writing` 的 Intro 直接消费。

### 5.4 碰撞审计（v5.0，强制）

| 步骤 | 内容 |
|---|---|
| 1. Recall TOP-5 | 按「同问题域 + 同方法族」检索 ≤5 篇最相似，必须含近 2 年工作；召回 0 → `retrieval_suspect` 触发重检索 |
| 2. 3 维矩阵 | 每篇打 0/1：`same_problem` / `same_method` / `same_data`，写入 `novelty_report.json.collision_matrix` |
| 3. 冲突树 | 见下表，取**最严命中** |
| 4. Recency | TOP-5 无近 2 年工作且 FRONTIER_MAP 该域有节点 → `recency_gap` |
| 5. 持久化 | `differentiation.md` + `collision_matrix` 供 Intro 引用 |

| 命中 | Verdict | 处理 |
|---|---|---|
| 3 维全 1 | `collision_fatal` | FAIL —— 这是复现不是研究 |
| problem+method=1，data 不同 | `collision_high` | 默认 FAIL；仅当能说明「数据差异带来的科学问题差异」才降为 REVISE |
| problem=1，method 不同 | `collision_medium` | REVISE，必须写清**机理层差异**（不是超参差异） |
| 仅 method 相似 | `collision_low` | PASS，但 Intro 必须引用并区分 |

### 5.5 判定矩阵（3 维 → 综合）

`novel+feasible+relevant → PASS`；`risky` 或 `partially_novel` → `REVISE`（最多 2 轮）；`not_novel` / `infeasible` / `irrelevant` 任一 → `FAIL`；信息不足 → `PENDING`（需人判）。

配置：`strictness ∈ {relaxed, normal, strict}`、`max_revise_cycles=2`、`min_survivors=1`、`require_literature=true`。

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `FrontierNode` | `paper_key`, `year`, `claims[]`, `open_problems[]`, `citation_count` | `HAS_STATE →` solved / **unsolved**；`CROSS_LINKS →` `Gap.gap_id` |
| `FrontierBaseline` | `sota_results[]`, `recent_citations[]`(近 2 年) | `PART_OF →` `FRONTIER_GAP.md`；`USED_BY →` `PaperIntroduction` |
| `DeltaClaim` | `statement`, `increment`, `falsifiable`, `benchmark` | `ADVANCES_FROM →` `FrontierBaseline`；`TARGET_OF →` `KillArgument` |
| `WhyNotBefore` | `reason`, `category ∈ {technical, theoretical, data}` | `SUPPORTS →` `DeltaClaim`（≥2 类、共 3 条） |
| `CollisionMatrix` | `same_problem`, `same_method`, `same_data`（各 0/1） | `VERDICTS →` `IdeaNode`（fatal/high/medium/low） |
| `Differentiation` | `mechanism_level_difference` | `CITED_BY →` `PaperIntroduction` |
| `GapAnchor` | `gap_id`, `valid`, `gap_consistent` | `RESOLVES_TO →` `Gap`；无效 → `FAIL` |
| `NoveltyScore` | `binary_novelty`, `frontier_advance`, `novelty_final` | `WEIGHTS →` `CompositeScore`（0.45） |
| `Survivor` | `id`, `novelty_score`, `feasibility_score`, `relevance_score`, `eg_tier` | `CONSUMED_BY →` `MethodRegistry` / `PaperWriting` |
| `EliminatedIdea` | `id`, `reason` | `AUDIT_TRAIL_OF →` `DAGState` |

**核心约束**：`Cardinality(Survivor) ≤ 1`；`DeltaClaim.falsifiable = true`；`WhyNotBefore` 覆盖 ≥2 类；`GapAnchor` 必须在 `GAP_REPORT.md` 中可解析。

---

## 7. 对应 `scripts/` 代码

**没有 novelty 打分脚本。 novelty 是 LLM 判断，scripts 保证其证据链真实。** 这是理解整个仓库分层的关键：`skill` 写「应该怎么判」，`script` 写「凭据是不是真的、格式合不合规、能不能放行」。

| 脚本 | 保障点 | 关键实现 |
|---|---|---|
| `scripts/gap_gate.py` | gap-id 真实且可判别 | `GAP_ID` / `CITATION` / `DISCRIMINATOR` 三个正则、`MIN_GAPS`、逐块引用检查、`exit 2` 硬门 |
| `scripts/doi_gate.py` | frontier baseline 的引用不是幻觉 | v1.7.1 strict-DOI：每个 `@entry` 必须有 `doi`（唯一例外 `no_doi_classical={yes}`）；CrossRef content negotiation 解析 DOI；**解析出的 BibTeX 标题与 bib 标题 token-overlap ≥0.8**（"a resolving DOI for the WRONG paper is the classic citation-hallucination surface"）；网络失败重试 1 次 |
| `scripts/citation_support.py` | 句子级引用支持（第 4 层） | 带数字/比较级的句子必须同句含 `\cite{}`（否则 `unsupported_quantitative_claim`）；每个 bib key 必须至少被引用一次（否则 `orphan_reference`）；`SCIFORGE_LLM_SUPPORT=1` 时才做模型抽查 `claim_not_entailed → WEAK_CITE` |
| `scripts/fantasy_gate.py` | 5 门防幻想，直接约束 delta claim | Gate3 假设合理性（`FINAL_PROPOSAL.json` 每个 assumption 需数值合理性分）；**Gate4 可证伪性：`FALSIFICATION_RECORD.json` 必须存在且 ≥1 次反例尝试**；5/4 门 → GROUNDED，3 → WEAKLY_GROUNDED（强制 Limitations），0–2 → FAIL 阻断 paper-writing |
| `scripts/claim_anchor_gate.py` | claim 与实验节点/证据字节的锚定 | `CLAIMS_FROM_RESULTS.md` 中每个进入正文的 claim 必须有 `CLAIM_ANCHORS.json` 中 `resolved=true` 的锚；锚的 node 必须存在于 `NODES.json`；**node outputs 哈希必须仍匹配**（"a result edited after anchoring invalidates the claim"） |
| `scripts/s2_integrity_gate.py` | D3 frontier-teacher co-occurrence | 确定性 D2（path/download）+ **D3（frontier-teacher co-occurrence）** 恒跑；语义 D1 仅在 provider 可用时跑（内核内 fail-closed）。这是「把前沿/教师信息泄漏进评测」的 Integrity 监控 |

> `fantasy_gate.py` 的 docstring 说得很直白：契约里称「最重要的质量门」，但此前**完全活在散文里**，没有东西阻止无根据的 claim 进入写作。脚本化的价值就在这里。

---

## 8. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `novelty_report.json` | `.sciforge/refine-logs/` | orchestrator / audit |
| `novelty_{idea_id}.md` | 同上 | 人 / 审计 |
| `survivor.md` | 同上 | method-registry / theory-derivation |
| `FRONTIER_GAP.md` / `FRONTIER_MAP.json` | 同上 | **paper-writing 的 Introduction** |
| `differentiation.md` + `collision_matrix` | 同上 | Intro 的 "Unlike X, we ..." |

DAG 状态示例字段：`dag_id / problem_id / status=converged / total_ideas / eliminated[{id,reason}] / survivor{...} / next_skill`。

---

## 9. 边界与反模式

- ❌ 重算 idea-discovery 已判过的 6 轴（应报 `inconsistent_pre-screen`）
- ❌ 写 "no research exists to our knowledge" 式的空泛 baseline
- ❌ delta claim 不可证伪；❌ why-not-before 只凑同一类理由
- ❌ 引用 GAP_REPORT 中不存在的 gap-id；❌ 落在已解前沿节点还判 novel
- ❌ TOP-5 无近 2 年工作却不做 `recency_gap` 处理
- ❌ agent 自行选定最终 idea（强制人工检查点）
- ✅ `collision_medium` 必须写**机理层**差异，不接受「换了超参」

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **FrontierNode / DeltaClaim / WhyNotBefore 三元组**可直接映射为 capfactory 的 `SourcePaper → HAS_LIMITATION / REPLACES / ON_METRIC` 链；`FRONTIER_MAP.json` 就是一张按年份切片的科技树视图。
2. **3 维碰撞矩阵**（problem / method / data）可作为 `ResearchQuestion × AlgorithmModule × Benchmark` 的三元去重键，天然适合图查询。
3. **claim anchor 的哈希复核**与上一轮 GGR 的 `ClaimAnchor（code_sha/inputs_sha/outputs_sha）` 完全同构，可扩展为六哈希并共享 `claim_anchor_gate` 式校验。
4. **把「可证伪性」变成机器门**：`falsifiable_claim` 不应只是文本字段，应像 `fantasy_gate` Gate4 一样要求存在 `FALSIFICATION_RECORD`。
