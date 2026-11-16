# 指导 · Verdict Schemas 使用手册（23 个 schema + 校验器）

> **依据**：`skills/shared-references/schemas/README.md`（v5.3，154 行）、同目录 23 个 `*.schema.json`、`scripts/validate_verdicts.py`、`shared-references/{artifact-registry,assurance-contract,output-protocol}.md`
> **用途**：指导你如何**写对**一个机器可读 verdict、如何**校验**、如何**新增**一个 schema，以及哪些写法会被校验器直接判为内部错误。

---

## 1. 这套 schema 到底解决什么

> 「Before this directory existed, every field promise in the skill docs was prose-only: agents could misspell or omit fields silently.」

在此之前，所有 skill 文档里的字段承诺都只是散文，agent 拼错字段名或漏字段**不会报错**，下游三阶段后才可能发现。这套 schema + stdlib 校验器把散文承诺变成**可检查的机器契约**。

**使用心法**：schema 是「字段级真相源」，`artifact-registry.md` 是「产物级真相源」，`output-protocol.md` 是「目录布局唯一权威」。三者冲突时：**`output-protocol.md` > `artifact-registry.md` > schema > SKILL.md 散文**。

---

## 2. 位置与命名约定（务必照做）

| 项 | 约定 |
|---|---|
| 产物位置 | 每个 workspace 的 `.sciforge/verdicts/`（v6.0 home；v5.2 为 `verdicts/`；更早在各阶段目录）。**固定文件名、平铺、不分子目录** |
| schema 位置 | `skills/shared-references/schemas/<NAME>.schema.json` |
| 对应关系 | `.sciforge/verdicts/REVIEW_STATE.json` → `schemas/REVIEW_STATE.schema.json`，`<NAME>` 必须完全一致 |
| 叙述性报告 | 放 `.sciforge/audits/`（如 `LEAKAGE_AUDIT.md`），**不是 verdict**，不进本套 schema |
| 两个例外 | `PROBLEM_HASH.txt`（INV-G1）、`REGISTRY_HASH.txt`（hash lock）是 **.txt 不是 JSON**，由校验器直接用 `^[0-9a-f]{64}$` 正则检查；`REGISTRY_HASH.txt` 额外允许 `BLOCKED: <reason>` 形式（实验矩阵不完整时） |
| 非 verdict | `RUNSTATE.schema.json` 只是放这里便于发现，**不被 `validate_verdicts.py` 扫描**（校验器只看 verdicts 目录）；由 orchestrator 的 resume 协议与 `tests/test_e2e_smoke.py` 检查 |

---

## 3. 23 个 schema 速查表

