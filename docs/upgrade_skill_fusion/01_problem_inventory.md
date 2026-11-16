# 01 · 待解决问题清单（对照本框架实测缺陷）

> 24 个问题分 6 组。每条都挂**本框架真实发生过的现象**，不是通用 best practice 罗列。
> 编号 Q-xx 在 `03_prompt_mapping.md` 中一一对应知识点与 prompt 改造。

---

## A 组 · 证据与声明（Q01–Q05）

| ID | 问题 | 本框架实测证据 | 若不解决的后果 |
|---|---|---|---|
| Q01 | **SA score 被当成任务目标**，指标代理与真实目标混淆 | similarity-RAG 删掉羰基氧片段拿到更好 SA（−0.422 vs −0.325），但 `anchor_violation 0.188`、手性 2→0 | 论文会声称「更可合成」，实际毁掉药效团；RL 会收敛到破坏性编辑 |
| Q02 | **claim 无证据分级**，动词与证据强度脱节 | 论文标题/结论写 "raises hard-constraint success"，但 48 次 API 是 16 分子、端到端只有 8 分子，且 `edit_validity` 更低 | 过度声称；审稿人一眼看出 `validity` 反例 |
| Q03 | **置信度是单个 p 值**，无多维分解 | 现有报告只给 p=0.0156 / p=0.0078；`validity` 低、SA 差、样本小这些最弱维没有被量化进总置信 | 无法回答「整体结论有多可信」，最弱环节被平均掩盖 |
| Q04 | **阴性结果没有统一纪律** | LoRA 与 base 产物逐条一致、18 批 GRPO 第 1 批即饱和（17 批空转）、`constraint_recall` 本体组更低 —— 这些散落在报告不同角落，没有统一 ledger | 要么静默丢弃，要么被包装成「边界贡献」 |
| Q05 | **样本量与长尾不透明** | 24 类问题里 P21 只有 4 例、P02 有 1284 例；端到端 8 分子；报告只给均值没给 per-class N 与 CI | micro 平均掩盖长尾；p 值不稳 |

## B 组 · 编排与门控（Q06–Q10）

| ID | 问题 | 本框架实测证据 | 后果 |
|---|---|---|---|
| Q06 | **没有统一 verdict 链** | `validate_edits`、`reward_components`、SHACL、owlrl 各自判定，但无 `PASS/WARN/FAIL/BLOCKED/ERROR` 统一状态，也无 `overall = min(所有门)` | 某个门挂了，下游仍继续 |
| Q07 | **模型自评被当真**（三次实锤） | ① `FM_` 前缀不匹配让 `requiresFailure` 加分从未生效；② `constraint_recall` 数 reasoning 文本，工具链天然吃亏；③ S1 probe 首版 `score=None` 异常被 `except` 吞成 0，报出假「无分歧」 | 「没效果」和「测量失效」分不清 |
| Q08 | **边界不复述硬约束** | 多轮工具链每步都靠模型记住「不能删保护原子」，没有 verbatim 复述机制；`get_solution_pack` 的契约只在某一轮返回里出现一次 | 长链路漂移 |
| Q09 | **无饱和 / 分歧度门禁** | 18 批全量 GRPO，第 1 批后 loss 恒定 −1.8074、p_correct 全 1.0，后 17 批空转约 26 分钟 | 算力浪费，且把「饱和」误读成「训练完成」 |
| Q10 | **无问题锚点冻结** | 3,483 分子标注按 case_id 组织过，早期 3,272 案例其实只覆盖 705 分子，曾存在 train/test 泄漏风险 | 评测结论不可信 |

## C 组 · 领域与证据规范（Q11–Q14）

