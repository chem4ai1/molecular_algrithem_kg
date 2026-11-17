# domain-signature · 从问题文本抽取轻量领域签名 hint

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/domain-signature/SKILL.md`（163 行）
> 类型：meta-skill · Phase 1a（OPTIONAL） · 契约：`domain-failure-modes.md`、`discipline-paradigm.md`、`discipline-writing.md`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 |
| **SciForge 26 节点** | `1a` |
| **输入节点（对齐）** | `Paper.research_question` → `ResearchQuestion`(global) |
| **输出节点（对齐）** | `DomainProfile`(paperapp, origin=rule) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用 `DomainProfile` + `origin=rule`；hint 不得成为下游直接来源，靠属性约束而非新类 |

## 1. 解决的问题

### 1.1 核心问题
从问题陈述中**规则化抽取**一个临时领域签名（hint），作为 Phase 1b learner 的冷启动先验；它不是最终签名。

### 1.2 具体场景 / 为什么需要
- 冷启动或文献稀疏时给 learner 一个起点：`Never hard-code domain-to-signature mapping. The signature is extracted from the problem text, not from a classification table.`
- 不做域适配会导致方法、证据、写作约定与领域错配。
- 签名始终是 provisional，下游可 refine。

### 1.3 不做的后果
- learner 从零开始且无文献时无从判断领域证据规范。
- 若把 hint 当最终签名直接消费，规则推断会冒充学习结果。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 / 谁产出 | 是否必须 |
|---|---|---|---|
| `Problem` | `statement` | 用户 Q-id / Phase 1 | 必须 |
| `UserPrompt` | 原始提示词 | 用户 | 可选 |
| `SeedLiterature` | `venues / methods / citation_style` | 用户或检索 | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Domain Signal Analysis | `Never hard-code domain-to-signature mapping...` | 从文本抽信号，不查分类表 |
| 契约 | `domain-failure-modes.md`、`discipline-paradigm.md`、`discipline-writing.md` | 失败模式 / 范式 / 写作参考 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| problem statement + seed literature + user prompt（未给固定路径） | 领域信号来源 |
| `shared-references/domain-failure-modes.md` 等三份契约 | 参考 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `Signature` | `signature_id`、`problem_id` |
| `DomainProfile` | `primary_domain`、`secondary_domains`、`evidence_type` |
| `MethodologyProfile` | `standard_methods`、`verification_approach` |
| `WritingProfile` | `style`、`citation_format` |
| `FailureModeProfile` | `common_failures`、`critical_assumptions` |
| `DataProfile` | `data_availability`、`min_sample_size` |
| `Confidence` | `domain_confidence`、`methodology_confidence`、`writing_confidence` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `refine-logs/domain-signature-hint.json` | `signature_id` 等 | **仅 `/domain-learner` 消费**作 prior |
| `refine-logs/domain-signature-report.md` | human-readable explanation | 人读报告 |
| `refine-logs/domain-signature.json` | Output Shape 仍列 | v2.8 起由 learner 独占写入，本 skill 不写 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| hint（provisional） | 仅 `/domain-learner` | `/idea-discovery` 等下游只读 learner 版签名，不读 hint |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 阶段门 | `kernel/config/phasegraph.json` | `id=1a / OPTIONAL / optional_on=host-agent`，next=`1b` | — | 失败 WARN 继续 |
| 置信门 | skill 内 | `confidence` | `<0.5` | 回落 default general signature |
| 临时性门 | skill 内 | signature always provisional | — | 下游可 refine |
| 消费门 | 契约 | `consumed ONLY by /domain-learner` | — | 下游 never read hint |
| 禁硬编码门 | skill 内 | 必须来自 problem text | — | 非 classification table |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 1 understand-decompose | Phase 1a `/domain-signature`（OPTIONAL） | Phase 1b `/domain-learner`（MUST）→ 其余 skills |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `DomainProfile / MethodologyProfile / WritingProfile` | `paperapp` `DomainProfile` 动态类 | 否（复用）；`hint` 需与 learner 版区分 `origin=rule\|learned` |
| `DomainProfile.confidence` 三态 | gate 判据 | 否 |
