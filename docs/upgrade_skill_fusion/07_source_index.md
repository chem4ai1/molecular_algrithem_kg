# 07 · 源码索引与回溯表

> 根目录 `R = /home/zengshuxin/xKG-main/SciForge-OSS-master/skills/`
> 本框架根目录 `M = /home/zengshuxin/MolLingo-main/repro/mechanism_kb/`
> 论文生成项目 `P = /home/zengshuxin/molecular_algrithem_design/`
> 所有行号均指原始源文件，可回溯。

---

## 1. 26 个 SKILL.md（8 meta + 1 orchestrator + 17 support）

### meta-skills（8）

| 路径（R/ 下） | 行数 | role | 阶段 / 模式 |
|---|---|---|---|
| `meta-skills/domain-signature/SKILL.md` | 162 | domain-characteristic-extractor | 1a OPTIONAL |
| `meta-skills/domain-learner/SKILL.md` | 182 | domain-characteristic-learner | 1b MUST，`sole writer` |
| `meta-skills/idea-discovery/SKILL.md` | 295 | research-idea-generation | 2 MUST |
| `meta-skills/novelty-check/SKILL.md` | 211 | novelty-verifier | 3 MUST + 人工 |
| `meta-skills/universal-retrieval/SKILL.md` | 269 | academic-retriever | 4broad/4targeted MUST never skipped |
| `meta-skills/dynamic-tooling/SKILL.md` | 179 | tool-builder | 横切按需 |
| `meta-skills/dynamic-sandbox/SKILL.md` | 151 | computation-sandbox | 横切按需 |
| `meta-skills/unified-plotting/SKILL.md` | 447 | figure-renderer-and-spec-generator | 11 |

### orchestrator（1）

| 路径 | 行数 | 关键段 |
|---|---|---|
| `orchestrator/auto-pipeline/SKILL.md` | 575 | `:5` 定位；§2 26 节点 DAG；§3 边界 5 件事；§4 Phase Mode Table；§Domain Signature Propagation；§预算双护栏 |

### support（17，用户特别要求覆盖）

| 路径 | 行数 | role | 主要知识点 ID |
|---|---|---|---|
| `support/intake-triage/SKILL.md` | 74 | intake-triage-router | K-G1 |
| `support/adversarial-falsification/SKILL.md` | 257 | idea-falsification-auditor | K-C1, K-C2 |
| `support/kill-argument/SKILL.md` | 349 | adversarial-attack-defense-reviewer | K-C9, K-D4 |
| `support/experiment-ladder/SKILL.md` | 75 | experiment-ladder-critic | K-D6 |
| `support/experiment-execution/SKILL.md` | 647 | experiment-runner | K-D3, K-D4, K-D8 |
| `support/theory-derivation/SKILL.md` | 308 | theory-builder-and-symbolic-verifier | K-A1 |
| `support/method-registry/SKILL.md` | 417 | method-registry-builder | K-D1, K-D2 |
| `support/ablation-planner/SKILL.md` | 81 | ablation-planner-critic | K-D5, K-D6 |
| `support/leakage-audit/SKILL.md` | 343 | structural-leakage-auditor | K-C4 |
| `support/logic-verification/SKILL.md` | 303 | logical-consistency-auditor | K-C3 |
| `support/invariant-check/SKILL.md` | 166 | phase-boundary-verifier | K-C5, K-C7 |
| `support/result-to-claim/SKILL.md` | 429 | result-to-claim-gate | K-A1~A5 |
| `support/quality-gate/SKILL.md` | 344 | pre-writing-quality-gate | K-C6, K-F7 |
| `support/paper-writing/SKILL.md` | 396 | paper-composer | K-F2, K-F3 |
| `support/unified-plotting` → 见 meta | — | — | K-F9 |
| `support/paper-compile/SKILL.md` | 294 | latex-compiler | K-F9 |
| `support/auto-review-loop/SKILL.md` | 625 | autonomous-review-loop-orchestrator | K-F5, K-F6 |
| `support/citation-audit/SKILL.md` | 388 | bibliographic-integrity-auditor | K-B3 |
| `support/rebuttal/SKILL.md` | 164 | rebuttal-letter-writer | K-F6 |
| `support/publishability-score/SKILL.md` | 180 | paper-publishability-assessor | K-F8 |

---

## 2. shared-references 关键契约（45 份中的 14 份）

