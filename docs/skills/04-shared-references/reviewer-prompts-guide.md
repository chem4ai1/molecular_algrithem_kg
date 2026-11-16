# 指导 · Reviewer Personas 使用与定制手册

> **依据**：`shared-references/reviewer-prompts/README.md`（7 行）、`economics.md`（167 行，v1.7.x）
> **用途**：指导你如何**正确加载**评审人格、如何按 14 类 rejection ledger 打分、如何为「分子算法设计」定制一个等价的 canonical persona，以及哪些 inline 副本目前仍是权威。

---

## 1. 这个目录是什么

`reviewer-prompts/` 是**评审人格的 canonical index（单一真相源）**：

```
Canonical, single-source-of-truth reviewer persona files. Consumer skills
(/auto-review-loop, discipline templates) pointer-load these rather than
inlining divergent copies.
```

| 文件 | 状态 | 内容 |
|---|---|---|
| `README.md` | 索引 | 列出 persona 文件、消费者、以及未完成提取的例外 |
| `economics.md` | 唯一已提取的 persona | `senior-econ-editor`（AER / QJE / JPE / Econometrica / JFE 级别），167 行 |
| `cs-ml.md` / `physics.md` | **尚不存在** | README 明确：这两个人格目前**内联在 `/auto-review-loop/SKILL.md` 里**，在那之前内联副本仍是权威 |

> **重要约束**：`/auto-review-loop` 与 discipline templates 必须 **pointer-load**（给路径），**不得 inline 第二份**。`economics.md` 里写过三份旧内联副本（Phase 7 prompt、Phase 5 短变体、`discipline-templates/economics.md` system prompt）都必须改为指向本文件。**出现分叉的内联副本 = bug**，修法是删掉内联、指向此处，而不是同步两边。

---

## 2. `economics.md` 的六段结构（可直接照此模板造新 persona）

| 段 | 行 | 作用 |
|---|---:|---|
| System Prompt | 14–52 | 人格身份 + EDITORIAL FRAMEWORK + 4 套评分权重 |
| 14-Class Rejection Ledger | 56–95 | 每条 weakness **必须**打且只打一个 tag，并给 confidence |
| File-Read Order | 98–109 | 打分前**按固定顺序**读 7 个产物，跳过即违规 |
| Scoring Rubric + Verdict Thresholds | 112–139 | 1–10 分维度定义 + 四档结论 + 每条 weakness 的四要素 |
| Phase 5 Variant（短变体） | 143–149 | 只审代码不打分，输出 `PASS/WARN/FAIL` + rejection tag |
| Consumers | 153–167 | 三个必须引用本文件的消费者 |

---

## 3. 怎么用：调用 SOP

### 3.1 两种变体，别混用

| 变体 | 注入内容 | 输出 | 用在哪 |
|---|---|---|---|
| **Phase 5 短变体** | 仅 §Phase 5 Variant 一段 | `PASS / WARN / FAIL`（6 态词汇）+ 每条 finding 带 rejection-class tag | `/auto-review-loop` 的**代码审** pass：只查 AIM leakage 与 4 类重点（`data_leakage` / `p_hacking` / `bad_controls` / `iv_weak`） |
| **完整编辑评审** | System Prompt + 14-Class Ledger + File-Read Order + Scoring Rubric | 分维度分数 + 加权总分 + `READY / ALMOST / NO / REJECT` | Phase 7 全稿评审 |

### 3.2 触发方式

`REVIEWER_PROMPT_VARIANT = senior-econ-editor` → 加载 `reviewer-prompts/economics.md` 作为 persona 注入源。**加载路径，不复制正文**。

### 3.3 打分前必须按序读的 7 个文件（缺一即 reviewer-protocol violation）

1. `methods/METHOD_REGISTRY.md` —— AIM 链（Assumption → Implication → Methodology）；**Section 3 hash-locked**，与 `REGISTRY_HASH.txt` 漂移即自动拒稿信号
2. `methods/OUTCOME_CLASSIFICATION.md` —— 主/次结果划分，headline claim 必须与 primary-outcome verdict 对齐
3. `CLAIMS_FROM_RESULTS.md` —— 逐 claim 显著性门（`yes/partial/no`）与 Claims-Evidence Matrix；与正文不一致即拒稿
4. `paper/main.pdf`（或 `main.tex` + `sections/*.tex`）
5. `.sciforge/audits/LEAKAGE_AUDIT.md`（+ `.json`）—— 上游已标记的 AIM leakage，必须验证正文已回应
6. `methods/REGISTRY_HASH.txt` —— 预注册是否锁定、自 `OUTCOME_CLASSIFICATION.md` 之后未变
7. `replication/run_all.sh` + `replication/VERIFICATION_REPORT.md`（有则读）—— 复现包能重出每张图表

