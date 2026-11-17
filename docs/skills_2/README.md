# `skills_2` · SciForge-OSS 全部 83 份 skills 的「问题 → 输入 → 输出」结构化整理

> **阶段标注已补齐（83/83）**：每份文件头部新增「阶段与节点对齐（paper_phase 六阶段）」表，含阶段标注、SciForge 26 节点、输入/输出节点对齐、对齐状态、节点增补建议。
> 汇总入口：[阶段与节点对齐汇总.md](阶段与节点对齐汇总.md)（阶段→文件索引 + 新增节点三层收敛判断）。

## 0. 本目录回答什么

逐个读取 `/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/` 下的**全部 83 份 md 文件**，
按统一的「**解决的问题 → 输入（知识节点 + prompt 模板）→ 输出（知识节点）**」三段式整理，
并结合 `scripts/` 与 `kernel/sciforge/` 中的真实判定器核对门、阈值与产物文件名。

与既有 `docs/skills/`（24 份，按功能/阶段分批）的区别：

| 维度 | `docs/skills/` | 本目录 `docs/skills_2/` |
|---|---|---|
| 组织单位 | 功能簇 / 阶段簇（一份文档覆盖多份 SKILL.md） | **一份源文件 = 一份整理文档**（83 对 83） |
| 叙事主轴 | 解决什么问题、属于哪个阶段、做了什么、怎么做 | **问题 → 输入知识节点 + prompt 模板 → 输出知识节点** |
| 代码佐证 | 概述性引用 | 逐条列出脚本名、退出码、阈值、产物 schema |

## 1. 每份文档统一的 6 节结构

```
# <skill 名> · <一句话定位>
> 源文件路径 + 行数 + 类型 + 代码佐证

## 1. 解决的问题
   1.1 核心问题（一句话） / 1.2 具体场景 / 1.3 不做的后果

## 2. 输入
   2.1 输入知识节点（表格：节点类 | 关键属性 | 来源 | 是否必须）
   2.2 输入 prompt 模板 / 契约文本（表格：模板段 | 关键原文指令句 | 作用）
   2.3 输入产物文件（表格：路径 | 用途）

## 3. 输出
   3.1 输出知识节点（表格：节点类 | 关键属性）
   3.2 输出产物文件（表格：路径 | 关键字段 | 用途）
   3.3 向下一阶段传递的 prompt / 约束片段

## 4. 判定与门（表格：门 | 脚本/机制 | 判据 | 阈值 | 失败去向）
## 5. 上下游接口
## 6. 与分子项目的映射（molecular_algrithem_design 落点 + 是否需新增类）
```

**关于 `2.2 输入 prompt 模板`：**
- SKILL 类文件：写出其 prompt 模板段名与关键原文指令句（如 `/domain-learner` 的 `Never hardcode domain characteristics...`）。
- `shared-references` 类文件：它们本身不是可执行 skill，没有 SKILL 式 prompt 模板；
  此时 `2.2` 写它被注入 prompt 的**关键契约句**，或明确标注「无 prompt 模板，作为法条被下游引用」并列出引用方。

## 2. 文件索引（83 份）

### 2.1 meta-skills（8 份）

| 文件 | 解决的问题（一句话） |
|---|---|
| [`meta-skills/domain-learner.md`](meta-skills/domain-learner.md) | 从文献与种子论文学习领域签名，作为 domain-signature.json 唯一写入者 |
| [`meta-skills/domain-signature.md`](meta-skills/domain-signature.md) | 从问题文本规则化抽取临时领域签名 hint，供 learner 冷启动 |
| [`meta-skills/dynamic-sandbox.md`](meta-skills/dynamic-sandbox.md) | 隔离执行代码并返回带 code_hash/session 的结构化结果 |
| [`meta-skills/dynamic-tooling.md`](meta-skills/dynamic-tooling.md) | 运行时生成、烟测、注册缺失工具，带 ToolContract 与 hash |
| [`meta-skills/idea-discovery.md`](meta-skills/idea-discovery.md) | gap 锚定的 8–12 个想法生成 + 六轴筛选 + 4 轮 MCTS |
| [`meta-skills/novelty-check.md`](meta-skills/novelty-check.md) | 四维复合分 + 碰撞审计，收敛到唯一 survivor |
| [`meta-skills/unified-plotting.md`](meta-skills/unified-plotting.md) | PDF+SVG 双矢量图、A1–A11 机械审计与 figure index |
| [`meta-skills/universal-retrieval.md`](meta-skills/universal-retrieval.md) | 多源检索 + 三层反幻觉 + broad/targeted 双波次 + gap 报告 |

