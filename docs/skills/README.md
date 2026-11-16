# SciForge-OSS `meta-skills` 解析索引

对 `/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/meta-skills/` 下 **8 个 SKILL.md（共 1896 行）** 的逐篇结构化解析，并结合 `/home/zengshuxin/xKG-main/SciForge-OSS-master/scripts/` 的对应代码。

> 每篇统一回答 7 个问题：① 解决什么问题 ② 对应论文生成哪个阶段 ③ 对应论文/算法/代码/数据哪个模块的哪个部分 ④ 做了什么 ⑤ 怎么做 ⑥ 运用了哪些关键知识节点 ⑦ 对应哪些脚本、怎么判定。另附产物契约、边界反模式、以及对「分子算法设计」本体与 capfactory 语义层的可迁移点。

---

## 总览表

| # | Skill | 阶段 | 模式 | 类型 | 主力对应脚本 | 文档 |
|---|---|---|---|---|---|---|
| 1 | `domain-signature` | **Phase 1a** | OPTIONAL | `meta-skill` | `tdal_compute.py`（间接） | [01-domain-ideation/domain-signature.md](01-domain-ideation/domain-signature.md) |
| 2 | `domain-learner` | **Phase 1b** | MUST | `meta-skill` | `tdal_compute.py`（A 维 / floors） | [01-domain-ideation/domain-learner.md](01-domain-ideation/domain-learner.md) |
| 3 | `idea-discovery` | **Phase 2** | MUST | `meta-skill` | `gap_gate.py`、`dep_gate.py`、`detect_device.py` | [01-domain-ideation/idea-discovery.md](01-domain-ideation/idea-discovery.md) |
| 4 | `novelty-check` | **Phase 3** | MUST + 人工检查点 | `reference-skill` | `gap_gate.py`、`doi_gate.py`、`citation_support.py`、`fantasy_gate.py`、`claim_anchor_gate.py` | [01-domain-ideation/novelty-check.md](01-domain-ideation/novelty-check.md) |
| 5 | `universal-retrieval` | **Phase 4broad / 4targeted** | MUST，never skipped | `reference-skill` | `gap_gate.py`、`doi_gate.py`、`citation_support.py`、`s2_integrity_gate.py` | [02-retrieval-tooling/universal-retrieval.md](02-retrieval-tooling/universal-retrieval.md) |
| 6 | `dynamic-tooling` | 横切（2.5 / 6a / 6b / 11） | 按需 | `reference-skill` | `dep_gate.py`、`security_scan.py`、`smoke_gate.py`、`arb_verify.py` | [02-retrieval-tooling/dynamic-tooling.md](02-retrieval-tooling/dynamic-tooling.md) |
| 7 | `dynamic-sandbox` | 横切（6a / 6b / 6c） | 按需 | `reference-skill` | `security_scan.py`、`smoke_gate.py`、`leakage_scan.py`、`workspace_hygiene.py` | [02-retrieval-tooling/dynamic-sandbox.md](02-retrieval-tooling/dynamic-sandbox.md) |
| 8 | `unified-plotting` | **Phase 11** | MUST | `meta-skill` | `plotting/{render_figure,figure_audit,figure_recipes,method_recipes,sciforge_style}.py`、`figure_style_gate.py`、`check_figure_embedding.py` | [03-figures-presentation/unified-plotting.md](03-figures-presentation/unified-plotting.md) |

---

## 分批依据（按功能 / 阶段）

| 批次 | 目录 | 覆盖阶段 | 共同主题 |
|---|---|---|---|
| ① 领域与选题层 | `01-domain-ideation/` | Phase 1a–3 | 「研究什么、为什么值得做」：领域证据规范 → gap 锚定选题 → 前沿定位与收敛 |
| ② 检索与工具层 | `02-retrieval-tooling/` | Phase 4 + 横切 | 「凭据与能力从哪来」：文献真实性、运行时造工具、可复现执行 |
| ③ 图表与呈现层 | `03-figures-presentation/` | Phase 11 | 「结果怎么变成可发表证据」：单入口渲染 + 机械审计 + 图表预算 |

> `meta-skills/` 中**没有**写作/评审类 skill —— 它们属于 `skills/support/`（`paper-writing`、`paper-compile`、`auto-review-loop`、`citation-audit` 等 20 个）。本目录只解析 `meta-skills/`，支撑类在框架文档中以「阶段」形式纳入。