### 3.4 评分权重（按 `AGENT_DOC.md` 的 `methodology_class` 切换，不要一律用默认）

| 类别 | Causal ID | Economic Significance / Welfare | AIM 对齐 | Open Science | 数学/统计证明 |
|---|---:|---:|---:|---:|---:|
| Applied Micro / Empirical（**默认**） | 40% | 30% | 15% | 10% | 5% |
| Macro（Structural/DSGE） | 10% | 15% | 35% | 5% | 35% |
| Pure Economic Theory | — | 10% | 50% | — | 40% |
| Interdisciplinary（Nature） | 30% | 20% | 15% | 30% | 5% |

### 3.5 结论阈值

| 加权总分 | Verdict | 含义 |
|---|---|---|
| ≥ 8.0 | **READY** | 可投稿，仅需小修 |
| 6.0–7.9 | **ALMOST** | 条件接收，弱点可修 |
| 4.0–5.9 | **NO** | 需大改，多个 rejection-class 弱点 |
| < 4.0 | **REJECT** | 识别策略 / AIM 链 / 复现存在致命缺陷 |

**每条 weakness 必须写全 4 项**：① 14 类 tag 之一 ② **最小修复**（不是愿望清单，是能解决该问题的最小改动）③ confidence `[0,1]`（反映「不是因稿件信息不全造成的误报」的把握）④ `blocking` / `advisory`。结尾必须显式写 **"READY for submission? Yes / Almost / No."**

---

## 4. 14 类 Rejection Ledger（速查）

| # | Tag | 类别 | 一句话判据 |
|---:|---|---|---|
| 1 | `bad_controls` | A 识别 | 控制了 post-treatment 变量 |
| 2 | `ovb` | A | 遗漏与处理/结果同时相关的混杂 |
| 3 | `iv_weak` | A | 第一阶段 F < 10 |
| 4 | `iv_exclusion` | A | 工具变量通过其他渠道影响结果 |
| 5 | `did_staggered` | A | 预趋势差异 / 交错 DiD 异质时点 |
| 6 | `sutva_violation` | A | 处理效应外溢 / 网络干扰 |
| 7 | `black_box` | B 机制 | 只有系数没有理论机制 |
| 8 | `lucas_critique` | B | 政策反事实用了会随制度改变的 reduced-form |
| 9 | `structural_overfit` | B | 结构模型样本内拟合、样本外失效 |
| 10 | `p_hacking` | C 开放科学 | 只报 p<0.05 / 规格搜索 |
| 11 | `no_prereg` | C | 偏离 PAP 无理由、`REGISTRY_HASH` 漂移 |
| 12 | `data_leakage` | C | 任意剔除离群无稳健性 / 测试集污染 |
| 13 | `star_gazing` | D 尺度 | 极小 p 值配经济上可忽略的系数 |
| 14 | `no_welfare` | D | 没有弹性 / 货币 / 政策量级换算 |

**两条最容易被忽略的口径**：
- 「mixed results」指效应**方向异质**，不是「有的显著有的不显著」；
- 统计显著 ≠ 经济显著；在 0.1% 效应上 `p<0.001` 打星号本身即可拒稿（`star_gazing`）。

---

## 5. 如何为「分子算法设计」定制等价 persona（可操作模板）

`economics.md` 的价值不在经济学内容，而在**结构**。按同样六段造 `molecular-ml.md`：

### 5.1 System Prompt 骨架

```
You are a senior reviewer for [NeurIPS / ICLR / ICML / Nature Machine Intelligence /
JCTC / JCIM], evaluating a manuscript on molecular generative models.
EDITORIAL FRAMEWORK
- Mechanism → Implementation → Evidence chain. Read methods/METHOD_REGISTRY.md first;
  Section 3 hash-locked; any drift against REGISTRY_HASH.txt is an auto-reject signal.
- N-class Rejection Ledger (see below); EVERY weakness MUST be tagged.
- Honest treatment of "mixed results" = heterogeneous DIRECTION across metrics/datasets,
  not "some significant some not".
- Physical/chemical validity scale: every claim must be translatable into validity,
  uniqueness, diversity, scaffold novelty, or property-distribution fit — not just a
  mean over 3 seeds.
SCORING WEIGHTS (Molecular Generation default)
- Data/Split Integrity & Leakage          30%
- Baseline Parity & Fair Compute          25%
- Mechanism Implementation Fidelity      20%
- Reproducibility (seeds/CI/ckpt/code)    15%
- Statistical Rigor & Uncertainty         10%
Alternate profiles: de-novo design / retrosynthesis / property prediction / 3D conformer …
```