### 2.2 orchestrator（1 份）

| 文件 | 解决的问题（一句话） |
|---|---|
| [`orchestrator/auto-pipeline.md`](orchestrator/auto-pipeline.md) | 单 Q-id 的 26 节点 DAG 编排，只读 verdict、卡硬门、触发有界回退 |

### 2.3 support skills（19 份）

| 文件 | 解决的问题（一句话） |
|---|---|
| [`support/ablation-planner.md`](support/ablation-planner.md) | 5–6 个组件消融计划与 AblCritic 单调账本 |
| [`support/adversarial-falsification.md`](support/adversarial-falsification.md) | Phase 2.5 先杀后证的假设健康度判定 |
| [`support/auto-review-loop.md`](support/auto-review-loop.md) | Phase 14 固定 5 阶段、最多 4 轮跨模型复审 |
| [`support/citation-audit.md`](support/citation-audit.md) | 存在/元数据/上下文三层引用核验 |
| [`support/experiment-execution.md`](support/experiment-execution.md) | toy→full 两段实验、安全/完整/烟测门与后台派发 |
| [`support/experiment-ladder.md`](support/experiment-ladder.md) | subset→full 阶梯与 GOOD/ENGINEER/BAD 三态 Critic |
| [`support/intake-triage.md`](support/intake-triage.md) | 任意投递物普查、信任分类与阶段路由建议（只规划不削门） |
| [`support/invariant-check.md`](support/invariant-check.md) | 阶段边界结构门与 INV-G1 问题内容哈希冻结校验 |
| [`support/kill-argument.md`](support/kill-argument.md) | 约 200 词最强拒稿论证与逐点裁决 |
| [`support/leakage-audit.md`](support/leakage-audit.md) | Type I 逻辑缺口与 Type IV 经验逃逸预注册审计 |
| [`support/logic-verification.md`](support/logic-verification.md) | 6 维一致性 + 20 类问题分类 + 3 轮修复上限 |
| [`support/method-registry.md`](support/method-registry.md) | 8 节方法注册表、Section 3 hash lock 与人工审批 |
| [`support/paper-compile.md`](support/paper-compile.md) | elsarticle 编译与零警告/页数/图嵌入硬检查 |
| [`support/paper-writing.md`](support/paper-writing.md) | 五模式章节集与 elsarticle 全稿组装 |
| [`support/publishability-score.md`](support/publishability-score.md) | 六维投稿评分与主逻辑一票否决 |
| [`support/quality-gate.md`](support/quality-gate.md) | 写作前停滞检测 + QF-G1~G9 + SD-G1~G5 硬门 |
| [`support/rebuttal.md`](support/rebuttal.md) | 逐点反驳信，禁承诺未做实验 |
| [`support/result-to-claim.md`](support/result-to-claim.md) | 三档保真度 + TDAL 联合置信 + ClaimAnchor |
| [`support/theory-derivation.md`](support/theory-derivation.md) | 冻结 Q-id + 假设 + 逐步 SymPy 验证的推导包 |

### 2.4 shared-references（55 份，法条层）