---

## 全局结论（三点最重要）

### 1. 三层解耦：`skills/` 是契约，`scripts/` 是判定器，`auto-pipeline/` 是编排

```
skills/meta-skills/*.md   → 给 LLM 的行为契约（该做什么、产物长什么样）
        ↓ 写文件产物
scripts/*.py              → 给内核的确定性判定（正则 / AST / 公式 / 哈希 / exit code）
        ↓ 机器 verdict
orchestrator/auto-pipeline/SKILL.md → 读 verdict、套质量门、触发回退
```

8 个 meta-skill 里**只有 `unified-plotting` 有完整可执行实现**（5 个 plotting 模块 + A1–A11 审计）；其余 7 个都是「散文契约 + 下游脚本兜底」。orchestrator 称之为 "**Mechanical verdicts via tool, not prose**"。

### 2. 文献先于 idea，机械判定先于 LLM 判断

- v6.0 gap chain：`4broad → GAP_REPORT.md → gap_gate.py PASS → 才允许 idea 打分`；
- v3.1 Type-A/B 解耦：GPU/数据/依赖/语法四项**零 LLM** 判定，FAIL 直接淘汰，绝不进 novelty 评审。

### 3. 一切靠「锚 + 哈希 + 单一写入者」防漂移

| 机制 | 例子 |
|---|---|
| 锚 | `gap_anchor`、`claim_anchor`、`ProblemAnchor`(INV-G1) |
| 哈希 | `sha256(code+input+output)`、工具 `sha256`、`Section 3 hash lock`、claim node outputs 哈希复核 |
| 单一写入者 | `domain-signature.json` 只由 learner 写；`references.bib` 全 wave 累积不 fork；`FIGURE_AUDITS.json` upsert |

---

## 对应脚本总表（33 个，按职责）

| 职责 | 脚本 |
|---|---|
| 领域/置信 | `tdal_compute.py` |
| 选题/gap | `gap_gate.py`、`s2_ladder_gate.py`、`s2_ablation_gate.py`、`s2_audit.py`、`s2_integrity_gate.py` |
| 引用真实性 | `doi_gate.py`、`citation_support.py`、`claim_anchor_gate.py` |
| 反幻想/逻辑 | `fantasy_gate.py`、`arb_verify.py`、`fairness_gate.py`、`completion_gate.py` |
| 代码/依赖/设备 | `dep_gate.py`、`detect_device.py`、`security_scan.py`、`ci_check.py` |
| 执行与工作区 | `smoke_gate.py`、`leakage_scan.py`、`workspace_hygiene.py` |
| 图 | `figure_style_gate.py`、`check_figure_embedding.py`、`plotting/*.py` |
| 汇总/裁决 | `sciforge_audit.py`、`validate_verdicts.py`、`submission_ready.py` |

判定约定：`exit 0 = PASS/SKIP`，`exit 2 = FAIL`（`security_scan.py` 另有 `--strict` 下 `1 = WARN`；`render_figure.py --strict` 下 audit FAIL = `4`）。

---

## 完整应用层本体框架

➡ **[APPLICATION_ONTOLOGY_FRAMEWORK.md](APPLICATION_ONTOLOGY_FRAMEWORK.md)** —— 把 8 个 skill 的知识节点、26 节点 DAG、scripts 的门、以及「论文/算法/代码/数据」四层模块整合成生成论文时应调用的完整应用层本体，并给出与 capfactory 语义层、GGR 复现层的对接表和可执行 SOP。

---

## 阅读建议

1. 先看框架文档 §2「三层架构」与 §3「阶段—skill—脚本全表」建立全局；
2. 再按自己关心的阶段读对应批次；
3. 若要落地到本体/知识图谱，重点看每篇的 **§6 关键知识节点**（类/属性/关系）和框架文档 **§4–§5**（类清单与关系词表）；
4. 每篇 §9/§10 记录了文档内部矛盾与版本残留 —— 实施时**以 `scripts/` 代码为准**，不要照抄散文里的数值。

---

# 续批：共享契约 / 编排器 / support skills（**指导性**文档）

