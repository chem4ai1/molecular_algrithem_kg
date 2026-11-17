# idea-discovery · 基于 gap 锚定的想法生成与 4 轮 MCTS 收敛

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/idea-discovery/SKILL.md`（296 行）
> 类型：meta-skill · Phase 2（MUST） · 代码佐证：`scripts/gap_gate.py`、`scripts/dep_gate.py`、`scripts/detect_device.py`、`kernel/config/phasegraph.json`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 选空白+定主张 |
| **SciForge 26 节点** | `4broad`/`2`/`2.5`/`2.5b`/`3` |
| **输入节点（对齐）** | `ResearchGap`(global 候选)；`EvidenceNorm`；`FailureMode`；`SourcePaper` |
| **输出节点（对齐）** | `IdeaNode`(paperapp)；`ResearchGap`(task-w, selected_at)；`ExplorationFrontier`(paperapp) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 `IdeaDAG`（mutation/crossover 谱系，现有节点无 multi-parent 边）与 `FalsificationRecord`（证伪尝试需独立留痕）；二者落 paperapp |

## 1. 解决的问题

### 1.1 核心问题
基于冻结 Q-id、领域签名和 `GAP_REPORT.md`，生成 8–12 个研究想法，经六轴筛选 + 4 轮 MCTS 收敛到 1–3 个供人工选定。

### 1.2 具体场景 / 为什么需要
- 防止过早锁定第一个想法：多视角生成 + 树搜索。
- v6.0 要求每个晋升想法必须锚定 gap-id；无锚点会把薄结果包装成发现。
- OSS 无 demo/pilot fallback，Type-A 预筛 FAIL 直接淘汰。

### 1.3 不做的后果
- 想法与 gap 脱钩 → novelty 打分靠主观口味，最后「新意」不成立。
- 失败想法无记录 → 下一轮重复探索。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `ResearchQuestion` | `Q-id` | Phase 0 冻结 | 必须 |
| `ResearchQuestion` | `problem statement` | Phase 1 | 必须 |
| `GapReport` | `gap-id` | `/universal-retrieval` 4broad | 必须 |
| `Paper` | `cite_key` | `references.bib` | 必须 |
| `DomainSignature` | `perspective weights` | `/domain-learner` | 可选 |
| `DataContract` | `data_required / data_sources` | 数据准备 | 可选 |
| `FailedIdea` | `description / failure reason` | `failed_ideas.json` | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无独立 prompt 模板 | 消费 `mcts-search-protocol.md`、`engineering-grounding-contract.md`、`domain-signature-consumer.md`、`output-protocol.md` | 搜索/落地/消费/产物契约 |
| `[failed-ideas prompt injection]` | `inject the N historically most similar killed ideas + their failure reasons into the generation prompt` | 反重复 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| frozen Q-id + problem statement | 研究锚 |
| `refine-logs/domain-signature.json` | 视角权重 |
| `literature/references.bib` | novelty |
| `literature/GAP_REPORT.md` | gap 链（phasegraph 前置文件） |
| sibling `output/RUN_PREPRINT.md` | PREPRINT gap |
| `data/` | data-readiness |
| `refine-logs/failed_ideas.json` | 反重复 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Idea` | `id / Perspective / Framing` |
| `Idea` | `insight / novelty_delta / falsifiable_claim / mechanism / boundary` |
| `Idea` | `gap_anchor`（idea-id → gap-id） |
| `MCTS` | `score`（六轴） |
| `Proposal` | `Problem Anchor / Selected idea` |
| `GapAnchor` | `idea-id → gap-id` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `refine-logs/IDEA_CANDIDATES.md` | id / Perspective / 6-axis | 候选排名 |
| `refine-logs/IDEA_DAG.json` | nodes + edges | DAG |
| `refine-logs/IDEA_DAG_VISUAL.md` | Mermaid | 可视化 |
| `refine-logs/MCTS_LOG.md` | rounds / promotions / rejections | 审计 |
| `refine-logs/FINAL_PROPOSAL.md` | Problem Anchor / Selected idea | 冻结下游输入 |
| `refine-logs/GAP_ANCHOR_LOG.md` | idea-id → gap-id | 锚定审计 |
| `.sciforge/audits/BA_EVENT.json` | triggered_by / failed_evidence | 回退审计 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `FINAL_PROPOSAL.md`：Q-id / selected idea / assumptions / rejected alternatives / MCTS convergence evidence | `/method-registry`、`/theory-derivation`、`/invariant-check` | 冻结提案 |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 六轴门 | skill 内 | 任一轴 BLOCKED | — | MCTS 前拒绝 |
| EG 门 | `engineering-grounding-contract.md` | ≥3 sub-dimensions=0 | — | BLOCKED |
| 晋升门 | MCTS | score | `≥0.6` 晋升；`<0.4` 拒绝；`0.4–0.6` 生 2–3 child | border 重评 |
| gap 锚门 | `scripts/gap_gate.py` | 无 gap-id 且无 justified exploratory | 每轮 2 次 | relevance capped at 0.5 |
| 反重复门 | skill 内 | TF-IDF cosine similarity | `>0.78` | discard / duplicate_failed_idea |
| Type-A 门 | `dep_gate / detect_device / security_scan` | FAIL | — | 不进 Phase 2.5 / 3 |
| 零晋升门 | skill 内 | 0 promoted | — | broader perspectives |
| BA 门 | orchestrator | BA → Phase 2 | `≤2` 轮 | BLOCKED + BA_EXHAUSTED |
| 阶段门 | `kernel/config/phasegraph.json` | file `literature/GAP_REPORT.md` | — | gap 不可读 → pending-literature |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 1b `/domain-learner` + Phase 4broad `/universal-retrieval` | Phase 2 `/idea-discovery` | targeted `/universal-retrieval`、`/novelty-check`、`/method-registry`、`/theory-derivation` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `Idea / FinalProposal / GapAnchor` | `paperapp` 14 动态类已有 `IdeaNode`，`applayer` 有 `ResearchQuestion` | 建议新增 `IdeaDAG / GapAnchor` |
| `TF-IDF>0.78` 反重复 | `replay.py` 的 `avoid` 机制 | 否 |
| `MCTS 4 轮` | `paperapp/runner.py` 阶段适配器 | 否 |