| Schema | 必需字段数 | 核心字段（required 摘选） | 关键枚举 / 约束 |
|---|---:|---|---|
| `BLINDSPOT_CHECK` | 5 | `round, evidence_type, failure_modes_checked, unresolved_count, fatal_unresolved` | 固定名文件每轮**覆写**（历史在 `AUTO_REVIEW.md`） |
| `BUDGET_FLOOR` | 2 | `verdict, budget_floor` | `verdict ∈ {PASS, IN_PROGRESS, BLOCKED}`；后检两条硬规则见 §5 |
| `CITATION_AUDIT` | 11 | `audit_skill, verdict, reason_code, summary, audited_input_hashes, trace_path, thread_id…` | `audit_skill=citation-audit`；6 态 verdict；`generated_at` 有 pattern |
| `EVALUATION_PROTOCOL` | 2 | `schema_version, generated_at` | **故意最宽松**：字段名未在文档固定，靠下游 `parity_check` / `all_seeds_reported` / `full_grid_reported` 落实 |
| `EVALUATION_REVIEW` | 6 | `dimensions, justifications, fatal_flaws, required_revisions, overall, verdict` | `verdict ∈ {ACCEPT, REVISE, REJECT}`（**不是 6 态**） |
| `EXPERIMENT_MATRIX` | 3 | `budget_scale, groups, locked_hash` | `budget_scale ∈ {full, lite, pilot}` |
| `FAIRNESS` | 7 | `gate, version, verdict, checks, comparisons, numbers_stale, generated_at` | `gate=experiment-fairness`；6 态 |
| `FIGURE_AUDITS` | 3 | `schema_version, generated_at, figures` | 所有图的审计镜像（upsert） |
| `INVARIANT_CHECK` | 5 | `timestamp, phase_boundary, discipline_context, overall_verdict, checks` | 用的是 **`overall_verdict`** 而不是 `verdict`；6 态 |
| `KILL_ARGUMENT` | 10 | `audit_skill, verdict, reason_code, summary, audited_input_hashes, trace_path, thread_id…` | `audit_skill=kill-argument`；6 态 |
| `LEAKAGE_AUDIT` | 9 | `verdict, discipline_context, type_i, type_ii, type_iii, type_iv, blockers…` | 6 态；`type_ii` 可 `NOT_APPLICABLE` |
| `LEAKAGE_SCRUB` | 8 | `gate, version, status, hits_found, hits_scrubbed, hits_remaining, classes_seen…` | `gate=pipeline-leakage-scrub`；`status ∈ {PASS, FAIL}`（**不是 6 态**） |
| `LOGIC_VERIFICATION` | 10 | `verdict, q_id, n_fatal, n_critical, n_major, n_minor, issues…` | 6 态 + `counterexample_passed` 枚举 |
| `PAPER_CLAIM_AUDIT` | 5 | `verdict, reason_code, summary, audited_input_hashes, generated_at` | 6 态；`aigc_scan` 内部结构**未约束** |
| `PAPER_COMPILE` | 4 | `verdict, zero_warnings, zero_errors, generated_at` | 6 态 |
| `PROOF_AUDIT` | 10 | `audit_skill, verdict, reason_code, summary, audited_input_hashes, trace_path, thread_id…` | 6 态 |
| `PUBLISHABILITY_SCORE` | 6 | `q_id, scored_at, verdict, total_score, dimensions, main_logic_gating` | `verdict ∈ {SUBMISSION_READY, SUPPLEMENTARY_GATE…}`（`scored_at` 有 pattern） |
| `QUALITY_GATE` | 3 | `verdict, overall, generated_at` | 6 态 + `stagnation` 枚举 |
| `REVIEW_LEDGER` | 1 | `details` | **单一 JSON 对象**，round 历史在 `details.rounds[]`；round 级用 `ready/almost/not_ready`，envelope 用 6 态 |
| `REVIEW_STATE` | 9 | `round, threadId, status, difficulty, last_score, last_verdict, pending_derivations…` | `status ∈ {in_progress, completed}`；两种 `not_ready` / `not ready` 拼写都接受（写 `not_ready`） |
| `RUNSTATE` | 6 | `schema_version, run_id, problem_id, current_phase, status, updated_at` | **非 verdict**；`status ∈ {running, paused_checkpoint, …}` |
| `RUN_BUDGET` | 10 | `schema_version, run_id, started_at, wall_clock_seconds, api_cost_usd, pivot_count, ba_rounds…` | 由 orchestrator Phase 0 初始化、每边界记账 |
| `VERIFICATION_ROUTING` | 3 | `route, evidence_type, reason` | `route ∈ {experiment-first, theory-only, hybrid…}`；`na_verdicts` 声明合法缺失 |

> ⚠️ **不要把 6 态 verdict 当成全局词汇表**：`EVALUATION_REVIEW` 用 `ACCEPT/REVISE/REJECT`，`LEAKAGE_SCRUB` 用 `PASS/FAIL`，`BUDGET_FLOOR` 用 `PASS/IN_PROGRESS/BLOCKED`，`REVIEW_LEDGER` 的 round 级用 `ready/almost/not_ready`。写错枚举是最常见的 FAIL。

---

## 4. 校验器用法（照抄即可）

```bash
python3 scripts/validate_verdicts.py <workspace>/.sciforge/verdicts/ [--strict]
```

| 退出码 | 含义 |
|---:|---|
| `0` | 全部有效 |
| `1` | 有违规 |
| `2` | 用法错误 |

行为要点：

| 情况 | 校验器行为 |
|---|---|
| 已注册且存在 | 按同名 schema 校验 |
| **未注册的 `*.json`** | **WARN**；`--strict` 下 WARN 也失败（BLOCKED 语义） |
| 已注册但缺失 | 列为 **pending**，**不是错误**（verdict 随管线推进逐步出现） |
| 缺失但列在 `VERIFICATION_ROUTING.json` 的 `na_verdicts` | 报 **N/A**（合法缺失，例如 theory-only run 没有实验 verdict） |
| 声明 N/A 却实际存在 | **WARN**（路由/产物不一致） |