> 上一批回答「是什么、对应哪个阶段、用了哪些知识节点」；这一批回答 **「具体怎么用、按什么顺序、过哪些门、失败怎么处理、改配置改哪里」**。解析范围覆盖 `shared-references/`（49 契约 + 23 schema + 2 评审提示词）、`orchestrator/auto-pipeline/SKILL.md`（575 行）、`support/`（19 个 SKILL.md + 2 个 LaTeX 模板），共约 18 000 行源文。

| 批次 | 目录 | 文件 | 覆盖源 | 主题 |
|---|---|---|---|---|
| ④ 共享契约 | `04-shared-references/` | `README.md`、`schemas-guide.md`、`reviewer-prompts-guide.md`、`01`–`04` 四份主题指南 | 49 契约 + 23 schema + 2 persona | 治理/输出、领域置信、选题评估、图与写作评审 |
| ⑤ 编排器 | `05-orchestrator/` | `auto-pipeline-guide.md` | 575 行 SKILL.md | 启动、26 节点、每边界 5 件事、L1–L13、预算、恢复 |
| ⑥ 执行者 | `06-support-skills/` | `README.md` + `01`–`05` 五份阶段指南 | 19 个 support skill | 方法锁定、实验、审计、claim/评审、写作交付 |

## 新增的关键认识

1. **`shared-references/` 是法条层**：`output-protocol.md`（目录）> `artifact-registry.md`（产物契约）> `integration-contract.md` > `schemas/`（字段）> SKILL.md 散文。它专门治两类静默故障：Phantom artifacts（生产者/消费者文件名不一致）与 Schema drift。
2. **`support/` 才是干活的人**：orchestrator 只分发/读 verdict/套门/回退，19 个 support skill 各自负责一个阶段；`meta-skills/` 是横切能力。三层加起来才是完整管线。
3. **两条轴、两道阈值、两类回退最容易写错**：`effort`（深度）与 `assurance`（审计严格度）独立；Phase 14 的 boundary floor **6.0** 与 S2 rebuttal bar **8.0** 不同；BA（idea 错了，回 Phase 2，全局 ≤2）与 in-phase fallback（执行出错，回相邻阶段，3 轮）不同。
4. **schema 不是全局 6 态**：`EVALUATION_REVIEW` 用 `ACCEPT/REVISE/REJECT`，`LEAKAGE_SCRUB` 用 `PASS/FAIL`，`BUDGET_FLOOR` 用 `PASS/IN_PROGRESS/BLOCKED`，`INVARIANT_CHECK` 字段叫 `overall_verdict`，`REVIEW_LEDGER` 是单对象 `details.rounds[]`。详见 [04-shared-references/schemas-guide.md](04-shared-references/schemas-guide.md)。

## 建议阅读顺序

```
APPLICATION_ONTOLOGY_FRAMEWORK.md（全局）
  → 05-orchestrator/auto-pipeline-guide.md（26 节点与门）
  → 04-shared-references/01-governance-and-output.md（启动与输出纪律）
  → 06-support-skills/README.md + 对应阶段指南（实际执行）
  → 04-shared-references/schemas-guide.md（写 verdict 时对照）
```

## 完整目录

```
docs/skills/
├── README.md                          ← 本文件（两批总索引）
├── APPLICATION_ONTOLOGY_FRAMEWORK.md  ← 完整应用层本体框架
├── 01-domain-ideation/        4 篇   ← Phase 1a/1b/2/3
├── 02-retrieval-tooling/      3 篇   ← Phase 4 + 横切检索/工具/沙箱
├── 03-figures-presentation/   1 篇   ← Phase 11
├── 04-shared-references/      7 篇   ← 49 契约 / 23 schema / 2 persona
├── 05-orchestrator/           1 篇   ← 26 节点编排
└── 06-support-skills/         6 篇   ← 19 个阶段执行者
```

> 两批合计 **24 份 md、4 404 行**：第一批 10 份（8 篇逐篇解析 + 框架 + 索引），续批 14 份（04 批 7 + 05 批 1 + 06 批 6）。[APPLICATION_ONTOLOGY_FRAMEWORK.md](APPLICATION_ONTOLOGY_FRAMEWORK.md) 仍是总入口，续批是它的「实施层展开」。全部相对链接已校验，0 处断链。
