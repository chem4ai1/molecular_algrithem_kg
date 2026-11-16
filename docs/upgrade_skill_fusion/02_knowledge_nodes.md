# 02 · 可融入知识点库（26 SKILL + shared-references）

> 6 族 30 个知识点。每条标**原始源文件与行号**（根目录
> `/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/`），并给出可直接搬进 prompt 的指令句。
> 覆盖 **17 个 support skill**（用户强调不只看 meta-skills）+ 8 meta + orchestrator + shared-ref 契约。

---

## K-A · 证据分级与联合置信（解决 Q01/Q02/Q03）

| ID | 知识点 | 来源 | 可搬指令句（原文） |
|---|---|---|---|
| K-A1 | **3-fidelity claim ladder**：symbolic→`proven`、numerical→`supported`、qualitative→`suggests/consistent with`；禁 `supported/proven` 越级 | `support/result-to-claim/SKILL.md` L~110-160 | "Block unsupported 'supported'/'proven' language." |
| K-A2 | **TDAL 4 维乘积**：`joint = T × D × A × L`，维内加权、维间相乘；任一维 0 → 至多 WEAK | `shared-references/domain-adaptation-contract.md:5,79` | "Confidence is not a single number... No single dimension may be silently inflated or dropped." |
| K-A3 | **最弱维必报** + 写进 Limitations；`missing_inputs` → STRONG 降 MODERATE；joint 不四舍五入 | 同上 `:213,257,283` | "`weakest_dimension` MUST always be reported; the paper's Limitations section MUST name it explicitly" |
| K-A4 | **verdict→动词映射**：STRONG `We establish/demonstrate`；MODERATE `We provide evidence for`；WEAK 只能 `preliminary/suggests`；UNSUPPORTED → BLOCK | 同上 `:205-208,267` | "Do NOT claim — reframe as 'preliminary' / 'suggests'" |
| K-A5 | **提升≠伪造证据**：最多 3 轮 uplift，固定机制顺序，`UNSUPPORTED` 三轮后 BLOCK | `shared-references/confidence-uplift.md:291` | "UNSUPPORTED after Round 3 → BLOCK. No amount of uplift drags UNSUPPORTED to publishable." |
| K-A6 | **多保真度**：toy / numerical / qualitative 分层，不得用低 fidelity 结果支撑高等级 claim | `shared-references/multi-fidelity-evaluation.md` | 与 K-A1 联合使用 |

## K-B · 反幻觉、引用与证据溯源（解决 Q15–Q18）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-B1 | **声明三源追溯**：结论只能来自 verified derivation / verified citation / 显式假设+reasonability score；无源即 FANTASY | `shared-references/fantasy-prevention.md:5,42-46` | "A labeled conjecture is valuable; an unlabeled one is dangerous." |
| K-B2 | **5-Gate 分级闸门**：推导/引用/假设/反例/数据可得性各 1 分；≤2/5 BLOCK 写作，3/5 强制 Limitations | 同上 `:98-104,116-118` | "Fantasy is not the same as wrong." |
| K-B3 | **引用三层校验**：EXISTENCE / METADATA / CONTEXT 独立判定，必须真实 web 查询；**wrong-context > typo** | `support/citation-audit/SKILL.md:91-99,243,326` | "soft-only 只软化句子不改 bib，但绝不残留指向幻觉文献的 \cite{X}" |
| K-B4 | **6 源分波检索 + 3 层反幻觉**，never skipped；broad wave 先出 `GAP_REPORT.md` 才允许打分 | `meta-skills/universal-retrieval/SKILL.md` | "MUST, never skipped（网络问题只降 WARN）" |
| K-B5 | **verbatim evidence**：标签必须附原文逐字短语，不得概括 | `shared-references/citation-discipline.md` + 本框架 `label_l2_gemini.py` | "Every label MUST quote a verbatim phrase from the text as evidence." |
| K-B6 | **受控词表 + proposals 队列**：ID 只能取自词表，新概念进 proposals 不写库 | `meta-skills/domain-learner` + 本框架抽取 prompt | "Never invent a class or property IRI." |
| K-B7 | **从零学习不硬编码领域表**，文献太薄写 `unknown — defaulting to conservative` | `meta-skills/domain-learner/SKILL.md` | "Do NOT pre-define domain characteristics." |

