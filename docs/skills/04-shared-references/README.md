# `shared-references` 全景索引与阅读路径

> **源**：`SciForge-OSS-master/skills/shared-references/` —— **49 份顶层契约 md** + `schemas/`（23 个 `*.schema.json` + `README.md`）+ `reviewer-prompts/`（`README.md` + `economics.md`）。
> **性质**：这不是 skill，而是**被所有 skill 引用的共享契约层**。若 `SKILL.md` 是「给模型的说明书」、`scripts/` 是「给内核的判定器」，那 `shared-references/` 就是**两者的共同法条**。

---

## 1. 权威顺序（冲突裁决）

```
output-protocol.md          ← 目录布局唯一权威
artifact-registry.md        ← 产物契约（名/生产者/消费者/schema/verifier）
integration-contract.md     ← 五组件接线
schemas/*.schema.json       ← 字段级机器契约
SKILL.md 散文 / 示例        ← 最低；示例与 registry 冲突时 registry 赢
```

`artifact-registry.md` 自述：它是为治两类故障而建的 SSoT —— **Phantom artifacts**（生产者写 `CLAIMS_FROM_RESULTS.md`、消费者找 `CLAIM_VERDICT.md`，链静默断裂）与 **Schema drift**（加字段没人跟，预注册锁形同虚设）。

---

## 2. 49 份契约分类（4 组 → 4 份指导文档）

### 组 1 · 治理、启动与输出（14 份）→ [01-governance-and-output.md](01-governance-and-output.md)

| 文件 | 行 | 一句话 |
|---|---:|---|
| `artifact-registry.md` | 194 | 承重产物 SSoT：路径/生产者/消费者/schema/verifier |
| `assurance-contract.md` | 247 | `assurance` 轴与 6 态 verdict 状态机 |
| `integration-contract.md` | 248 | 五组件接线与验证、live integration registry |
| `output-protocol.md` | 197 | 目录树、版本化写入、长跑恢复、verdict 校验 |
| `output-manifest.md` | 84 | `.sciforge/MANIFEST.md` append-only 行协议 |
| `output-versioning.md` | 82 | 双写（时间戳副本 + 固定名副本）、时间戳格式 |
| `output-language.md` | 42 | 什么本地化 / 什么绝不本地化 |
| `project-architecture-contract.md` | 208 | GitHub 式 README、工作区卫生、Phase 16 cleanliness audit |
| `startup-protocol.md` | 155 | **每个 skill 启动必做 5 步**（读领域签名） |
| `skill-config.md` | 192 | 集中公共旋钮、优先级、透明性 |
| `effort-contract.md` | 170 | 四档 effort、hard invariants、per-skill 档位表 |
| `pipeline-integrity.md` | 126 | 每阶段入口的前置完整性检查与日志格式 |
| `grounding-check.md` | 80 | 轻量「有没有凭空断言」自检清单 |
| `plugin-router.md` | 100 | 非约束咨询层；插件永不产生注册产物 |

### 组 2 · 领域适配与置信（14 份）→ [02-domain-and-confidence.md](02-domain-and-confidence.md)

| 文件 | 行 | 一句话 |
|---|---:|---|
| `domain-adaptation-contract.md` | 305 | **TDAL 四维联合置信 locked schema** |
| `domain-adaptation-guide.md` | 734 | 7 步执行指南 + 5 领域示例 + 6 验收用例 |
| `domain-adaptive-pipeline.md` | 172 | 按 evidence_type/paradigm 覆盖 Phase 5/6/11 强度 |
| `domain-contribution-protocol.md` | 197 | 新增 `evidence_type` 的 PR 契约 + falsification test set |
| `domain-failure-modes.md` | 104 | 领域失败模式 catalog 与扩展方式 |
| `domain-signature-consumer.md` | 236 | 每个 skill 该消费签名的哪些字段 |
| `discipline-context.md` | 90 | **无 DISCIPLINE_CONTEXT**，只有 `general` no-op stub |
| `discipline-paradigm.md` | 90 | 4 范式（formal/empirical/interpretive/design） |
| `discipline-writing.md` | 213 | mode-selected 章节集与跨学科写作原则 |
| `confidence-uplift.md` | 314 | TDAL ≤ WEAK 时的三种有界提升机制 |
| `ouroboros-integration.md` | 609 | Basic(D 维) / Deep(T 维 uplift) |
| `methodology-and-context-contract.md` | 74 | 5 条横切纪律（sufficiency / evidence-forcing / bundle-out / deterministic-first / reviewer-raw） |
| `multi-fidelity-evaluation.md` | 205 | 三层过滤、false-trick 检测、资源预算 |
| `verification-routing.md` | 59 | experiment-first 默认、终局决策、`na_verdicts` |

### 组 3 · 选题、搜索与评估（9 份）→ [03-ideation-and-evaluation.md](03-ideation-and-evaluation.md)

