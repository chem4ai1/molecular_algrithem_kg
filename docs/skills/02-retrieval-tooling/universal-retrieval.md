# P4 · `universal-retrieval` — 分波文献检索与三层反幻觉验证

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/universal-retrieval/SKILL.md`（v1.7.2，269 行）
> **功能批次**：② 检索与工具层
> **机械对应代码**：`scripts/gap_gate.py`、`scripts/doi_gate.py`、`scripts/citation_support.py`、`scripts/s2_integrity_gate.py`、`scripts/sciforge_audit.py`、`scripts/validate_verdicts.py`
> **性质判断**：**反幻觉型 skill**（`type: reference-skill` / `role: academic-retriever`）。它是 8 个 meta-skill 中**唯一被 orchestrator 明确标注「MANDATORY, never skipped」**的，也是 v6.0 gap chain 的起点。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `universal-retrieval` / `1.7.2` |
| `type` / `role` | `reference-skill` / `academic-retriever` |
| 管线阶段 | **Phase 4broad**（ideation 打分前）+ **Phase 4targeted**（MCTS 选择后、Phase 3 碰撞审计前） |
| 阶段模式 | **`[MUST]`**；v2.2 起 **non-skippable**，theory-only 也必须跑（避免重复证明已知结论） |
| 输入 | 检索 query + wave mode（broad / targeted） |
| 输出 | `references.bib`、`landscape_report.md`、`verified_papers.json`、`VERIFICATION_LOG.md`、`unverified_papers.json`、`GAP_REPORT.md`、`TARGETED_WAVE_LOG.md`、`FILTER_CHAIN_AUDIT.json` |
| 定位 | "**The skill does not interpret paper content — it only retrieves, verifies, and formats metadata.**" |

---

## 2. 解决什么问题

### 2.1 四个主要病灶

| 病灶 | 机制 |
|---|---|
| **引用幻觉** | 3 层反幻觉验证（arXiv → CrossRef → S2），每条文献必须带真实存在性标签；绝不凭记忆写论文 |
| **先有 idea 后找文献** | v6.0 **wave protocol**：broad wave 先写 `GAP_REPORT.md`，idea 打分必须等它可读 |
| **文献陈旧 / 检索偷懒** | recency hard gate：近 2 年文献占比 ≥40%，不达标自动重检索 |
| **网络不通就跳过检索** | 代理自动挂载 + 后台重试；网络问题**只能**把 PASS 降为 WARN，绝不 SKIP / NOT_APPLICABLE / BLOCKED |

### 2.2 一句话的架构转向

> "**literature is the upstream of ideas, not their filter**" —— 文献不是用来事后筛掉坏 idea 的，而是产出 idea 的原料。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | `1b → **4broad** → 2 → 2.5 → 2.5b → 3 → **4targeted**（orchestrator 的表格把 4targeted 放在 Phase 3 之后） → 5` |
| 并行组 | Group A：4broad 与 Phase 2 Round 1 的头脑风暴可并行，但 **gap 锚定、novelty 预筛、Round 2–4 打分必须等 `GAP_REPORT.md`** |
| 门 | `gap_gate.py`（broad wave 产物硬门）；Phase 4 的 filter-chain integrity audit `FILTER_CHAIN_AUDIT.json` |
| 失败 | FAIL（无核心 claim 被覆盖 / 引用全部未验证）→ 回 Phase 4 重检索，最多 3 轮；WARN → 记 `NEEDS_HUMAN_LIT_supplement` 继续 |
| 后继 | `/idea-discovery`、`/novelty-check`、`/paper-writing`（Intro）、`/citation-audit`（Phase 15） |

> orchestrator Quality Gates 明确：Phase 4 的 3 层验证 + screening-chain（truth+completeness）完整性检查**理论型问题也不能跳**。

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | **Introduction** | `GAP_REPORT.md` 的 gap 表 + `landscape_report.md` 的 §Gap identification | 两者必须一致：前者是机器锚定清单，后者是叙述 |
| **论文层** | References / Bibliography | `references.bib`（全 wave 累积，不 fork 第二份） | 唯一引用源；`\cite{TODO}` / `forthcoming` 禁止 |
| **论文层** | Related Work | 子方向聚类 + 方法族 + 时间线 | 由 `landscape_report.md` 的四段组织直接供给 |
| **算法层** | 前沿节点 | 近 2 年高引论文 → `FRONTIER_MAP.json` | novelty-check 用它建 frontier node graph |
| **算法层** | gap 类型词表 | `contradiction / unsolved_node / method_blank / data_blank / generalization_blank` | 决定 idea 的 `gap_anchor` 类型 |
| **代码层** | 检索实现 | 6 个 API 客户端 + 代理挂载 + 后台 `nohup` 重试 | 全部外部调用必须走代理 |
| **代码层** | 验证实现 | arXiv 40-ID 批查、CrossRef DOI、S2 fuzzy ≥0.6 | 三层验证的具体接口契约 |
| **数据层** | 文献元数据 | `verified_papers.json` / `unverified_papers.json` | 结构化元数据 + 失败原因，供审计 |
| **数据层** | 检索状态 | `VERIFICATION_LOG.md`、`FILTER_CHAIN_AUDIT.json`、`.proxy-resolved.json` | 可复核的检索与网络状态 |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  query + wave mode
  ↓
Step 1  解析 query：topic / sub-topics / time range / type / constraints
Step 2  6 源按优先级检索（arxiv → S2 → CrossRef → PubMed → Web → OpenAlex），按 arXiv ID 或 DOI 去重
Step 3  3 层反幻觉验证（书 → CrossRef ISBN；技术报告 → web+机构库；会议论文 → S2 venue filter）
Step 4  合成 survey：子方向聚类 / 方法族 / 时间线 / gap 识别
        └─ broad wave 必须在此产出 GAP_REPORT.md（每条 gap ≥1 个已验证 cite key）
Step 5  生成引用产物：references.bib（累积）/ verified_papers.json / VERIFICATION_LOG.md
        └─ broad → GAP_REPORT.md；targeted → append TARGETED_WAVE_LOG.md
输出  8 类文献产物 + FILTER_CHAIN_AUDIT.json
```