| 文件 | 解决的问题（一句话） |
|---|---|
| [`shared-references/artifact-registry.md`](shared-references/artifact-registry.md) | 跨技能产物唯一真相源（路径/生产者/消费者/schema/验证器） |
| [`shared-references/assurance-contract.md`](shared-references/assurance-contract.md) | 审计严格度轴与 6 态 verdict 语义 |
| [`shared-references/background-dispatch-protocol.md`](shared-references/background-dispatch-protocol.md) | 长任务后台派发与 STATUS.json 回执 |
| [`shared-references/citation-discipline.md`](shared-references/citation-discipline.md) | 三层反幻觉引用纪律 |
| [`shared-references/color-themes.md`](shared-references/color-themes.md) | 色盲安全配色与字号/线宽地板 |
| [`shared-references/competitive-analysis.md`](shared-references/competitive-analysis.md) | 竞品差异化静态快照与优化路线 |
| [`shared-references/competitive-drift-monitor.md`](shared-references/competitive-drift-monitor.md) | 差异化衰减的季度监控与 PR 触发 |
| [`shared-references/confidence-uplift.md`](shared-references/confidence-uplift.md) | TDAL 弱维的有界提升机制（3 种机制/3 轮） |
| [`shared-references/discipline-context.md`](shared-references/discipline-context.md) | 单一 general 管线，无学科分支 |
| [`shared-references/discipline-paradigm.md`](shared-references/discipline-paradigm.md) | formal/empirical/interpretive/design 四范式 |
| [`shared-references/discipline-writing.md`](shared-references/discipline-writing.md) | 跨领域逐节写法（Signature-Driven Writing） |
| [`shared-references/domain-adaptation-contract.md`](shared-references/domain-adaptation-contract.md) | TDAL 单一权威 schema（joint = T×D×A×L） |
| [`shared-references/domain-adaptation-guide.md`](shared-references/domain-adaptation-guide.md) | 领域签名接线 7 步 + 18 项验收 |
| [`shared-references/domain-adaptive-pipeline.md`](shared-references/domain-adaptive-pipeline.md) | 26 节点结构不变，强度按签名自适应 |
| [`shared-references/domain-contribution-protocol.md`](shared-references/domain-contribution-protocol.md) | unknown evidence_type 经 PR 成为 first-class |
| [`shared-references/domain-failure-modes.md`](shared-references/domain-failure-modes.md) | 领域失败模式目录，供证伪/盲区审计查询 |
| [`shared-references/domain-signature-consumer.md`](shared-references/domain-signature-consumer.md) | 下游统一消费领域签名，hint 仅供 learner |
| [`shared-references/effort-contract.md`](shared-references/effort-contract.md) | 工作量深度轴，与审计严格度正交 |
| [`shared-references/engineering-grounding-contract.md`](shared-references/engineering-grounding-contract.md) | 想法可实现性 8 维量化与三档 tier |
| [`shared-references/experience-replay-contract.md`](shared-references/experience-replay-contract.md) | 跨 run 经验回放，avoid 为硬排除 |
| [`shared-references/fantasy-prevention.md`](shared-references/fantasy-prevention.md) | 理论主张 5 门反幻想 |
| [`shared-references/figure-complexity-contract.md`](shared-references/figure-complexity-contract.md) | 图形复杂度与视觉层级下限 |
| [`shared-references/figure-layout-contract.md`](shared-references/figure-layout-contract.md) | 图形排版即论证结构，A11 对齐审计 |
| [`shared-references/figure-quality-contract.md`](shared-references/figure-quality-contract.md) | 图形质量地板与 PDF+SVG 双输出 |
| [`shared-references/figure-quality-review.md`](shared-references/figure-quality-review.md) | 视觉质量自审，机械审计的补充 |
| [`shared-references/grounding-check.md`](shared-references/grounding-check.md) | 理论结果落地概率 A–E 清单 |
| [`shared-references/idea-dag-schema.md`](shared-references/idea-dag-schema.md) | 想法 DAG 单一真源 schema（mutation/crossover） |
| [`shared-references/integration-contract.md`](shared-references/integration-contract.md) | 跨技能调用必须有 5 个机器证据组件 |
| [`shared-references/mcts-search-protocol.md`](shared-references/mcts-search-protocol.md) | 想法 DAG 上的 UCB 搜索与 βEG |
| [`shared-references/methodology-and-context-contract.md`](shared-references/methodology-and-context-contract.md) | 分析停止规则与上下文经济 |
| [`shared-references/multi-fidelity-evaluation.md`](shared-references/multi-fidelity-evaluation.md) | 想法 low/mid/high 三档保真度评估 |
| [`shared-references/ouroboros-integration.md`](shared-references/ouroboros-integration.md) | 自指改进循环，默认关闭、显式 opt-in |
| [`shared-references/output-language.md`](shared-references/output-language.md) | 输出语言 7 维控制 |
| [`shared-references/output-manifest.md`](shared-references/output-manifest.md) | 产物清单即运行态 SSoT，跨 agent parity |
| [`shared-references/output-protocol.md`](shared-references/output-protocol.md) | 双层产物目录与执行即留痕 |
| [`shared-references/output-versioning.md`](shared-references/output-versioning.md) | 结构决策变更强制版本更新 |
| [`shared-references/paper-modes.md`](shared-references/paper-modes.md) | 按验证类型选论文章节集 |
| [`shared-references/paper-voice-contract.md`](shared-references/paper-voice-contract.md) | 论文书面语气与禁区 |
| [`shared-references/pipeline-adaptive-degradation.md`](shared-references/pipeline-adaptive-degradation.md) | 可验证的降级路径，禁静默 skip |
| [`shared-references/pipeline-integrity.md`](shared-references/pipeline-integrity.md) | 反「看似完成」的运行完整性三硬门 |
| [`shared-references/plugin-router.md`](shared-references/plugin-router.md) | 外部可复用插件注册表 |
| [`shared-references/project-architecture-contract.md`](shared-references/project-architecture-contract.md) | 零隐藏状态、零自动造文件的产物模型 |
| [`shared-references/reviewer-independence.md`](shared-references/reviewer-independence.md) | 跨模型、盲审、强制反例的评审独立性 |
| [`shared-references/reviewer-prompts/economics.md`](shared-references/reviewer-prompts/economics.md) | 经济学 persona（历史存档，不活跃） |
| [`shared-references/reviewer-prompts/README.md`](shared-references/reviewer-prompts/README.md) | persona 目录归档说明 |
| [`shared-references/reviewer-routing.md`](shared-references/reviewer-routing.md) | 评审输入/输出路由与结果落地 |
| [`shared-references/review-tracing.md`](shared-references/review-tracing.md) | 双 reviewer 独立留痕，防自评冒充 |
| [`shared-references/s2-protocol.md`](shared-references/s2-protocol.md) | S2 保真度阶梯/完整性/消融三 gate |
| [`shared-references/schemas/README.md`](shared-references/schemas/README.md) | 23 个 JSON Schema 索引，schema 是字段权威 |
| [`shared-references/skill-config.md`](shared-references/skill-config.md) | 单一配置源与 no-op 迁移契约 |
| [`shared-references/startup-protocol.md`](shared-references/startup-protocol.md) | 每个 skill 启动必读与加载顺序 |
| [`shared-references/venue-checklists.md`](shared-references/venue-checklists.md) | 按 venue 族的投稿前核对清单 |
| [`shared-references/venue-profiles.md`](shared-references/venue-profiles.md) | venue 档位画像（只调格式不建分支） |
| [`shared-references/verification-routing.md`](shared-references/verification-routing.md) | 验证模式路由与 na_verdicts 规则 |
| [`shared-references/writing-principles.md`](shared-references/writing-principles.md) | 12 条跨节写作原则 |

