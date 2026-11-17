# universal-retrieval · 多源检索 + 三层反幻觉 + broad/targeted 双波次

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/universal-retrieval/SKILL.md`（270 行）
> 类型：meta-skill · Phase 4broad / 4targeted（MUST, never skipped） · 代码佐证：`scripts/gap_gate.py`、`scripts/doi_gate.py`、`scripts/citation_support.py`、`scripts/s2_integrity_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 → 阶段1 |
| **SciForge 26 节点** | `4broad`/`4targeted` |
| **输入节点（对齐）** | `ResearchQuestion`；`Paper`；`EvidenceNorm` |
| **输出节点（对齐）** | `SourcePaper`(global)；`ResearchGap`(task-w)；`CitedPaper`(task-w) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 `GapReport`（gap-id/statement/evidence/priority 的检索侧产物）与 `VerificationLog`（三层验证状态）；`SourcePaper` 只记 relation/resolved，无法承载验证层级 |

## 1. 解决的问题

### 1.1 核心问题
多源检索真实论文，执行 arXiv → CrossRef → Semantic Scholar 三层反幻觉验证，并在 broad/targeted 两个波次中产出文献库、GAP 报告与碰撞日志。

### 1.2 具体场景 / 为什么需要
- `The 3-layer anti-hallucination protocol is mandatory` —— 最终引用不得来自记忆。
- 文献先于想法：先生成想法会把薄结果当发现。
- 网络问题只能 WARN，不得跳过 Phase 4（理论型也要查重）。

### 1.3 不做的后果
- 幻觉文献进 bib；gap 建立在检索盲区上；novelty 碰撞未被记录。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `SearchQuery` | `research topic / sub-topics` | 用户/问题 | 必须 |
| `SearchQuery` | `wave mode ∈ broad\|targeted` | orchestrator | 必须 |
| `Retrieval` | `sources / min_year / max_papers / verification_level` | 配置 | 必须 |
| `Proxy` | `proxy / detected_at` | 自动探测 | 可选 |
| `Claim` | `core claims` | `FINAL_PROPOSAL.md` | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无 prompt 模板 | 消费 `citation-discipline.md`、`discipline-context.md`、`output-manifest.md`、`orchestrator/auto-pipeline/SKILL.md` Phase4 v2.2 | 引用纪律/领域/output/编排 |
| 硬约束 | `The 3-layer anti-hallucination protocol is mandatory` | 不可跳过 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| Search query (+ wave mode) | 检索输入 |
| `refine-logs/FINAL_PROPOSAL.md` | core claim coverage |
| `literature/.proxy-resolved.json` | proxy |
| `literature/.pending/` | timeout results |
| surviving idea gap + keywords | targeted seed |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Paper` | `title / authors / abstract / categories / PDF URL` |
| `Paper` | `DOI / arXiv ID` |
| `Verification` | `status / layers passed` |
| `GapReport` | `gap-id / gap_type / statement / evidence / priority` |
| `Audit` | `recency_ratio / audit_verdict / recommendation` |
| `Wave` | `idea-id → gap-id → queries → papers added → collision pre-check` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `literature/references.bib` | cite keys | 累计引用 |
| `literature/landscape_report.md` | `recency_ratio / Gap identification` | 综述 |
| `literature/VERIFICATION_LOG.md` | `status / layers passed / source_status` | 验证日志 |
| `literature/verified_papers.json` / `unverified_papers.json` | metadata / reasons | 结构化 |
| `literature/GAP_REPORT.md` | `gap-id / type / statement / evidence / priority` | 想法锚 |
| `literature/TARGETED_WAVE_LOG.md` | `idea-id → gap-id → papers added → collision pre-check` | novelty 消费 |
| `.sciforge/audits/FILTER_CHAIN_AUDIT.json` | `audit_verdict / recommendation` | Phase5 门 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `GAP_REPORT.md` | `/idea-discovery` | gap 锚定前置 |
| `references.bib` + `TARGETED_WAVE_LOG.md` | `/novelty-check` | 碰撞预检 |
| `landscape_report.md` | `/paper-writing` Introduction | 前沿综述 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| Layer1 | arXiv | batches of 40 | `40` | — |
| Layer2 | CrossRef | DOI | — | — |
| Layer3 | S2 | fuzzy threshold + ≥2 metadata fields | fuzzy `≥0.6` | — |
| 总判定 | skill 内 | PASS≥2 layers；WARN=1 或部分 2；BLOCKED=0/fatal mismatch；ERROR=API failure | — | 未验证不入 bib |
| 近因门 | skill 内 | last 2 years | `≥40%` | 低 → re-retrieval `min_year=current year-2`；仍低 → `recency_gap` |
| 过滤链门 | `FILTER_CHAIN_AUDIT` | FAIL | — | Phase4 re-search ≤3 轮 |
| gap 门 | `scripts/gap_gate.py` | GAP-1/2/3、gap-id token、citation、discriminator | lite≥1 / balanced≥2 / max≥3 / beast≥4 | 回 Phase4broad |
| proxy 门 | skill 内 | 不可达 | — | WARN 而非 SKIP |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase4 broad → `/idea-discovery`；idea-pick 后 targeted → `/novelty-check` | `/universal-retrieval` | `/theory-derivation`、`/paper-writing` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `Paper / Verification / GapReport` | `semantic` 已有 `Paper`；`applayer` 的 `SourcePaper / Evidence` + `ResearchGap` | 建议新增 `GapReport / VerificationLog` |
| 三层验证状态 | `RELATED_TO.properties.verified` | 否（C 类落点） |
| near 2-year ≥40% | `DK-P1-14` 前沿时间轴 | 否 |
