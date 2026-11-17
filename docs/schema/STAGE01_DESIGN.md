# 阶段 01 · 问题锚定：输入 / 检索 / 输出

> 依据 `docs/论文生成任务链_12阶段/阶段01_问题锚定.md`。
> 核心判断：**语义层提供「论文里写了什么」，应用层提供「这次要解什么」**。

## 1. 输入

| 输入 | 层 | 落点 | 必须 |
|---|---|---|---|
| 用户问题文本 | 外部 | `ProblemAnchor.question`（任务级冻结） | 是 |
| 种子论文 | 语义层已有 `Paper` | `RelatedPaper`（任务级候选） | 否 |
| 投递物清单 | 外部文件 | `INTAKE_MANIFEST.json`（不进图） | 否 |
| 领域标签 | 语义层 `Paper.domain`（808/808） | **仅作 `RelatedPaper.domain_hint`** | 否 |

**重要：领域标签不参与证据规范推导。**
它只是检索线索——不知道领域也能搜（BM25 + 向量），有领域也只是弱加权（≤0.1）。

## 2. 检索

```
用户问题
   │
   ├─ 语义层向量索引：vector_sync.search(query, types=["Paper"], k=8)
   ├─ BM25 混合召回：kg/retrieval.HybridRetriever
   └─ 领域标签：弱加权 / 可选过滤（不硬过滤，避免跨领域召回被封死）
   │
   ▼
RelatedPaper（task-r）  ← 带 score / bm25 / vector / rank / domain_hint
```

**阶段01 不判定 `evidence_type`**，那是阶段02（domain-learner）的事。
本阶段只产 `DomainHint`（概率信号 + confidence），且 `confidence < 0.5` 回落 `general`。

## 3. 输出

### 3.1 两个任务级节点

| 节点 | 属性 | 说明 |
|---|---|---|
| `ProblemAnchor` | run_id / qid / question / content_hash / frozen_at / source_span / status / redirected_from | Q-id = `Q-<sha256前12>`；问题文本变一个字就记 `redirected_from` |
| `DomainHint` | run_id / 五维 profile / confidence / origin=rule / provisional=true | 规则抽取的**临时**签名，永不冒充 learned profile |

### 3.2 关系

```
RelatedPaper  <-GROUNDED_IN-  ProblemAnchor      （问题由哪些候选支撑）
DomainHint    -HINTS->        ProblemAnchor      （签名针对哪个问题）
SectionDraft  -ANCHORED_BY->  ProblemAnchor      （下游每节回引冻结问题）
```

### 3.3 产物文件

`FINAL_PROPOSAL.md`（含 Problem Anchor）/ `PROBLEM_HASH.txt`（SHA256）/
`domain-signature-hint.json` / `INTAKE_MANIFEST.json` / `REP.json`

## 4. 门与回退

| 门 | 判据 | 失败 |
|---|---|---|
| INV-G1 | 下游每个节点都有 `ANCHORED_BY` 且 qid 一致 | BLOCKED，重新锚定 |
| 内容哈希 | 当前 question 的 SHA256 == `content_hash` | `problem_content_rewritten` → KILL 回阶段换题 |
| 签名置信 | `confidence < 0.5` | 回落 `general`，不阻断 |
| intake | 无硬门（planning artifact） | OUT-OF-SCOPE 拒绝 |

## 5. 语义层 / 应用层分工

| | 语义层 | 应用层 |
|---|---|---|
| **读** | 808 篇 Paper 的 `domain` / `research_question` / 向量索引 | 检索结果（`RelatedPaper`） |
| **写** | 不写 hint（provisional 不该进事实层） | 写 `ProblemAnchor` / `DomainHint`（task 级） |
| **不混** | `ResearchQuestion` = 论文问了什么（global） | `ProblemAnchor` = 本次要解什么（task） |

两者同名不同义，**不要合并**。

## 6. 用法

```python
ctx = WritingContext(graph, "run_01")

# 1) 输入 + 冻结
anchor_id = ctx.freeze_problem(
    question="现有 3D 分子生成方法无法控制片段连接几何",
    seed_ids=["paper:2411.06608"], source_span="problem:1")

# 2) 检索（领域只作 hint）
ids = ctx.retrieve("3D-aware fragment generation", k=8,
                   domain_hint="分子生成与从头设计")

# 3) 输出 provisional 签名
hint_id = ctx.hint(anchor_id=anchor_id,
                   domain_profile=["分子生成", "计算化学"],
                   methodology_profile=["deep generative"],
                   failure_mode_profile=["metric_mismatch"],
                   confidence=0.72)
```

## 7. 与阶段02 的边界

```
阶段01  DomainHint    origin=rule, provisional=true   ← 本阶段
              │  REFINED_BY
              ▼
阶段02  EvidenceNorm  origin=learned, confidence      ← 唯一真值
```

hint 永远是 prior；阶段02 从文献学习后覆盖，且保留 `REFINED_BY` 追溯链。
