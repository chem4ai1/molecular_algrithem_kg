# 05 · 前后端升级方案（基于已有 paperapp，纯增量）

> 现状（`docs/plan/S6_FINAL_REPORT.md` / `README.md`）：`src/capfactory/paperapp/` 22 模块、
> `web/paperapp_api.py` 43 GET + 6 POST、`paperapp.html` 7 tab（v2 加的 T7「人工决策」）、
> `tests/test_paperapp_s0..s6.py` **194 项全绿**、16 硬门 PASS、`run:demo:s6` 26 阶段 PASS。
> **原则：不改这 22 个模块、不动既有 API 语义、不推翻 194 项测试，只做增量。**

---

## 1. 一句话定位

paperapp 已经把「语义图 / 缓存 / 矿挖 / 决策传播」做成了可审计前后端；
**缺的是「证据链 → claim → 论文」这一段**。升级 = 把 `03`/`04` 的 prompt 契约
落成后端 verdict 门 + 前端可审计视图，并与已有 `CONSTRAINT_REINJECTION` 机制接上。

---

## 2. 后端增量（4 个新模块，全部放 `src/capfactory/paperapp/`）

| 新模块 | 对应知识点 | 职责 | 输入 → 输出 |
|---|---|---|---|
| `verdict_chain.py` | K-C7 / K-G3 / K-G2 | 统一 6 态 verdict；`overall = worst(chain)`；边界逐字复述；拦截「我完成了」 | 各工具的机器判定 → `.sciforge/verdicts/VERDICT_CHAIN.json` |
| `claim_gate.py` | K-A1~A5 / T7 | 3-fidelity 分级、TDAL 4 维乘积、`weakest_dimension`、tier→动词映射、UNSUPPORTED BLOCK | `end2end_results.json` + `evidence ledger` → `CLAIM_LEDGER.json` |
| `evidence_norm.py` | K-E1 / K-E2 / K-E4 | 从 seed papers 学 `evidence_norm_profile`（≥3 seeds / mean±std / scaffold split / baseline+ablation），带 `learning_basis` + `learning_confidence`，薄证据写 `unknown — defaulting to conservative` | `paper/references.bib` + seed 列表 → `EVIDENCE_NORM.json`（**sole writer**） |
| `probe_audit.py` | K-C6 / Q07 | 每个探针强制报 `n_success/n_error/error_types`；异常绝不静默记 0；`n_error>0` → 批 `STALE` | `env_reward_probe.json` 等 → `PROBE_HEALTH.json` |

**关键约束**：
- `verdict_chain.py` 是**唯一 verdict 聚合者**（SingleWriter，K-E3）
- `evidence_norm.py` 是 `EVIDENCE_NORM.json` 的唯一写入者，带 `spec_hash`（K-E5）
- 下游一律 **CONSUME 上游 verdict，不重算**（K-C6）——直接复用 paperapp 已有的
  `CONSTRAINT_REINJECTION.json` / `SUPERSEDES` 传播机制，不另造一套

---

## 3. API 增量（`/api/v10/paperapp/*`，6 组 GET + 2 个 POST）

| 端点 | 返回 | 前端用途 |
|---|---|---|
| `GET /verdicts/chain` | 6 态链 + overall + 每步证据指针 | T8 证据链视图 |
| `GET /claims/ledger` | 每条 claim 的 fidelity / TDAL / joint / weakest_dimension / allowed_verbs | T9 声明门 |
| `GET /evidence-norm` | 领域证据规范 + learning_basis + confidence | T9 阈值来源 |
| `GET /negative-results` | 阴性结果 ledger（regime / boundary / consequence） | T9 / Limitations 草稿 |
| `GET /probe-health` | n_success / n_error / error_types / STALE 批次 | T10 探针健康 |
| `GET /boundary-reinjection` | 每边界逐字复述记录（复用已有 H15） | T7 已有视图扩展 |
| `POST /claims/{id}/verdict` | 人工对某 claim 判 PASS/BLOCK | 人工检查点 |
| `POST /probe/{id}/stale` | 把异常批次标 STALE 并触发重跑 | 人工检查点 |

> 与 V2_DELTA 已有的 `/choices` `/decisions` `/reinjection` 并列，不覆盖。
> 所有 GET 保持 paperapp 既有三态契约（loading / error / empty + 可操作下一步，S5 硬门）。

