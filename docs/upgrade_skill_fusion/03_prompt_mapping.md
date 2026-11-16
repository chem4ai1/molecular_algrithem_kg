# 03 · 完整对照表：问题 → 知识点 → 现有 prompt → 改造后 prompt → 验收

> 本框架的 8 个 prompt 触点逐一改造。每条给出**要新增的具体指令句**（可直接复制），
> 不是泛泛的「应该更严谨」。「现状」列摘自真实代码常量。

---

## 总览矩阵

| Prompt 触点 | 代码位置 | 现状一句话 | 主要缺口 | 融入知识点 |
|---|---|---|---|---|
| P1 编辑生成 | `eval_pipeline.py:40` `SYSTEM` | 只规定输出格式与 9 种命令 | 无证据分级、无强制证伪、无 verdict 消费 | K-A1, K-C1, K-B5, K-D2, K-G3 |
| P2 本体抽取 | `ontology_grounded_extraction.py:47` `SYSTEM` | 已有受控词表 + proposals + verbatim | 无 spec_hash、无 pointer-load、无证据门 | K-E3, K-E5, K-B2, K-B6 |
| P3 L2 弱标签 | `label_l2_gemini.py:33` `SYS` | 已有 verbatim + 「不从结构推断」 | 无置信度、无 `unknown` 降级、无阴性纪律 | K-E1, K-B7, K-A4, K-F4 |
| P4 分类标注 | `classify_corpus.py:32` `SYS` | 已有 computed 优先 + `other` | LLM 仍被要求判 D2/D4；无 verbatim、无 proposals 门 | K-B1, K-B5, K-E3, K-C6 |
| P5 工具链 | `toolenv/env.py:18` `SYSTEM` | 已有 workflow + 硬约束规则 | 无边界逐字复述、无统一 verdict、无「拦截我完成了」 | K-G2, K-G3, K-C7, K-C8 |
| P6 GRPO 决策 | `toolenv/grpo_traj.py:30` `STATE` | 只有状态 + 规则 | 无分歧度/饱和门、无 KILL 论证 | K-C2, K-G4, K-D4 |
| P7 工具探测 | `toolenv/probe_qwen_toolcall.py:10` | 只列工具名 | 无 n_success/n_error、无证据指针 | K-C6, K-B3 |
| P8 论文写作 | `paper/acl_latex.tex` | 静态 LaTeX，`compile.sh` 只编译 | 无 claim ladder / TDAL / Limitations 最弱维 / 黑名单 | K-A2~A5, K-F1~F9 |

---

## P1 · 编辑生成 prompt（`eval_pipeline.py:40`）

**现状原文（关键句）**：
```
You are an expert medicinal chemist. Analyze the source molecule ... then propose
minimal chemically sound modifications. Output EXACTLY this format ...
```
只有角色 + 输出契约 + 9 种命令，**没有任何证据/证伪/置信约束**。

| Q | 知识点 | 来源 | **新增指令句（改造后 prompt 片段）** | 验收 |
|---|---|---|---|---|
| Q01 | K-A1 3-fidelity | `result-to-claim` | `Classify each claim by evidence fidelity: symbolic / numerical / qualitative. SA score and Tanimoto are numerical proxies, NOT proof of synthesizability. Never write "proven", "demonstrates", or "establishes" for a proxy.` | 输出含 `fidelity` 字段；`proven` 出现率 0 |
| Q02 | K-A4 verdict→动词 | `domain-adaptation-contract.md:205-208` | `If your overall evidence is WEAK or the sample is N<30, use only "suggests" / "preliminary"; reserve "We provide evidence for" for MODERATE.` | 人工抽检 20 条无越级动词 |
| Q01 | K-C1 先杀后证 | `adversarial-falsification/SKILL.md:16,247` | `Before emitting [EDITS], state ONE way this edit could FAIL (anchor deletion, stereocentre loss, valence error), then explain why it does not. Never skip this.` | 每条 `[REASONING]` 含 failure 段落，正则检出率 100% |
| Q18 | K-B5 verbatim | `citation-discipline` | `Every liability you identify MUST quote a verbatim phrase from the provided SourcePack as evidence; paraphrase is not evidence.` | `evidence_in_source` 命中率 ≥0.95 |
| Q03/Q05 | K-D2 报量 | `method-registry/SKILL.md:126-130` | `Report N, seeds/independent runs, and an uncertainty bound with any improvement claim. If N<30 or a single run, label the result "preliminary".` | 结果 JSON 必填 `n`, `seeds`, `bound` |
| Q07 | K-G3 verdict 消费 | `auto-pipeline` §3 | `Do not self-assess. Consume the machine verdict from validate_edits; if it is absent or ERROR, output ABSTAIN instead of edits.` | 无 verdict 时 ABSTAIN 率 100% |
| Q04 | K-F4 阴性纪律 | `writing-principles.md:87-88` | `If no admissible edit exists, say so explicitly with a reason_code; never fabricate an edit to appear productive.` | abstain 精度/召回同时报 |