> 因此**不要为了「让 pending 消失」提前伪造 verdict**。`na_verdicts` 才是声明合法缺失的正确机制。

---

## 5. 三条超出 schema 的跨字段后检（必背）

1. **Audit family 6 态词汇**：`PROOF_AUDIT`、`LOGIC_VERIFICATION`、`LEAKAGE_AUDIT`、`CITATION_AUDIT`、`KILL_ARGUMENT`、`PAPER_CLAIM_AUDIT`、`INVARIANT_CHECK` 必须带 `verdict`（`INVARIANT_CHECK` 用 `overall_verdict`），值 ∈ `PASS | WARN | FAIL | NOT_APPLICABLE | BLOCKED | ERROR`。schema 里写了 enum，校验器**再查一遍**。
2. **`audited_input_hashes`**：`PROOF_AUDIT / CITATION_AUDIT / KILL_ARGUMENT / LEAKAGE_AUDIT / PAPER_CLAIM_AUDIT` 必须含对象 `{"文件名": "sha256:<hex>"}`。这是 `artifact-registry.md` invariant 2，防止「审计完又悄悄改了输入」。
3. **Budget-floor 硬规则**：`budget_floor.satisfied == false` 时**禁止** `verdict: PASS`（只允许 `IN_PROGRESS` / `BLOCKED`）；且 `verdict: PASS` 必须带 `completion_justification[]`（`{route, status, evidence}`）。

### 6 态词汇的语义（`assurance-contract.md`）

| 状态 | 审计跑了吗 | 是否阻断 submission |
|---|---|---|
| `PASS` | 是 | 否 |
| `WARN` | 是 | 否 |
| `FAIL` | 是 | **是** |
| `NOT_APPLICABLE` | 阶段跑了，检测器阴性，**写了 verdict 文件** | 否 |
| `BLOCKED` | 应跑但前置缺失（有数字 claim 却无 `results/`） | **是** |
| `ERROR` | 调用失败（网络/超时/格式错） | **是** |

> **`NOT_APPLICABLE ≠ SKIP`**：前者有文件为证，可从 LLM 外部验证；后者什么都没留下。`assurance: submission` 时**禁止静默 skip**。`assurance` 与 `effort` 是两条独立轴：`lite/balanced → draft`，`max/beast → submission`；也可显式 `-- effort: balanced, assurance: submission`。

---

## 6. 支持的 JSON Schema 子集（写 schema 时的红线）

`validate_verdicts.py` 是**纯 stdlib 的极简校验器，不依赖 `jsonschema` 包**。

| 可用 | `type`(object/array/string/integer/number/boolean/null)、`required`、`properties`、`additionalProperties`(布尔或子 schema)、`enum`、`pattern`、`minimum` / `maximum`、`items`（作用于每个数组元素） |
|---|---|
| 被忽略的注解 | `$schema`, `$id`, `$comment`, `title`, `description`, `examples`, `default` |
| **会报内部错误** | `$ref`, `oneOf`, `anyOf`, `allOf`, `const`, `format`, `minItems`, `patternProperties`, … |

> 设计意图：不支持的关键字**不会被静默忽略**，而是报 internal error，这样 schema 永远不会「承诺了却没校验」。写 schema 时务必保持 `additionalProperties: true` 的宽松策略，只强制文档承诺了的字段。

---

## 7. 新增一个 verdict schema 的 4 步 SOP

1. **先改目录权威**：在 `output-protocol.md` 的 `.sciforge/verdicts/` 树里加固定文件名；再在 `artifact-registry.md` 加一行（Path 必须与 `output-protocol.md` 一致）。顺序不能反。
2. **建 schema**：`schemas/<NAME>.schema.json`，draft 2020-12 但只用 §6 的子集；只把文档承诺的字段放进 `required`，其余 `additionalProperties: true`。
3. **注册**：在 `scripts/validate_verdicts.py` 的 `REGISTRY` dict 里加一项，按需置 `audit_family=True`（6 态词汇）/ `audit_hashes=True`（`audited_input_hashes`）。
4. **自测**：`python3 -m json.tool schemas/<NAME>.schema.json`，再用一个 fixture workspace 跑校验器。