## K-C · 强制证伪、逻辑与锚点冻结（解决 Q06–Q10）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-C1 | **先杀后证**：强制证伪，先试推翻 idea 再试证明；证伪永不跳过 | `support/adversarial-falsification/SKILL.md:16,247,250` | "Forced falsification — first try to kill the idea, then try to prove it" / "Never skip falsification." |
| K-C2 | **verdict 三档 + 阈值**：`assumption_health ≥6` 且无反例 → SURVIVE；4–6 → WEAKENED；<4 → FALSIFIED；数据 <50% → DATA_BLOCKED | 同上 `:64-71,205-208,233-235` | "Search for contradiction, not confirmation. The default should be skepticism." |
| K-C3 | **逻辑客观门**：零 FATAL/CRITICAL + 假设台账逐项 discharge + 关键引理反例扫描；3 轮不收敛 → `NOT YET COHERENT` | `support/logic-verification/SKILL.md:52-58,194-198,268-272` | 不静默放行 |
| K-C4 | **结构泄漏 Type I / Type IV**：结论不由假设推出 / 数值验证跑出假设成立 regime 仍算通过 → 硬阻断写作 | `support/leakage-audit/SKILL.md:38,85,110,192` | FAIL 一律 block `/paper-writing` |
| K-C5 | **问题锚点双冻结**：Q-id + SHA256 问题段落写 `PROBLEM_HASH.txt`，专防「Q-id 没变但题目被悄悄改写」 | `support/invariant-check/SKILL.md:53,127-130` | 换题只能显式 swap idea 重跑 |
| K-C6 | **自评最不可靠**：能文件解析的判据必须 deterministic，语义判据必须 cite `file:line`；下游 **CONSUME** 上游 verdict 不重算 | `support/quality-gate/SKILL.md:37,56,167-169,236-242` | "The agent's own assessment of its work is the least reliable signal." |
| K-C7 | **6 态 verdict + 最差值传播**：`PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR`，`overall` 取最差 | `auto-pipeline/SKILL.md` + `support/invariant-check/SKILL.md:76-85` | 禁止为了清 pending 伪造 verdict |
| K-C8 | **边界逐字复述硬约束** + 拦截「我完成了」声明（PASS 但字段不全 → 降 IN_PROGRESS） | `orchestrator/auto-pipeline/SKILL.md` §3 | "verbatim, not summary" |
| K-C9 | **角色隔离**：attacker / adjudicator / citation reviewer 一律 fresh thread、零上下文、不得携带历史 fix list；verdict 由代码算 | `support/kill-argument/SKILL.md:63,88,160,265,311` | 禁止被审方自评顶层 verdict |

---

