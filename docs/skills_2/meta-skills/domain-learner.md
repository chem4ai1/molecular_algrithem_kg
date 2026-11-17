# domain-learner · 从文献与种子论文学习领域签名（唯一写入者）

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/domain-learner/SKILL.md`（183 行）
> 类型：meta-skill · Phase 1b（MUST） · 代码佐证：无直接判定脚本；验收依据 `shared-references/domain-adaptation-guide.md`，下游 `/result-to-claim`、`/experiment-execution`、`/publishability-score` 消费其证据规范。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 |
| **SciForge 26 节点** | `1b` |
| **输入节点（对齐）** | `Paper.research_question` → `ResearchQuestion`(global)；`Paper`(seed literature) |
| **输出节点（对齐）** | `DomainProfile`(paperapp, learned)；`EvidenceNorm`(global)；`FailureMode`(global) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | `DomainProfile` 需加 `origin=learned|rule`（区分 1a hint）与 `learning_confidence`；领域规范字段已被 EvidenceNorm 覆盖，不新增类 |

## 1. 解决的问题

### 1.1 核心问题
从问题描述、文献与 3–5 篇种子论文中**学习**领域特征，并作为 `domain-signature.json` 的唯一写入者产出可被全流水线复用的领域画像。

### 1.2 具体场景 / 为什么需要
- 新领域不应硬编码签名：原文要求 `Never hardcode domain characteristics. The learner starts from zero every time.`
- 文献稀疏或证据不足时，若仍套用学到的特征，会把错误的方法/证据/写作规范传播到所有下游阶段。
- `domain-signature-hint.json` 只能作 prior，最终真值必须由 learner 产出。

### 1.3 不做的后果
- 下游不知道「这个领域认什么证据」，导致分子生成用 accuracy 证明表示质量这类代理不匹配。
- 领域画像多写者并存，`hint` 冒充 learned profile，置信度虚高。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 / 谁产出 | 是否必须 |
|---|---|---|---|
| `Problem` | `description` | 用户 Q-id / Phase 1 | 必须 |
| `LiteratureSearch` | `Query / Results / Source` | 检索阶段 | 必须 |
| `SeedPaper` | `Methodology / Structure / Citations` | 用户提供或检索 | 可选 |
| `SignatureHint` | prior（`domain-signature-hint.json`） | Phase 1a `/domain-signature` | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Literature Search Results | 基于检索结果归纳领域证据规范 | 从真实文献而非记忆学习 |
| Seed Paper Analysis | 分析种子论文的方法/结构/引用 | 补文献不足时的先验 |
| Synthesize Domain Profile | `Never hardcode domain characteristics. The learner starts from zero every time.` | 禁止硬编码 |
| 契约 | `shared-references/domain-signature-consumer.md`、`shared-references/domain-adaptation-guide.md` | 消费规则与验收 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| 问题描述 + 种子文献（未给固定路径） | 搜索与 3–5 篇论文分析 |
| `refine-logs/domain-signature-hint.json` | 仅作 prior |
| `shared-references/domain-adaptation-guide.md` | 验收规范 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Learner` | `learner_version`、`learning_confidence` |
| `DomainProfile` | `primary_domain`、`evidence_type`、`reasoning_paradigm` |
| `MethodologyProfile` | `standard_methods`、`verification_approach` |
| `FailureModeProfile` | `common_failures` |
| `WritingProfile` | `style`、`citation_format` |
| `EvidenceNormProfile` | `sample_size_norm`、`control_design_norm`、`effect_reporting_norm`、`negative_result_norm` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `refine-logs/domain-signature.json` | learned profile | 下游统一消费的唯一真值 |
| `refine-logs/domain-learning-log.md` | searches / analyses / synthesis | 学习过程日志 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 证据规范（sample size / control / effect / negative result） | `/result-to-claim`、`/experiment-execution`、`/publishability-score` | 决定证据充分性与实验矩阵底线 |
| `unknown` → 保守默认 | 全体下游 | 低置信时回落 general evidence norm |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 置信门 | skill 内 | `learning_confidence` | `≥ 0.7` | 低于阈值 → 使用 defaults，不应用 learned characteristics |
| 论文数门 | skill 内 | `min_papers_for_learning` | `3` | `<3` 不可靠；源文未给明确去向 |
| 零结果门 | skill 内 | 检索结果为 0 | — | Learning Failure Report + WARNING → general academic + 2–3 seed papers |
| 失败回退门 | skill 内 | `fallback_to_default=true` | — | 学习失败 → 下游 defaults |
| 优先级门 | skill 内 | seed papers 与检索同时存在 | — | seed papers 优先于 literature search |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 1（problem）→ Phase 1a `/domain-signature`（hint） | Phase 1b `/domain-learner`（MUST） | Phase 4broad `/universal-retrieval`；全下游读 learner 版 `domain-signature.json` |

## 6. 与分子项目的映射

| 知识点 | `molecular_algrithem_design` 落点 | 是否需新增类 |
|---|---|---|
| `DomainProfile / EvidenceNormProfile` | `paperapp` 动态类 `DomainProfile` + `reprospec` 证据规范 | 建议新增 `EvidenceNormProfile` 节点承载五项规范 |
| `learning_confidence ≥ 0.7` | gate 判据（可落 `GateVerdict.state`） | 否 |
| 唯一写入者纪律 | `nodecache / registry / materialize` 白名单写入矩阵的先例 | 否 |