**最小示例**（可直接复制）：

```bash
mkdir -p myrun/.sciforge/verdicts
cat > myrun/.sciforge/verdicts/QUALITY_GATE.json <<'EOF'
{
  "verdict": "PASS",
  "overall": "PASS",
  "generated_at": "2026-11-15T00:00:00Z",
  "stagnation": "PASS",
  "quality_floor": "PASS",
  "self_deception": "PASS"
}
EOF
python3 scripts/validate_verdicts.py myrun/.sciforge/verdicts/ --strict
```

---

## 8. 12 条 Known gaps 的实施解读

README 的 §Known gaps 不是待办清单，而是**已定案的口径裁决**，实施时必须按它写：

| # | 裁决 |
|---|---|
| 1 | `REVIEW_LEDGER` = 单一 JSON 对象 + `details.rounds[]`（**不是 JSONL 流**）；`scripts/verifiers/verify_review_ledger.sh` 强制；`phase: "finalized"` 终止条目不带 `action_items` |
| 2 | `BLINDSPOT_CHECK` 每轮**覆写**，历史在 `AUTO_REVIEW.md`（固定名文件只能装一个 JSON 文档） |
| 3 | `LEAKAGE_AUDIT` 必须带 `audited_input_hashes`（registry 优先于 SKILL.md 示例） |
| 4 | `thread_id` 除 `CITATION_AUDIT` 外**可选**（OSS 单 agent，没有外部 reviewer thread） |
| 5 | `LOGIC_VERIFICATION` 用完整 6 态（`NOT_APPLICABLE` 保留但 OSS 对推导恒跑） |
| 6 | `BUDGET_FLOOR` 字段名由 e2e fixture 钉死：`budget_floor.checks.{routes_explored, matrix_completion, seed_budget, failure_records, remaining_budget_declaration}` |
| 7 | `REVIEW_STATE` 两种 `not_ready` / `not ready` 拼写都合法，生产者写 `not_ready` |
| 8 | `PAPER_CLAIM_AUDIT` 无官方示例；只承诺 verdict、`audited_input_hashes`、`aigc_scan`，后者内部形状自由 |
| 9 | `VERIFICATION_ROUTING.json` 的权威路径是 `.sciforge/verdicts/`（不是 `refine-logs/`） |
| 10 | `PROBLEM_HASH` / `REGISTRY_HASH` 是 `.txt`，正则检查 |
| 11 | `RUN_BUDGET.json` 字段由 orchestrator Phase 0 + fixture 钉死 |
| 12 | `EVALUATION_PROTOCOL` 故意只有 2 个 required；四项预注册（metrics lock / baseline parity / baseline re-implementation / anti-cherry-picking）靠 result-to-claim 的检查落实 |

---

## 9. 与「分子算法设计」应用层框架的对接

| 本套机制 | 对应到 `APPLICATION_ONTOLOGY_FRAMEWORK.md` |
|---|---|
| 6 态 verdict | `Verdict` 类的 `state` 属性；`Gate` 的 `exit_code_map` |
| `audited_input_hashes` | `ClaimAnchor` / `Hash` 节点；与 GGR `code_sha/inputs_sha/outputs_sha` 同构 |
| `na_verdicts` | `VerificationRoute` → 合法缺失声明；对应 GGR `dry` 下 R6 诚实 `BLOCKED` |
| `RUNSTATE` / `RUN_BUDGET` | `RunBudget` / `LoopBack` 的持久化；GGR 的 `events.ndjson` 也是 durable truth |
| `FIGURE_AUDITS` | `FigureAudit` 的 upsert 镜像（见 P11 解析） |
| `BUDGET_FLOOR` 硬规则 | `budget_floor` 门；防止「实验没跑完就 PASS」 |
| `EXPERIMENT_MATRIX.locked_hash` | `MethodRegistry` 的 Section 3 hash lock（INV-G1 同源） |

**落地建议**：若把 GGR 的 `FINAL_EVALUATION.json` 接入这套校验器，新增一个 `FINAL_EVALUATION.schema.json` 时应置 `audit_hashes=True`，并把 `sau_score / coverage / drift_rate / overall` 放入 `required`，同时在 `artifact-registry.md` 登记单一写入者为 `finalize()`。