## K-D · 实验矩阵、预注册与阴性结果（解决 Q04/Q19–Q21）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-D1 | **预注册 + hash lock**：方法/实验矩阵/评估协议在看结果前锁定；Section 3 SHA256 + 强制人工批准，agent 不得 self-approve | `support/method-registry/SKILL.md:33,43,110,210` | "After derivations are run (post-hoc registration is research fraud)" |
| K-D2 | **实验矩阵下限**：≥1 主实验、≥3 baselines、≥2 消融组、≥1 超参×≥3 点、**≥3 seeds mean±std**；lite 不得整类删除 | 同上 `:126-130,137-138` | pilot 结果不得进正文 |
| K-D3 | **toy first**：1–10% 规模、`scale_ratio=0.1`、`timeout_toy=300s`；`RESULT.json` 必填 `core_claim_validated`+`seeds_used≥3`；FAIL 绝不进 full | `support/experiment-execution/SKILL.md:13,60,87-93,289,318` | "Never invest full compute in an unvalidated idea. Toy first, gate check, then full." |
| K-D4 | **KILL/PIVOT 双条件**：需「显著 + ≥2 seeds 可复现」，PIVOT ≤2 且必须换方法而非调超参 | 同上 `:323-324,330,334-335` | 禁「调参硬救」与「把阴性 toy 包装成 honest findings」 |
| K-D5 | **严格消融**：5–6 个组件计划，`GOOD iff strictly better`，平局 REFINE；full set 同协议、**不做 proxy ablation** | `support/ablation-planner/SKILL.md:48,79-81` | "Ablations run on the full set with the main arm's protocol" |
| K-D6 | **阴性结果即发现**：消融没变差 = 组件冗余，写进论文而非静默丢弃；「ties never count as wins」「No reproduction = no ladder」 | 同上 `:80-81`；`support/experiment-ladder/SKILL.md:25,37` | "an ablation that fails to hurt is a finding" |
| K-D7 | **经验回放**：每个 FAIL/KILL/代码错误带 `lesson`+`evidence` 进 `LESSONS.json`（4 类 key 齐全），下轮作 `avoid` 硬排除；只有 `status=PASS` 可回流 | `shared-references/experience-replay-contract.md:46,60-63`；`domain-adaptation-contract.md:298-305` | 防幻觉结果自我强化 |
| K-D8 | **后台 dispatch 不 busy-wait**：>5min 派后台，边界读 verdict；未完成标 "experiment pending" | `orchestrator/auto-pipeline/SKILL.md` §后台 | 与本框架 AiZynthFinder 离线缓存同构 |

## K-E · 领域自适应与证据规范（解决 Q11–Q14）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-E1 | **`evidence_norm_profile`**：sample_size / control_design / effect_reporting / negative_result / exemplar_venues，每个带 `learning_basis` | `meta-skills/domain-learner/SKILL.md` v6.0 | 文献太薄 → `unknown — defaulting to conservative` |
| K-E2 | **频次化先验**：`method_frequencies` / `failure_frequencies` 把定性印象变权重数值 | `meta-skills/idea-discovery/SKILL.md` + learner | 门禁阈值应由这里归纳，不是拍脑袋 |
| K-E3 | **SingleWriter + IndependentReadAtStartup + PointerLoad**：唯一写入者、下游启动时各自读、只传路径不内联正文 | `domain-learner` + `auto-pipeline` §Domain Signature Propagation | "pointer-load, do NOT inline" |
| K-E4 | **置信门 + 降级**：`learning_confidence ≥0.7` 才应用；失败 → `general` + WARN，绝不静默 | `domain-learner/SKILL.md`；`tdal_compute.py` A 维 | `A = 0.8×lc + 0.2×0.5`，缺输入 → STRONG 降 MODERATE |
| K-E5 | **spec_hash 锁**：全局配置带哈希，下游读取校验，防长链路悄悄改写 | `docs/skills/APPLICATION_ONTOLOGY_FRAMEWORK.md` §11.3 | 对应本框架 `failure_prior_index.json` |
| K-E6 | **领域失败模式注入证伪**：learner 学出的 `common_failures` 直接喂 `adversarial-falsification` | `shared-references/domain-failure-modes.md` | 让「先杀后证」有领域针对性 |