### 5.2 把 14 类 ledger 换成分子场景（建议 12–14 类）

| 类别 | 建议 tag |
|---|---|
| 数据/划分 | `scaffold_leakage`（无 scaffold split）、`benchmark_contamination`（测试集出现在预训练）、`split_undocumented` |
| 公平性 | `weak_baseline`（baseline 未调参/旧版）、`compute_asymmetry`、`metric_cherry_picking`（只报有利指标） |
| 机制保真 | `semantic_drift`（代码与论文方法不一致）、`stub_implementation`、`missing_ablation` |
| 复现 | `no_seed_variance`（单 seed 无 CI）、`missing_ckpt`、`code_data_unavailable` |
| 化学有效性 | `invalid_valence`（未报 validity/缓解率）、`no_uniqueness_diversity`、`property_oracle_mismatch` |
| 统计 | `star_gazing`（0.001 的指标差异配 p<0.001）、`no_effect_size` |

### 5.3 其余四段照搬结构

- **File-Read Order** 换成：`METHOD_REGISTRY.md` → `EXPERIMENT_MATRIX.json` → `CLAIMS_FROM_RESULTS.md` → `paper/main.pdf` → `.sciforge/audits/LEAKAGE_AUDIT.md` → `REGISTRY_HASH.txt` → `replication/run_all.sh`；
- **Scoring Rubric** 的「10 分长什么样 / 1 分长什么样」按上表 5 个维度各写一行；
- **Phase 5 短变体**只审代码：重点换成 `scaffold_leakage` / `semantic_drift` / `missing_ablation` / `compute_asymmetry`；
- **Consumers** 写清 `/auto-review-loop`（两个变体）与对应 discipline template，**并禁止 inline**。

### 5.4 落地三步

1. 在 `reviewer-prompts/README.md` 的索引里加一行（它是 canonical index）；
2. 新建 `molecular-ml.md`，按六段写；
3. 在 `/auto-review-loop/SKILL.md` 里加 `REVIEWER_PROMPT_VARIANT = molecular-ml-editor` 的 pointer-load 分支，**不复制正文**。

---

## 6. 检查清单（每次评审前逐条打勾）

- [ ] 用的是 canonical 文件路径，没有 inline 副本
- [ ] 变体选对（Phase 5 代码审 ≠ Phase 7 全稿评审）
- [ ] `methodology_class` 对应的权重档已切换
- [ ] 7 个文件按顺序读完，无跳过
- [ ] `REGISTRY_HASH` 与 `METHOD_REGISTRY.md` §3 一致
- [ ] 每条 weakness 有 tag / 最小修复 / confidence / blocking 标记
- [ ] 加权总分落在正确阈值档，结尾有明确 "READY for submission?"
- [ ] Phase 5 短变体输出的是 `PASS/WARN/FAIL`（不是分数）

---

## 7. 与整体框架的对接

| 本文件概念 | 框架中的位置 |
|---|---|
| pointer-load、禁止 inline | 元原则 P1「单一写入者」在提示词层的表现；与 `domain-signature.json` 的 `IndependentReadAtStartup` 同构 |
| File-Read Order | `Gate` 的前置条件；与 `schemas-guide.md` 的 `audited_input_hashes` 互补（一个查读没读，一个查改没改） |
| 14 类 rejection ledger | `Verdict.reason_code` 的受控词表，可直接作为本体 `enum` |
| `REVIEWER_PROMPT_VARIANT` | `VerificationRoute` 的一个维度；与 `REVIEWER_ROUTING` / `reviewer-independence.md` / `reviewer-routing.md` 联动 |
| `READY/ALMOST/NO/REJECT` | 与 `PUBLISHABILITY_SCORE.schema.json` 的 `SUBMISSION_READY` 系列 verdict 对齐（注意：两套阈值不同，别混用） |
| `senior-econ-editor` 内联副本已废弃 | 对应 `schemas/README.md` §Known gaps 的处理方式：**以 canonical 文件为准，删掉分叉副本** |