| 文件（R/shared-references/） | 知识点 | 关键行 |
|---|---|---|
| `fantasy-prevention.md` | K-B1, K-B2 | `:5,42-46`（三源追溯）、`:98-104`（5-Gate）、`:116-118,135,140-143`（阴性即 conjecture） |
| `citation-discipline.md` | K-B5 | verbatim evidence |
| `writing-principles.md` | K-F1, K-F2, K-F4 | `:27-37` 黑名单、`:41` 锚点、`:74-85` 零道歉/hedge 带界、`:87-88` Limitations、`:201,203` Abstract/claim |
| `reviewer-independence.md` | K-F5 | `:20-24` 输入污染禁区 |
| `domain-adaptation-contract.md` | K-A2~A5, K-E4 | `:5,79` 4 维乘积、`:205-208,267` 动词映射、`:211-213,257,283` 最弱维/不 inflate、`:298-305` PASS 才可回流 |
| `confidence-uplift.md` | K-A5 | `:291` UNSUPPORTED 三轮 BLOCK |
| `experience-replay-contract.md` | K-D7, K-F4 | `:46,60-63` LESSONS 4 类 key |
| `multi-fidelity-evaluation.md` | K-A6 | 多保真度 |
| `domain-failure-modes.md` | K-E6 | 领域失败模式注入 |
| `domain-signature-consumer.md` | K-E3 | pointer-load |
| `pipeline-integrity.md` | K-G4 | verdict 传播 |
| `mcts-search-protocol.md` | K-E2 | 频次化先验 |
| `engineering-grounding-contract.md` | K-C2 | EG 8 维 |
| `schemas/README.md` + 27 个 `*.schema.json` | verdict / claim / 实验矩阵的结构契约 | 见目录 |

---

## 3. 本框架对照位置（现有 prompt 与结果）

| 用途 | 路径（M/ 下） | 关键位置 |
|---|---|---|
| 编辑生成 SYSTEM | `eval_pipeline.py` | `:40` |
| 抽取 SYSTEM / prompt | `ontology_grounded_extraction.py` | `:47`, `:55` |
| L2 标注 SYS / prompt | `label_l2_gemini.py` | `:33`, `:37` |
| 分类 SYS / prompt | `classify_corpus.py` | `:32`, `:36` |
| 工具链 SYSTEM | `toolenv/env.py` | `:18` |
| GRPO 状态 | `toolenv/grpo_traj.py` | `:30` |
| 工具探测 | `toolenv/probe_qwen_toolcall.py` | `:10` |
| 端到端结果 | `end2end_results.json` | — |
| 本体 TBox | `../../ontology/mech/07_tbox/mech-decision-axioms.ttl` | `:21-27` 决策动作 |
| 编辑契约 | `../../ontology/mech/07_tbox/mech-mechanism-kernel.ttl` | `:196-200` A21 |
| 测试方案 | `COMPREHENSIVE_TEST_PLAN.md` | G1–G17 |
| 环境奖励 | `ENV_REWARD_DESIGN.md` | S1 probe |
| 论文 | `P/../SynCraft-Core-main/paper/acl_latex.tex` | 11 节 / 5 表 |

---

## 4. paperapp 现状（P/ 下）

| 项 | 位置 |
|---|---|
| 22 个模块 | `src/capfactory/paperapp/`（align / cli / config / coverage / gates / hitl / materialize / miners / nodecache / paperspec / promote / registry / replay / report / runner / schemas / signals / tbox / util / validate / vocab_bridge） |
| API | `web/paperapp_api.py`；`/api/v10/paperapp/*` 43 GET + 6 POST |
| 前端 | `web/static/paperapp.html` 7 tab（v2 加 T7 人工决策） |
| 测试 | `tests/test_paperapp_s0..s6.py`，194 项；`bash scripts/test_all.sh` |
| 计划 | `docs/plan/S0..S6`、`V2_DELTA.md`、`TEST_PLAN.md`、`S6_FINAL_REPORT.md` |
| 集成报告 | `docs/INTEGRATION_REPORT.md`、`docs/DESIGN_REFLECTION_V2.md` |
| 解析文档 | `docs/skills/` 24 篇（8 meta 逐篇解析 + 框架 + 共享引用 + 支撑 + 编排） |

---

## 5. 精度警告（精读发现，勿照抄）

1. `logic-verification/SKILL.md` 自称 "6-dimension / 20-category"（`:13,60`），但 taxonomy 表实列 **21 条**（A7+B6+C6+D2）。
2. `adversarial-falsification/SKILL.md` 同时出现 "6-dimension"（`:13`）、"5 attack vectors"（`:35`）、`max_attack_vectors=5`（`:242`），另有独立 Phase 6 数据可用性检查。
3. 因此 **`04` 的模板按阶段名显式枚举，不写死计数** —— 这正是本框架 Q07 那类静默不一致的教训。

> 另：`docs/skills/` 是**解析文档**不是源码；本套方案的所有机制引用均以 `R/` 下真实 SKILL.md 为准。