**不改的部分**：`[REASONING]/[EDITS]` 格式、9 种命令、atom map 契约 —— 这些是与 `reconstruct_from_sequence` 的硬接口，改了会破坏回放。

---

## P2 · 本体抽取 prompt（`ontology_grounded_extraction.py:47`）

**现状原文（已经做得不错的部分）**：
```
You MUST output exactly ONE JSON object ... CRITICAL: every "id" field MUST be chosen
from the provided controlled vocabulary. Never invent a class or property IRI.
If you believe a genuinely new concept is needed, put it in the "proposals" array ...
Evidence must be a short verbatim phrase from the source text.
```
已含 K-B5 / K-B6。**缺的是配置层与门控层**。

| Q | 知识点 | 来源 | **新增指令句 / 结构调整** | 验收 |
|---|---|---|---|---|
| Q14 | K-E3 pointer-load | `auto-pipeline` §Propagation | **结构性改造**：不把整份词表序列化进 prompt，改为只传 `vocab_path` + `vocab_hash`；由工具在运行时读文件。prompt 改为 `Load the controlled vocabulary from {vocab_path} (sha256={vocab_hash}). Do not rely on any inlined list.` | prompt token 数下降 ≥40%；词表更新不改 prompt |
| Q13 | K-E5 spec_hash | `APPLICATION_ONTOLOGY_FRAMEWORK.md` §11.3 | `Your output MUST echo vocab_hash. If it does not match, return {"status":"STALE"} and nothing else.` | 哈希不符时 STALE 100% |
| Q16 | K-B2 5-Gate | `fantasy-prevention.md:98-104` | `Each extracted instance must have all five gates passed: derivation, citation, assumption, counterexample, data availability. If ≤2/5, move it to "proposals" instead of ABox.` | 归位后 SHACL 违规不来自 invented IRI（当前 7 条中抽取实例违规应为 0） |
| Q17 | K-B3 三层校验 | `citation-audit/SKILL.md:91-99` | `For every evidence source, state existence / metadata / context separately; a source that exists but does not support the sentence is a FAIL, not a typo.` | 输出含 `evidence_layers` 三元组 |
| Q06 | K-C7 verdict | `invariant-check/SKILL.md:76-85` | `Emit a machine verdict field per instance: PASS / WARN / FAIL / NOT_APPLICABLE / BLOCKED / ERROR. overall = the worst value.` | 每条记录有 verdict |

> 注意：本框架实测 **6/6 解析成功、零发明 IRI**，说明 P2 的现有约束有效；
> 改造重点是**别把有效约束撑爆上下文**（Q14），以及把「有效」变成**可机器验证的 verdict**。

---

## P3 · L2 弱标签 prompt（`label_l2_gemini.py:33`）

**现状原文**：
```
You extract evidence-backed problem labels from chemistry reasoning text.
Output ONE JSON object only. Every label MUST quote a verbatim phrase from the text.
Do NOT infer from molecular structure; if the text does not state it, do not label it.
```
已正确防住 Q15（不可观测类型）。实测 **696/705 成功、verbatim 0.9939**。

| Q | 知识点 | 来源 | **新增指令句** | 验收 |
|---|---|---|---|---|
| Q11 | K-E1 证据规范 | `domain-learner` v6.0 | `Attach learning_basis to the output: which label definitions and which seed evidence were used. If the evidence is too thin, write "unknown — defaulting to conservative" and emit no label.` | 每条输出含 `learning_basis`；薄证据 0 标签 |
| Q03 | K-A4 置信分级 | `domain-adaptation-contract.md:205-208` | `Emit confidence per label with a verdict tier: STRONG / MODERATE / WEAK / UNSUPPORTED. Labels from a single sentence are at most MODERATE.` | tier 分布可统计；无 STRONG 来自单句 |
| Q04 | K-F4 阴性纪律 | `experience-replay-contract.md:60-63` | `Emit unmentioned_types explicitly. Leaving a type out silently is a FAIL; every one of the 10 types must appear either in l2_labels or unmentioned_types.` | 10 类覆盖率 100% |
| Q07 | K-C6 不自评 | `quality-gate/SKILL.md:37` | `Do not assert your own accuracy. Report n_success / n_error / error_types; if n_error>0, mark the batch STALE.` | 对应 S1 probe 那次静默吞异常 |
| Q15 | K-B7 零硬编码 | `domain-learner/SKILL.md` | `The label set is provided by the schema file, not by your prior knowledge. Never introduce a type not in LABEL SET.` | 越界类型 0 |

## P4 · 分类标注 prompt（`classify_corpus.py:32`）