| 文件 | 行 | 一句话 |
|---|---:|---|
| `idea-dag-schema.md` | 241 | DAG（非树/图）、节点状态、边类型、UCB 语义 |
| `mcts-search-protocol.md` | 308 | UCB 公式、四相循环、anti-false-trick、参数表 |
| `fantasy-prevention.md` | 150 | 5 门防幻想（机器门是 `fantasy_gate.py`） |
| `s2-protocol.md` | 196 | ScientistTwo parity：ladder / ablation / rebuttal / audit |
| `experience-replay-contract.md` | 83 | `LESSONS.json` 生产者/消费者、失败路由 |
| `competitive-analysis.md` | 178 | 竞争格局与 Crush-tier 能力矩阵（基线文档） |
| `competitive-drift-monitor.md` | 254 | 季度自动漂移检查 + 锁定 Transition Rubric + PR |
| `engineering-grounding-contract.md` | 233 | AI 视角 8 子维 EG 报告与 tier 分类 |
| `background-dispatch-protocol.md` | 192 | >5min 后台、状态轮询、下载也不许跳过 |

### 组 4 · 图、写作与评审（12 份）→ [04-figures-writing-review.md](04-figures-writing-review.md)

| 文件 | 行 | 一句话 |
|---|---:|---|
| `color-themes.md` | 103 | Dopamine(L1) + 连续色图(L2)、三道安全网、禁用色 |
| `figure-complexity-contract.md` | 280 | 组件丰富度 ≥60% 图标、边密度 ≤1.6、零文本重叠 |
| `figure-layout-contract.md` | 277 | 五点 Figure Contract、page archetypes、A11 1.5pt 门 |
| `figure-quality-contract.md` | 186 | 16:9、栏宽预设、PDF+SVG 双输出、可读性与工具链 |
| `figure-quality-review.md` | 115 | 视觉自审 Tier1(必) / Tier2(可选)、能力探测 |
| `writing-principles.md` | 208 | 风格合同、anti-AIGC、SCI stance-first、5 句摘要 |
| `paper-voice-contract.md` | 200 | claim 纪律、内部术语替换表、negative vocabulary |
| `paper-modes.md` | 225 | 5 种模式、章节集、强调矩阵、页数带 |
| `citation-discipline.md` | 57 | 3 层反幻觉 + BibTeX 管理规则 |
| `venue-checklists.md` | 138 | 单一统一清单（不按 venue 分叉） |
| `venue-profiles.md` | 121 | 单一 `elsarticle` 模板 + mode-aware 页数 |
| `reviewer-independence.md` / `reviewer-routing.md` / `review-tracing.md` | 36 / 42 / 123 | 只喂原始产物 / 角色轮换 / 评审留痕 |

> 分组按**用途**划分，个别文件跨组（如 `background-dispatch-protocol.md` 既是治理也是执行），已在相应指南中交叉引用。

---

## 3. `schemas/` 与 `reviewer-prompts/`

| 子目录 | 内容 | 指南 |
|---|---|---|
| `schemas/` | 23 个 `*.schema.json`（draft 2020-12 的 stdlib 子集）+ `README.md`(154) | **[schemas-guide.md](schemas-guide.md)** —— 字段表、校验器用法、跨字段后检、新增 SOP、12 条 known gaps |
| `reviewer-prompts/` | `README.md`(7，canonical index) + `economics.md`(167，`senior-econ-editor`) | **[reviewer-prompts-guide.md](reviewer-prompts-guide.md)** —— 六段结构、14 类 rejection ledger、打分 SOP、如何为分子算法设计定制等价 persona |

> `README.md` 明确：`cs-ml` / `physics` persona 尚未提取，目前**内联在 `/auto-review-loop/SKILL.md` 里仍是权威**。`economics.md` 的三份旧内联副本必须改为指向它 —— 分叉副本是 bug。

---

## 4. 怎么用这套契约（3 条）

1. **改目录结构** → 先改 `output-protocol.md`，再镜像 `artifact-registry.md`，再建/改 schema，最后注册到 `validate_verdicts.py`。顺序不可反。
2. **加新 skill / 新阶段** → 在 `startup-protocol.md` 的 5 步上加消费规则（写进 `domain-signature-consumer.md`），在 `artifact-registry.md` 登记它产出的每个被下游依赖的文件，在 `effort-contract.md` 补 per-skill 档位。
3. **发现散文与代码冲突** → 以 `scripts/` 为准，并把它记成「known gap」（`schemas/README.md` §Known gaps 已裁决 12 条，是这种处理的范本）。

---

## 5. 与总框架的关系

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 的 8 条元原则、5 命名空间类清单、25 条关系词表，绝大部分是从这 49 份契约中提升出来的。读框架建立全局，读本目录 4 份指南做实施，读源文件取精确阈值。