---

## 3. 阶段标注与节点对齐

83 份文件均已按 [`paper_phase.md`](../paper_phase.md) 的**六阶段模型**（0 问题锚定 / 1 选空白+定主张 / 2 章节规划 / 3 起草 / 4 反驳预演 / 5 自检核验）补上标注，并对齐到：

- 语义层 6 类：`Paper / Algorithm / AlgorithmModule / CodeRepository / CodeFunction / Benchmark`
- 应用层 21 类（`global` / `task-w` / `task-r` 三种生命周期）：如 `ResearchQuestion / EvidenceNorm / FailureMode / ResearchGap / Contribution / SectionPlan / CitedPaper / SectionDraft / ReviewPoint / FailureCheck`
- paperapp 14 动态类：`DomainProfile / IdeaNode / GateVerdict / HumanDecision / KnowledgeSignal / ExplorationFrontier / …`

对齐状态：**完全对齐 20 / 部分对齐 33 / 无法完全对齐 26 / 无法对齐 4**。
其中「无法对齐」的 4 份是战略快照与历史 persona 存档，判断为**不应进知识图**。

新增节点的集中判断见 [阶段与节点对齐汇总.md](阶段与节点对齐汇总.md) §3：
- **应新增 7 个**：`Claim / ClaimAnchor / TDAL / IdeaDAG / FalsificationRecord / MethodLock / VerificationRoute`
- **改为属性扩展 12 项**（如 `FigureAudit → FigureAsset.audit_verdict`、`ExecutionSession → RunArtifact` 加字段）
- **不进图 4 类**（运行态、项目治理、历史存档、纯约束法条）

## 4. 覆盖性校验

| 项 | 结果 |
|---|---|
| 源文件 md 数 | 83 |
| 产出 md 数 | 83 |
| 缺失 / 多余 | 0 / 0 |
| 六节结构完整 | 83 / 83 |
| 阶段与节点对齐块完整 | 83 / 83 |
| 断链 | 0（相对链接全部指向本目录内文件） |

## 5. 使用建议

1. 想知道「某个 skill 到底读入什么、吐出什么」→ 直接看其 `2.1 / 3.1` 两张表。
2. 想知道「它属于论文生成哪一步、对齐哪个节点」→ 看文件头的「阶段与节点对齐」表，或 [汇总索引](阶段与节点对齐汇总.md) §2。
3. 想把某 skill 落到分子项目 → 看 `6. 与分子项目的映射`，再对应 `docs/question_knowledge_skills/16_索引与缺口汇总.md` 的落点清单。
4. 想核对门与阈值 → 看 `4. 判定与门`，其中的脚本名与退出码均已按 `scripts/` 与 `kernel/` 核实。
