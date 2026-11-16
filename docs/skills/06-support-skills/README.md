# `support/` 19 个 skill 总览与分组指南

> **源**：`SciForge-OSS-master/skills/support/` —— **19 个 `SKILL.md`**（合计约 5 600 行）+ `paper-writing/templates/default/{main.tex, math_commands.tex}`（90 / 47 行）。
> **定位**：`meta-skills/` 是横切能力（领域、选题、检索、工具、沙箱、绘图），`support/` 是 **26 节点 DAG 上每个具体阶段的执行者**。orchestrator 只分发、不执行研究，真正干活的是这 19 个。

---

## 1. 19 个 skill 一览（按 DAG 顺序）

| Phase | Skill | 行 | 主要输出 | 门 / 边界 |
|---|---|---:|---|---|
| 0 前置 | `intake-triage` | 74 | `INTAKE_MANIFEST.json` + `INTAKE_REPORT.md` | 无（planning artifact） |
| 2.5 | `adversarial-falsification` | 257 | `SURVIVE/WEAKENED/FALSIFIED` + `FALSIFICATION_RECORD.json` | 假设健康 ≥6 或无反例；L1/L2 |
| 5 | `method-registry` | 417 | `METHOD_REGISTRY.md`(8 节) + `REGISTRY_HASH.txt` + `EXPERIMENT_MATRIX.json` | **人工审批**；L4 hash 失配 |
| 6a | `theory-derivation` | 308 | `derivation.py` + `derivation_output.md` + `PROOF_AUDIT.json` | SymPy 逐步验证 |
| 6b/6c | `experiment-execution` | 647 | `RESULT.json` + `.SMOKE.json` + `DISPATCH/STATUS.json` | toy gate、`budget_floor`、后台强制 |
| 6c | `experiment-ladder` | 75 | `S2_LADDER.json` | `s2_ladder` 门，ties fail |
| 7 | `leakage-audit` | 343 | `LEAKAGE_AUDIT.{md,json}` | Type I 无 CRITICAL；L8 |
| 8 | `logic-verification` | 303 | `LOGIC_VERIFICATION.{md,json}` | 零 FATAL/CRITICAL；L9 |
| 9 | `invariant-check` | 166 | `INVARIANT_CHECK.{md,json}` | INV-G1 内容哈希 |
| 10 | `result-to-claim` | 429 | `CLAIMS_FROM_RESULTS.md` + `TDAL.json` + `CLAIM_ANCHORS.json` | ≥ numerical fidelity；`s2_ablation` |
| 10 | `ablation-planner` | 81 | `ABLATION_LEDGER.json` | 5–6 plans；`s2_ablation` 门 |
| 12 前置 | `quality-gate` | 344 | `QUALITY_FLOOR_REPORT.md` + `SELF_DECEPTION_REPORT.md` | FAIL 阻断写作 |
| 12 | `paper-writing` | 396 | `main.tex` + `sections/*.tex` + `PAPER_PLAN.md` | elsarticle + leakage scrub |
| 13 | `paper-compile` | 294 | `main.pdf` + `COMPILE_REPORT.json` | 零 warning 零 error；L12 |
| 14 | `auto-review-loop` | 625 | `AUTO_REVIEW.md` + `REVIEW_STATE/LEDGER.json` | 分数 ≥6；校准 <8 触发 rebuttal |
| 14 | `kill-argument` | 349 | `KILL_ARGUMENT.{md,json}` | 反自欺；成立 → L11 BA |
| 14+ | `rebuttal` | 164 | `REBUTTAL_LETTER.md` | advisory（人审），禁声称不存在的实验 |
| 15 | `citation-audit` | 388 | `CITATION_AUDIT.{md,json}` | 3 层 + `doi_gate` + `citation_support` |
| 15.5 | `publishability-score` | 180 | `PUBLISHABILITY_SCORE.{md,json}` | 主实验逻辑轴 + `FAIRNESS` PASS |