### 5.1 v6.0 波次协议

| 波次 | 时机 | 产出 | 关键约束 |
|---|---|---|---|
| **Broad wave** | Phase 4 entry，idea 打分定案前 | `references.bib` + `landscape_report.md` + **`GAP_REPORT.md`** | gap 表字段 `gap-id / gap_type / statement / evidence(cite keys) / priority`；每条 gap 至少 1 个已验证 cite key；gap_type 属 5 类枚举 |
| **Hand-off** | → `/idea-discovery` | 每个被提升 idea 引用 gap-id | `GAP_REPORT.md` 不可读前禁止最终打分，标 `pending-literature` |
| **Targeted waves** | MCTS 选择之后、Phase 3 碰撞之前 | 每个存活 idea 一次检索，追加 `TARGETED_WAVE_LOG.md` | 由 anchored gap + idea 关键词做种子；新论文同样过 3 层验证；**若发现直接重复必须在日志里明说**，novelty-check 会读 |

### 5.2 三层反幻觉验证

| 层 | 接口 | 校验 | 状态 |
|---|---|---|---|
| L1 arXiv | `http://export.arxiv.org/api/query`，**每批 40 个 ID** | title / authors / abstract / categories 一致 | `verified / unverified / error` |
| L2 CrossRef | `https://api.crossref.org/works/{doi}` | DOI 可解析、标题匹配、≥1 作者匹配 | 同上 |
| L3 S2 | 按标题 fuzzy（阈值 **≥0.6**） | ≥2 个元数据字段（authors/year/venue/title）匹配 | 同上 |

**Final verdict**：≥2 层通过 = `PASS`；1 层或 2 层部分匹配 = `WARN`；0 层或致命不匹配 = `BLOCKED`；API 失败 = `ERROR`。

### 5.3 OSS 单一活动条（无学科分叉）

| 参数 | 统一值 |
|---|---|
| 源优先级 | arXiv → S2 → CrossRef → PubMed → Web → OpenAlex（**不按学科切换**） |
| `min_year` | 2020（绝对年份，非 6/12/18 月窗口） |
| `max_papers` | 30 |
| `verification_level` | `full`（无学科降级路径） |
| **recency hard gate** | 近 2 年文献 ≥ **40%**；不足 → WARN + 自动以 `min_year = 当前年-2` 重检索并去重；仍不足且该方向活跃 → `recency_gap`（novelty-check 消费） |

> SKILL.md 明确要求：若从主仓库迁移来的代码里出现 `DISCIPLINE_CONTEXT.source_priorities`，**删掉该分支** —— OSS 只有 `general` 一行。

### 5.4 代理自动挂载（v2.2，硬性）