---

## 4. 前端增量（7 tab → 10 tab，或先做 3 个面板）

| Tab | 内容 | 对应问题 |
|---|---|---|
| **T8 证据链** | verdict 时间线（颜色 + 文字双编码）、每步 `tool:file:line` 指针、overall 最差值高亮、边界逐字复述记录 | Q06/Q07/Q08 |
| **T9 声明门** | claim 表格：fidelity 徽章、TDAL 四维雷达、joint、weakest_dimension、允许动词、BLOCK 原因；下方阴性结果 ledger + 证据规范卡 | Q01–Q05, Q11/Q12, Q22 |
| **T10 探针健康** | `n_success/n_error`、error_types、STALE 批次红标、「重新运行」按钮；展示三个历史静默 bug 的回归探针状态 | Q07/Q09 |

**必须避免的反模式**（V2_DELTA C25 已踩过）：
- 门禁超时**不得显示「已自动通过」**，只显示 `BLOCKED + 原因`
- `overall` 不能显示成「全部通过」的绿色平均值，必须显示最差值
- 阴性结果不能折叠隐藏，也不能标成 contribution

---

## 5. 数据流（从分子管线到论文）

```
MolLingo 产物
  eval_pipeline / end2end_results / grpo_pool / env_reward_probe
        │  (只读，pointer-load)
        ▼
  verdict_chain.py  ← 9 个工具的机器判定 (validate_edits / SHACL / RDKit)
        │  VERDICT_CHAIN.json (sole writer, spec_hash)
        ▼
  claim_gate.py  ← evidence_norm.py 的 EVIDENCE_NORM.json
        │  CLAIM_LEDGER.json
        ▼
  paper/acl_latex.tex 生成前的 quality gate (T7)
        │  阴性结果 → Limitations；BLOCK 的 claim 不进正文
        ▼
  paperapp 后端 6 组 API → T8/T9/T10 前端 → 人工 /claims/{id}/verdict
        │
        ▼
  CONSTRAINT_REINJECTION：人工决定 append-only，后续每边界逐字复述
```

**与现有 paperapp 的接合点**：人工对 claim 的 PASS/BLOCK 就是一个新的 `HumanDecision`，
直接复用 v2 的 `ChoicePoint → Decision → SUPERSEDES → 约束再注入` 链路，无需新机制。

---

## 6. 分批实施（每批可独立验收）

| 批次 | 内容 | 验收 | 依赖 |
|---|---|---|---|
| **U1 判定层** | `verdict_chain.py` + `GET /verdicts/chain` + T8 | 6 态链完整、`overall=worst`、194 项旧测试不退化 | 无 |
| **U2 声明层** | `claim_gate.py` + `evidence_norm.py` + `GET /claims/ledger` + T9 | 每个主结论有 fidelity + TDAL + weakest_dimension；论文动词与 tier 一致 | U1 |
| **U3 健康层** | `probe_audit.py` + `GET /probe-health` + T10 | 复现 `score=None` 探针时报 error 而非 0；`n_error>0` → STALE | 无（可与 U1 并行） |
| **U4 写作门禁** | `paper/claim_gate.py` 前置 `compile.sh`；T7/T8 reviewer prompt | 编译前 G1–G7 全 PASS 才生成 PDF；黑名单零命中 | U1+U2 |
| **U5 经验回放** | `LESSONS.json` 接入 paperapp 已有 `replay.py` | 每次 FAIL/KILL 带 lesson+evidence，下轮作 `avoid` | U3 |

---

## 7. 明确「不做」的事

1. **不重写 `auto-pipeline`**：它是 SciForge 的唯一入口编排器，paperapp 已经复刻 26 阶段；本次只加 verdict 消费，不新增第二条管线。
2. **不把词表/阈值内联进任何 prompt**（K-E3），一律 path + hash。
3. **不让模型重算 verdict**（K-G3），所有判定由 RDKit / SHACL / 已有 scripts 出。
4. **不为了清 pending 伪造 verdict**（K-G4）：ROUTED 合法缺失写 `na_verdicts`。
5. **不静默丢弃阴性结果**，也不把它写成贡献（K-F4）。
6. **不改动 `vocab.py` / `research/gaps.py` / `applayer/miner.py` / `graph_source.py`**
   —— S6 记录里这四个文件「全部未改」，是已验证的稳定性边界。