## K-F · 写作质量、评审与交付（解决 Q05/Q22–Q24）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-F1 | **AI 腔黑名单 + 零道歉 + hedge 必带界**：禁 `It is worth noting that`/`leverage`/`delve into`；禁 `we apologize`/`future work will fix`；**每个 hedge 必带 range/N/CI/regime**，hedge-to-claim ratio >1.0 重写 | `shared-references/writing-principles.md:27-37,74-85` | "every hedge must carry a bound" |
| K-F2 | **每段 ≥1 具体锚点**（数字/引用/符号/图表号）；Abstract 5 句含具体数字；每个 claim 有 `\cite{}` 或 `\cref{}` | 同上 `:41,201,203` | 对应本框架 Q05 |
| K-F3 | **泄漏 scrub**：8 类正则 A–H + I（工具名/伪造作者），re-grep 零命中才 PASS；Title ≤20 words；Abstract 无引用；禁 `\cite{TODO}` | `support/paper-writing/SKILL.md:167,171,231,243-256` | "a reviewer ... immediately desk-rejects as an AI pipeline dump" |
| K-F4 | **阴性结果只进 Limitations**（3–6 条，每条 = regime/boundary + observable consequence + 可选测量），**永不列为 contribution** | `writing-principles.md:87-88`；`experience-replay-contract.md:60-63` | flat register、无道歉 |
| K-F5 | **评审独立性**：fresh thread、只读最终 artifact、禁带作者推理/既往评审/修复记录；`effective_score = min(raw, blind-spot cap)` | `shared-references/reviewer-independence.md:20-24`；`support/auto-review-loop/SKILL.md` | 防「假 ready」 |
| K-F6 | **Anti-shrinkage**：被批评只准实质变更（experiment_redesign / PIVOT / KILL），wording-only 轮无效；3 轮无实质响应强制 KILL | `support/rebuttal/SKILL.md`；`auto-review-loop` | "round_invalid" |
| K-F7 | **quality-gate 三道门**：Stagnation / Quality Floor (QF-G1~G9) / Self-Deception (SD-G1~G5)；G1–G7 全 PASS 才放行，FAIL 阻塞写作 | `support/quality-gate/SKILL.md:28-31,161-171,205,236-242,290-296` | hard gate，不接受自评 PASS |
| K-F8 | **publishability 6 维评分 + verdict tiers**，go/no-go 在 citation-audit 之后 | `support/publishability-score/SKILL.md` | 与 K-A 联合 |
| K-F9 | **编译零 warning**：elsarticle 零 error 零 warning；≥1 图，12 种图表类型 + 布局契约 | `support/paper-compile/SKILL.md`；`meta-skills/unified-plotting/SKILL.md` | 本框架 `compile.sh` 已有雏形 |

## K-G · 编排与状态（横切 Q06–Q10）

| ID | 知识点 | 来源 | 可搬指令句 |
|---|---|---|---|
| K-G1 | **唯一入口编排器**：26 节点 DAG，自己不执行研究，只分发 / 读 verdict / 套门 / 回退 / 恢复 | `orchestrator/auto-pipeline/SKILL.md:5` | "It does not do research." |
| K-G2 | **每个边界固定 5 件事**：逐字复述硬约束、verdict 校验、漂移检测、拦截「我完成了」、重写三状态文件 | 同上 §3 | `RUNSTATE.json` / `PIPELINE_VERDICT_SUMMARY.md` / `RUN_BUDGET.json` |
| K-G3 | **机械判定走工具**：`sciforge_audit.py` 一次调用硬退出码，模型读 verdict 不重新推导规则 | 同上 §3 + §8 | "Mechanical verdicts via tool, not prose" |
| K-G4 | **MUST/OPTIONAL/ROUTED + 人工检查点**：MUST 失败 3 轮 fallback → BLOCKED 交人；ROUTED 合法缺失写 `na_verdicts` 不伪造 | 同上 Phase Mode Table | 总 verdict = 最差值 |
| K-G5 | **预算双护栏**：超限 BLOCKED，且 `budget_underuse`（<0.5×上限却宣布完成）也 WARN + 逐条解释未尝试路线 | 同上 §预算 | "便宜可以，但探索没做完就宣布完成不行" |

---

## 知识点 → 问题 速查

| 问题组 | 主要知识点 |
|---|---|
| A 证据声明 Q01–Q05 | K-A1~A6, K-F1~F2 |
| B 编排门控 Q06–Q10 | K-C1~C9, K-G1~G5 |
| C 领域规范 Q11–Q14 | K-E1~E6 |
| D 反幻觉引用 Q15–Q18 | K-B1~B7 |
| E 实验消融 Q19–Q21 | K-D1~D8 |
| F 写作评审 Q22–Q24 | K-F3~F9 |

> **精度提醒（来自精读）**：`logic-verification` 自称 6 维/20 类但表格实列 21 条；
> `adversarial-falsification` 的 6 维 / "5 attack vectors" / `max_attack_vectors=5` 并存。
> **搬进 prompt 时按阶段名显式枚举，不要照抄计数** —— 否则会复现本框架 Q07 那类静默不一致。