1. 已有 `http_proxy` 或 1 小时内的 `literature/.proxy-resolved.json` → 直接用；
2. 端口候选逐个探：`8099 → 7890 → 7892 → 1080 → 8080`；
3. 每个候选做 **TCP `socket.connect_ex`（2s）+ HTTP GET `export.arxiv.org`（3s，期望 2xx/3xx）双检**；
4. 首个双检通过的写 `.proxy-resolved.json` 并挂载到所有后续请求；
5. 全不可达 → 先直连 1 次 → 再 `nohup` 后台重试，记 `source_status: proxy_unavailable`，Phase 4 **降为 WARN 但绝不 SKIP**；
6. 连续 2 次超时 → 删 `.proxy-resolved.json` 重新探测。

超时策略：单请求 30s、重试 1 次换 endpoint；整批超时 → `nohup` 后台写 `literature/.pending/`，前台继续其它源；结果在 Phase 10 或 15 回收。

### 5.5 Filter-Chain Integrity Audit（进 Phase 5 前必须过）

| 维度 | 检查 |
|---|---|
| **真实性** | 每条 bib 至少过 1 层验证；无 `\cite{TODO}` / `forthcoming` / 手写 BibTeX；`VERIFICATION_LOG.md` 逐条记录 |
| **完整性** | `FINAL_PROPOSAL.md` 每个核心 claim 至少 1 条引用或标 `[needs-citation]`；无 orphan citation / orphan ref；N 个子方向至少覆盖 N−1（允许 1 个作为本文贡献）；引用年份不能全集中一年 |
| **输出** | `FILTER_CHAIN_AUDIT.json`：`audit_verdict / authenticity{verified_count,...} / coverage{core_claims_covered, orphan_citations, subdirections_covered, time_span.recency_ratio,...} / unavailable_sources / recommendation` |

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `SearchQuery` | `topic`, `sub_topics[]`, `time_range`, `type`, `constraints[]` | `ROUTES_TO →` `DataSource`（6 源有序） |
| `DataSource`（6 值枚举） | `priority`, `coverage`, `provides[]` | `RETURNS →` `CandidatePaper` |
| `CandidatePaper` | `arxiv_id`, `doi`, `title`, `authors[]`, `year`, `venue`, `abstract` | `VERIFIED_BY →` `VerificationLayer`(1–3) |
| `VerificationLayer` | `layer_no`, `status`, `matched_fields[]`, `fuzzy_score` | `AGGREGATES_TO →` `CitationVerdict`（PASS/WARN/BLOCKED/ERROR） |
| **`Gap`** | `gap_id`, `gap_type`(5 枚举), `statement`, `evidence[cited keys]`, `priority` | `ANCHORS →` `IdeaNode`；`CONSISTENT_WITH →` `LandscapeReport.§Gap` |
| `TargetedWave` | `idea_id`, `gap_id`, `queries[]`, `papers_added[]`, `collision_precheck` | `FEEDS →` `CollisionMatrix` |
| `VerifiedPaper` | `cite_key`, `verification_layers[]`, `recency_ratio` | `CITED_BY →` `PaperSection` / `Gap` |
| `FilterChainAudit` | `authenticity`, `coverage`, `recommendation` | `GATES →` Phase 5 |
| `ProxyResolution` | `port`, `detected_at`, `probed[]`, `tcp_ok`, `http_forward_ok` | `ENABLES →` 所有外部 API 调用 |
| `RecencyRatio` | 近 2 年占比，阈值 0.4 | `TRIGGERS →` `ReRetrieval` / `recency_gap` |

**核心约束**：`Gap.evidence ⊆ VerifiedPapers`；`CitationVerdict ≠ BLOCKED` 才入 bib；`IdeaScoring ⇒ GAP_REPORT.readable`；`Phase4 never SKIP`。

---

## 7. 对应 `scripts/` 代码

**没有检索客户端脚本**（arXiv/S2/CrossRef 调用由模型/宿主运行时执行）。scripts 负责**验证 broad wave 的产物是否合格**，以及引用进入正文后是否仍然真实。