**现状原文**：
```
You are a controlled-vocabulary classifier ... if nothing fits, use "other" ...
ALREADY COMPUTED (do not guess; D1/D3 anchors are given) ...
Your job: from the CASE TEXT only, decide D2_problem_types and D4_solutions.
```
实测第一版 **12/20 无 JSON、D1 全空**，后改为「结构计算优先 + LLM 兜底」才可用。

| Q | 知识点 | 来源 | **新增指令句 / 结构调整** | 验收 |
|---|---|---|---|---|
| Q15 | K-B1 三源追溯 | `fantasy-prevention.md:5,42-46` | `D2/D4 may only be emitted from verified text evidence. If the case has no reasoning text, return empty D2/D4 with observability="not_observable"; do NOT infer from SMILES.` | crossdocked 的 L2 泄漏率 0 |
| Q18 | K-B5 verbatim | `citation-discipline` | `Every D2/D4 label needs a verbatim evidence phrase; otherwise route to other.free_text.` | 与 P3 同一 verbatim 校验器 |
| Q14 | K-E3 pointer-load | 同 P2 | **结构性**：VOCAB 改为 `vocab_path + vocab_hash`，不内联 24 类 + 21 策略全文 | prompt 缩短且支持词表热更新 |
| Q07 | K-C6 确定性优先 | `quality-gate/SKILL.md:56` | `Any field answerable by file lookup or RDKit is Type D: use the computed value, never your judgment. Semantic fields are Type S and must cite file:line.` | L0 与 `analyze()` 输出逐字段一致率 100% |
| Q16 | K-B6 proposals 门 | `ontology_grounded_extraction` | `New type suggestions go to other.candidate_new_types; they are NOT written to the vocabulary without human review.` | 词表无自动增长 |

## P5 · 工具链 system prompt（`toolenv/env.py:18`）

**现状原文（已含硬约束）**：
```
Workflow: diagnose_structure -> query_ontology -> get_solution_pack -> get_skill
-> propose_edits -> (compare_candidates if several) -> validate_edits -> finalize.
Rules: Never delete an atom in protected_atom_maps. Always emit SET_CHIRAL ...
finalize only after validate_edits returned hard_ok=true.
```
这是 8 个 prompt 里最完整的一个，端到端 8/8 `hard_ok=True`。**缺的是编排层的边界纪律**。

| Q | 知识点 | 来源 | **新增指令句** | 验收 |
|---|---|---|---|---|
| Q08 | K-C8 边界逐字复述 | `auto-pipeline` §3 | `At EVERY tool call, restate verbatim (not summarize) the current hard-constraint pack: protected_atom_maps, stereocentre_maps, required_edit_operations, and the last machine verdict.` | 每轮 assistant 消息可 grep 到契约字段 |
| Q06 | K-C7 统一 verdict | `invariant-check/SKILL.md:76-85` | `Maintain a 6-state verdict (PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR). overall is the WORST value so far. Any ERROR blocks finalize.` | 轨迹含 verdict 链 |
| Q07 | K-G3 拦截自评 | `auto-pipeline` §3 | `A tool response is the only source of truth. "I completed" is not a verdict; if a hard-constraint field is missing, downgrade to IN_PROGRESS and request it.` | 复现三次静默 bug 的探针应被拦下 |
| Q09 | K-G4 早停 | Phase Mode Table | `If the last 3 steps produced identical reward and action distribution, emit SATURATED and stop; do not loop.` | 18 批 GRPO 不再空转 |
| Q10 | K-C5 锚点冻结 | `invariant-check/SKILL.md:53,127` | `Echo case_id and problem_hash in every turn. Never change the target molecule or the problem statement mid-episode.` | 哈希一致率 100% |
| Q04 | K-F4 放弃是合法动作 | `writing-principles.md:87-88` | `abstain(reason_code) is a successful terminal action when no admissible candidate exists; it is not a failure.` | abstain 不被当作 parse_failed |

---

## P6 · GRPO 决策状态 prompt（`toolenv/grpo_traj.py:30`）

**现状**：`STATE_TMPL` 只给分子、保护原子、候选列表、规则；奖励来自固定查表 → 第 1 批即饱和。

| Q | 知识点 | 来源 | **新增指令句 / 结构调整** | 验收 |
|---|---|---|---|---|
| Q09 | K-C2 分歧度门 | `adversarial-falsification:233-235` | **结构性**：训练前先算组内 `std(R_env)`；`<0.1` 的 prompt 直接丢弃，不进入 GRPO。prompt 内加 `Each candidate has a DIFFERENT environment reward; do not assume a fixed action policy.` | G2 通过率 ≥60%（S1 probe 实测 87.5%） |
| Q21 | K-D4 KILL 论证 | `experiment-execution:323-324` | `If three consecutive batches show identical loss and action distribution, emit a KILL_ARGUMENT with evidence and stop; do not relabel saturation as convergence.` | 18 批不再空转 |
| Q19 | K-D1 预注册 | `method-registry:33` | `Freeze reward weights, action set, and train/heldout split BEFORE seeing results; record spec_hash. Post-hoc changes require a new run id.` | `spec_hash` 可复算 |
| Q03 | K-A2 联合置信 | `domain-adaptation-contract:5,79` | `Report per-component reward and the weakest component; joint uses multiplication, not a sum, so a single zero vetoes the step.` | 奖励日志含 `weakest_component` |