> **两个模板**：`main.tex`(90) 是统一 `elsarticle` 骨架（不按 venue 分叉），`math_commands.tex`(47) 是数学宏。详见 [05-writing-and-delivery.md](05-writing-and-delivery.md) §4。

---

## 2. 5 份分组指导文档

| 组 | 文档 | 覆盖 skill | 核心主题 |
|---|---|---|---|
| ① 入口与方法锁定 | [01-intake-and-method.md](01-intake-and-method.md) | `intake-triage`, `adversarial-falsification`, `method-registry`, `theory-derivation`, `invariant-check` | 投料分类 → 先杀后证 → 预注册 hash lock → SymPy → INV-G1 |
| ② 实验与阶梯 | [02-experiments.md](02-experiments.md) | `experiment-ladder`, `experiment-execution`, `ablation-planner` | 三道前置门、toy KILL/PIVOT、`budget_floor`、S2 ladder/ablation |
| ③ 结构审计 | [03-audits.md](03-audits.md) | `leakage-audit`, `logic-verification`, `quality-gate`, `kill-argument` | Type I/IV、20 类问题、写作前硬门、KILL 人工检查点 |
| ④ claim 与评审 | [04-claims-and-review.md](04-claims-and-review.md) | `result-to-claim`, `auto-review-loop`, `rebuttal`, `publishability-score` | 3-fidelity、6.0/8.0 双阈值、ledger 形状、主逻辑轴 |
| ⑤ 写作与交付 | [05-writing-and-delivery.md](05-writing-and-delivery.md) | `paper-writing`, `paper-compile`, `citation-audit` | 五模式、零 warning 编译、四层引用链 |

每份统一给出：DAG 位置 → 每个 skill 的 Purpose/Input/Output/Gate/关键规则 → 对应 `scripts/` → 组级 SOP → 检查清单 → 与总框架的对应。

---

## 3. 三条贯穿 19 个 skill 的硬纪律

1. **产物即证据**：每个阶段必须落文件，链靠文件证明，不靠承诺。`output-protocol.md` 定路径，`artifact-registry.md` 定生产者/消费者，`schemas/` 定字段。
2. **机械门优先**：`smoke_gate` / `s2_ladder_gate` / `s2_ablation_gate` / `claim_anchor_gate` / `doi_gate` / `citation_support` / `figure_style_gate` / `check_figure_embedding` / `leakage_scan` / `validate_verdicts` 用 exit code 说话，模型读 verdict 而不是重推规则。
3. **回退带预算且改状态**：L1–L13 全登记在 orchestrator，3 轮 fallback（按失败类型）、PIVOT ≤2、BA 全局 ≤2、KILL 必须先有 `KILL_ARGUMENT.json` 且默认人工确认。

---

## 4. 与另外三块的关系

```
meta-skills (8)           → 横切能力，见 01/02/03 批
shared-references (49+23) → 共同法条，见 04 批
orchestrator (1)          → 分发/门/回退/状态，见 05 批
support (19)              → 本批：每个阶段的实际执行者
scripts (33)              → 机械判定器，被以上所有层调用
```

完整调用顺序见 [05-orchestrator/auto-pipeline-guide.md](../05-orchestrator/auto-pipeline-guide.md) §2 与 [APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) §7。

---

## 5. 阅读建议

1. 先读 orchestrator 指南建立 26 节点全局；
2. 再按你负责的阶段读本目录对应分组；
3. 写 verdict 时对照 [04-shared-references/schemas-guide.md](../04-shared-references/schemas-guide.md)（**注意 `INVARIANT_CHECK` 用 `overall_verdict`、`REVIEW_LEDGER` 是单对象、`EVALUATION_REVIEW` 与 `LEAKAGE_SCRUB` 的枚举不是 6 态**）；
4. 遇到散文与脚本冲突，以 `scripts/` 为准并记成 known gap。