| 脚本 | 保障点 | 关键实现 |
|---|---|---|
| `scripts/gap_gate.py` | **broad wave 的硬门** | `GAP_ID` 正则识别 `GAP-\d+` / `#gap-*` / `[GAP: n]`；`CITATION` 正则识别 `[@key]`、`[Author, 2024]`、`Author et al. 2024`、`(2024)`；`DISCRIMINATOR` 判别动词词表；`MIN_GAPS` 按 effort（lite1/balanced2/max3/beast4）；**按 gap 块逐块检查引用**；`exit 2` 阻断 Phase 4broad → ideation |
| `scripts/doi_gate.py` | strict-DOI（比 3 层更严） | 3 层协议容忍「至少 1 层」，会让无 DOI 的 preprint 混进正文；此脚本要求每个 `@entry` 有 `doi` 且 CrossRef content negotiation 能返回非空 BibTeX；**解析出的标题与 bib 标题 token-overlap ≥0.8**（防「DOI 有效但指向别的论文」）；唯一例外 `no_doi_classical={yes}`（古典书籍，因为强配假 DOI 就是造假）；有 `--offline` |
| `scripts/citation_support.py` | **第 4 层**：句子级引用支持 | 前 3 层只证明文献存在且元数据吻合，不证明「引用句真的是该文献说的」。此脚本把正文切句，含**数字或比较级**（"X% higher"/"2.3x"/"outperforms by 0.8"）的句子必须同句有 `\cite{}`，否则 `unsupported_quantitative_claim`；每个 bib key 必须至少被引用一次，否则 `orphan_reference`；`SCIFORGE_LLM_SUPPORT=1` 时才做模型抽查 `claim_not_entailed → WEAK_CITE` |
| `scripts/s2_integrity_gate.py` | 检索/评测的完整性监控 | 确定性 **D3 frontier-teacher co-occurrence**（前沿/教师信息是否泄漏进评测）恒跑；D2 path/download 恒跑；语义 D1 仅在 provider 可用时跑（内核内 fail-closed） |
| `scripts/sciforge_audit.py` | 汇总所有 gate 的硬退出码 | orchestrator 的 "Mechanical verdicts via tool, not prose"：一次调用得到整体机器判定 |
| `scripts/validate_verdicts.py` | verdict schema 完整 | 每 Phase 边界 `--strict --require-complete` |

> **分层洞察**：`universal-retrieval` 管「找得到、是真的」，`doi_gate` 管「DOI 严格且没张冠李戴」，`citation_support` 管「正文里真的用了、且用对了」，`gap_gate` 管「挖出来的 gap 能驱动选题」。四者叠加才是完整引用链，任何一层都不能省。

---

## 8. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `references.bib` | `literature/` | 全管线（累积，不 fork） |
| `landscape_report.md` | `literature/` | paper-writing / novelty-check |
| **`GAP_REPORT.md`** | `literature/` | **idea-discovery（必须）/ novelty-check / paper-writing Intro** |
| `TARGETED_WAVE_LOG.md` | `literature/` | novelty-check 碰撞审计 |
| `verified_papers.json` / `unverified_papers.json` | `literature/` | citation-audit |
| `VERIFICATION_LOG.md` | `literature/` | 审计 / filter-chain |
| `FILTER_CHAIN_AUDIT.json` | `literature/` | Phase 5 边界门 |
| `.proxy-resolved.json` / `.pending/` | `literature/` | 网络状态 / 后台回收 |

---

## 9. 边界与反模式

- ❌ 因网络问题把 Phase 4 降为 SKIP / NOT_APPLICABLE / BLOCKED（只能 WARN）
- ❌ 凭记忆编造文献；❌ `\cite{TODO}` / `forthcoming` / 手写 BibTeX
- ❌ gap 无已验证 cite key；❌ 引用不存在的 gap-id
- ❌ 学科分叉的源优先级；❌ `verification_level=none`
- ❌ targeted wave 发现直接重复却不写进日志
- ❌ 静默丢弃候选论文（必须 verified 或显式标 unverifiable）
- ✅ 每条引用带存在性标签；✅ landscape 与 GAP_REPORT 一致；✅ 近 2 年占比达标

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **`Gap` 节点五分类**（contradiction / unsolved_node / method_blank / data_blank / generalization_blank）可直接作为 capfactory `ResearchQuestion` 的子类型，并配 `SUPPORTED_BY → SourcePaper`。
2. **三层验证 → 图边置信**：把 `VerificationLayer` 结果存成 `SourcePaper` 的属性（arxiv_verified / doi_verified / s2_verified），而非布尔 `resolved`；上一轮诊断的「lineage 0/3 逐字证据」正是缺这类分层证据。
3. **代理自动挂载与镜像下载**：本 skill 的「探测 → 挂载 → 后台重试 → 绝不跳过」策略可直接复用到 `FULL_TRAIN_REPRODUCTION_DESIGN.md` 的数据集镜像下载（HF_ENDPOINT 等价于这里的 proxy-resolved）。
4. **recency_ratio 作为图属性**：`FRONTIER_MAP` 的节点应带年份与被引数，才能做 novelty-check 的 recency check。