> 更根本的改造在 `ENV_REWARD_DESIGN.md`：把 group 从「5 个动作名」换成
> **同一分子的 K 个候选编辑产物**，用 AiZynthFinder / PLIP 的真实 `R_env` 产生分歧。
> prompt 层只能加纪律，**真分歧必须来自环境信号**。

## P7 · 工具探测 prompt（`toolenv/probe_qwen_toolcall.py:10`）

| Q | 知识点 | **新增指令句** | 验收 |
|---|---|---|---|
| Q07 | K-C6 | `Report n_success / n_error / error_types for every probe; never silently convert an exception into a zero score.` | 复现 `score=None` bug 时应报 error 而非 0 |
| Q17 | K-B3 | `Record model_id, prompt_hash, tool_schema_hash, seed, and max_tokens with the result.` | 每次探测可复现 |
| Q06 | K-C7 | `Emit a machine verdict, not a prose judgement.` | 输出 JSON 含 verdict |

## P8 · 论文写作（`paper/acl_latex.tex` + `compile.sh`）

不是 prompt，但对应「生成论文的最终产物」，需要一套 **writing-time prompt**（见 `04` 模板 T7/T8）。

| Q | 知识点 | 来源 | **改造动作** | 验收 |
|---|---|---|---|---|
| Q02/Q03 | K-A2/A3/A4 | `result-to-claim`, `domain-adaptation-contract` | 新增 `\paragraph{Evidence ledger}`：列出每个 claim 的 fidelity、TDAL 四维、`joint`、`weakest_dimension`、`missing_inputs`；按 tier 选动词 | 每个结论段有 ledger 引用 |
| Q04 | K-F4 | `writing-principles:87-88` | Limitations 固定 3–6 条，每条 = regime/boundary + observable consequence；写入 LoRA 零增益、GRPO 饱和、SA 代价 | 阴性结果全部有位置 |
| Q05 | K-F2 | `writing-principles:41,201` | 每段 ≥1 具体锚点；报 per-class N 与 CI，不只给均值 | 表格加 `N` 列 |
| Q22 | K-F1 | `writing-principles:27-37,74-85` | 编译前跑黑名单 + 无界 hedge 扫描；hedge-to-claim >1.0 重写 | 扫描零命中 |
| Q23 | K-F5 | `reviewer-independence:20-24` | fresh-thread reviewer，只读 PDF 与 ledger，不读推理过程/修复记录 | 评审轨迹留痕 |
| Q24 | K-F7/F8/F9 | `quality-gate`, `publishability-score`, `paper-compile` | `compile.sh` 之外加 `quality_gate.py`（G1–G7）+ publishability 评分 | 16 门 → 与 paperapp 对齐 |
| Q17 | K-B3 | `citation-audit:91-99` | 16 条 bib 做 EXISTENCE/METADATA/CONTEXT 三层校验，尤其 CONTEXT | 无 wrong-context 引用 |

---

## 改造的四条原则（避免把 prompt 越改越糟）

1. **只加契约，不改接口**：`[REASONING]/[EDITS]`、JSON schema、tool_calls 结构是与回放器/训练器的硬接口，一律不动。
2. **每条新增指令必须有机器验收**：本表「验收」列全部是可 grep / 可计数 / 可断言的条件，不接受「模型会更严谨」这类主观验收。
3. **pointer-load 优于内联**：词表、阈值、证据规范走路径 + 哈希，prompt 只传指针（K-E3），否则改词表要改所有 prompt。
4. **判定与生成分离**：新增的 verdict 门由脚本算（对应 SciForge `sciforge_audit.py`），prompt 只负责「必须消费 verdict」，绝不自己重算（K-G3）——这正是本框架三次静默 bug 的根源。

---

## 落地顺序

| 批次 | 改哪些 | 依赖 |
|---|---|---|
| B1 | P5 工具链 + P7 探测（Q06/Q07/Q08/Q09） | 无，收益最高 |
| B2 | P1 生成 + P8 写作（Q01–Q05, Q22–Q24） | B1 的 verdict 链 |
| B3 | P2/P3/P4 抽取标注（Q11–Q18） | pointer-load 改造 |
| B4 | P6 GRPO（Q09/Q19/Q21） | 环境奖励 S2 完成 |