| ID | 问题 | 实测证据 | 后果 |
|---|---|---|---|
| Q11 | **门禁阈值是拍脑袋的** | `COMPREHENSIVE_TEST_PLAN.md` 的 G1–G17 阈值（Spearman≥0.3、std>0.1、heldout≥0.85）没有出处 | 无法说明「为什么是 0.3 不是 0.5」 |
| Q12 | **缺 evidence_norm_profile** | 论文没规定本领域「几个 seed / 要不要 scaffold split / 是否必须报 mean±std / 阴性结果能否发表」；实际实验常单 seed、无 CI | 实验矩阵设计无依据 |
| Q13 | **全局配置无单一写入者 + 哈希锁** | `failure_prior_index.json` 由 `merge_l2.py` 写，但 `query_ontology` 直接读；没有 `spec_hash` 校验，词表升级后缓存可能静默过期 | 长链路里配置被悄悄改写 |
| Q14 | **词表正文内联进 prompt** | `ontology_grounded_extraction.py` 把整份受控词表 + 17 条 SMARTS 序列化进每次 prompt；`classify_corpus.py` 同样 | 上下文膨胀、易被压缩截断，且改词表要改 prompt |

## D 组 · 反幻觉与引用（Q15–Q18）

| ID | 问题 | 实测证据 | 后果 |
|---|---|---|---|
| Q15 | **不可观测类型曾被 LLM 硬猜** | L2 十类（P04 路线 / P15-17 蛋白 / P18-19 活性毒性 / P20/21/24 度量）从 SMILES 物理不可观测；初版分类器让 LLM 从 SMILES 猜，D1 全空、12/20 无 JSON | 幻觉监督 |
| Q16 | **抽取可能发明 TBox 外 IRI** | 已防住（6/6 零发明），但只靠一句 prompt 约束，没有 proposals 队列 + 人工复核的机器门 | 本体污染 |
| Q17 | **引用无三层校验** | `paper/references.bib` 16 条，只做了 LaTeX 编译无 undefined citation；没查 EXISTENCE / METADATA / CONTEXT | 引了存在但不支持该句 |
| Q18 | **evidence 不要求逐字** | 只有 `label_l2_gemini.py` 要求 verbatim（实测 0.9939）；其他 prompt 允许模型概括 | 无法回溯证据 |

## E 组 · 实验、消融与失败处理（Q19–Q21）

| ID | 问题 | 实测证据 | 后果 |
|---|---|---|---|
| Q19 | **无预注册 / hash lock** | transform 从 5 扩到 13、覆盖率 34.7%→92.5% 是**看到结果后**改的；方法、指标、切分没有在看结果前锁定并哈希 | 事后挑 metric 的嫌疑 |
| Q20 | **消融不完整** | 只做过「关掉标注真值打分 / LoRA」的零星对比，没有 5–6 个组件的严格消融，也没有 `strictly better 才算 GOOD` 规则 | 无法归因提升来自哪一层 |
| Q21 | **KILL/PIVOT 无双条件** | GRPO 发现饱和后只是记录，没有触发「显著 + ≥2 seeds 可复现」的正式 KILL 论证 | 失败方向被反复重试 |

## F 组 · 写作与评审（Q22–Q24）

| ID | 问题 | 实测证据 | 后果 |
|---|---|---|---|
| Q22 | **无界 hedge / AI 腔** | 报告里大量「可能」「有待验证」但无数值界；`acl_latex.tex` 未做黑名单扫描 | desk reject 风险 |
| Q23 | **评审不独立** | 目前所有结论由同一套脚本 + 同一模型自评，没有 fresh-thread reviewer、没有盲审第二遍 | 自我印证 |
| Q24 | **写作只有编译门禁** | `compile.sh` 只验证 PDF 能生成、无 undefined citation；没有 quality-gate / publishability-score / auto-review-loop | 格式合格但论证不合格 |

---

## 优先级（按「修完能解锁多少」）

1. **Q07 / Q09 / Q06**：直接决定后续所有实验结论是否可信（元问题）
2. **Q01 / Q02 / Q03**：决定论文主结论站不站得住
3. **Q11 / Q12 / Q19**：决定测试方案与实验矩阵有没有依据
4. **Q15 / Q16 / Q17 / Q18**：反幻觉，已有部分防护，需固化成 prompt 契约
5. **Q04 / Q20 / Q21 / Q22–Q24**：写作与经验回放学处理
