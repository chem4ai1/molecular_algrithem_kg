# 论文生成前后端升级方案 · Skill 知识点融合对照

> 2026-11-15。基于 `xKG-main/SciForge-OSS-master/skills/` **全部 26 个 SKILL.md**
> （8 meta + 1 orchestrator + **17 support**，用户明确要求不只看 meta-skills）、
> 45 份 `shared-references/` 契约、27 个 `schemas/*.json`，
> 对照现有分子编辑框架（`MolLingo-main/repro/mechanism_kb/` +
> `SynCraft-Core-main/paper/` + `molecular_algrithem_design/docs/plan/` 的 paperapp）。

---

## 0. 这套文档要解决什么

现有分子框架已经做到了：本体语义（TBox/ABox/SHACL）、13 个 transform 工具、
9 个 tool-calling、全量标注、GRPO 训练池、端到端对标（hardOK 0.125→1.000）。
但**「把结果写成论文」这一段仍靠散文式 prompt 与人工判断**，缺 SciForge 那套
「机器 verdict + 边界复述 + 反幻觉 + 证据分级」的硬约束。

因此本套文件回答三件事：
1. **要解决的问题**（`01`）——用本框架真实踩过的坑做锚，不是泛泛而谈
2. **要融入的知识点 + 对应 prompt + 如何改造**（`02`/`03`/`04`）——完整对照表
3. **前后端怎么升级**（`05`/`06`）——把知识点落成 orchestrator 门、API、tab、测试

---

## 1. 两个体系对照（一句话定位）

| | SciForge-OSS | 我的分子框架 |
|---|---|---|
| 编排 | `auto-pipeline` 26 节点 DAG，唯一入口编排器 | `run_qwen_tool_agent.py` 多轮循环 + `SynCraftEnv.step`（隐式编排） |
| 契约 | 26 个 SKILL.md + 45 shared-ref + 27 schema | 9 个工具 `description` + TBox/SHACL |
| 判定 | `scripts/*.py` 硬退出码，模型读 verdict | `validate_edits` / RDKit / SHACL 有，但**散、无统一 verdict 链** |
| 证据 | 3-fidelity claim ladder、TDAL 4 维乘积、引用三层校验 | 8 指标 + hardOK，**无 claim 分级、无置信度分解** |
| 写作 | paper-writing / quality-gate / auto-review-loop / publishability-score | 一篇静态 `acl_latex.tex`，无编译门禁之外的检查 |
| 前端 | paperapp 7 tab（已实现，194 测试） | 无 |

**核心判断**：我的框架在「分子编辑正确性」上强，在「研究过程可信度 / 论文声明可追溯」上弱；
SciForge 恰好相反。融合方向不是替换，而是**把 SciForge 的证据链与 verdict 门，
套在分子框架已有的机器判定之上**。

---

## 2. 目录（分批输出）

| 文件 | 内容 |
|---|---|
| `01_problem_inventory.md` | 6 组共 24 个待解决问题，每条带本框架实测证据 |
| `02_knowledge_nodes.md` | 26 skills + shared-ref 提炼的 6 族 30 个知识点（带源文件行号） |
| `03_prompt_mapping.md` | ★ **完整对照表**：问题→知识点→来源 skill→现有 prompt→改造后 prompt→验收 |
| `04_prompt_templates.md` | 改造后的 8 份可直接复制的 prompt 模板（含 system / user / verdict schema） |
| `05_pipeline_upgrade.md` | 前后端升级架构：orchestrator 门、新增 API、前端 tab、数据流 |
| `06_test_plan.md` | 验收矩阵：每个知识点如何被测试证明「真的融入了」 |
| `07_source_index.md` | 原始 skills 索引与行号，供回溯 |

---

## 3. 方案思路（5 条，先在脑子里立住）

**S1 · 不改判定器，只改 prompt 与边界。**
本框架已有 RDKit / SHACL / `validate_edits` 这些确定性判定器，
对应 SciForge 的 `scripts/*.py`。缺的是「模型必须读机器 verdict、不得自评」这条散文契约。
所以最小改造是：**在每个 prompt 末尾加 verdict 消费条款**，而不是重写代码。

**S2 · 把「我完成了」变成不可信声明。**
SciForge `quality-gate` 的核心：`The agent's own assessment of its work is the least reliable signal`。
本框架已经吃过三次亏（`FM_` 前缀不匹配让加分从未生效、`constraint_recall` 口径不公、
`score=None` 异常被吞成 0 导致假「无分歧」）。
对应改造：每个生成 prompt 都要带 `n_success/n_error`、证据指针、禁止自评通过。

**S3 · 证据分级决定动词。**
`result-to-claim` 的 3-fidelity ladder（symbolic→proven / numerical→supported /
qualitative→suggests）直接解决本框架的「SA 单指标奖励破坏性编辑」：
SA Δ 是 numerical proxy，不是「分子真的可合成」；
逆合成路线数/PLIP 才是任务级证据。论文里必须按证据等级选动词。

**S4 · 领域画像从文献学，不从硬编码规则学。**
`domain-learner` 的 `evidence_norm_profile`（≥3 seeds、mean±std、scaffold split、
baseline+ablation、阴性进 Limitations）正好补本框架 `COMPREHENSIVE_TEST_PLAN.md`
里 G1–G17 门禁的「阈值从哪来」。当前阈值是我拍的，应改为从 seed paper 归纳并带 `learning_basis`。

**S5 · 前后端只做「可审计性」，不做新研究。**
paperapp 已有 7 tab 与 43+6 API。升级应加的是：
`verdict trail` / `claim ladder` / `evidence norm` / `negative results` 四类视图，
把后端已有的机器产物**展示出来并让人能点「不通过」**，而不是再生成一遍。

---

## 4. 使用方式

1. 先读 `03_prompt_mapping.md` 找到你关心的问题编号（Q-xx）
2. 到 `04_prompt_templates.md` 复制对应模板，替换现有 prompt 常量
3. 按 `06_test_plan.md` 跑一条最小回归，确认改造生效
4. `05_pipeline_upgrade.md` 是后端/前端改造清单，按优先级分批实施

> 所有「现有 prompt」均摘自本框架真实代码，路径与常量名可查；
> 所有「知识点」均标了 SciForge 源文件行号，可回溯，不凭记忆杜撰。
