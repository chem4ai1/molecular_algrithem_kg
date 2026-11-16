# 06 · 验收矩阵：怎么证明「知识点真的融入了」

> 原则（来自 Q07 三次教训）：**任何「已融入」的结论都必须有机器可判定的测试**，
> 不接受「prompt 看起来更严谨」这类主观验收。每条测试给出触发信号、断言、通过阈值。

---

## 1. 三条必须复现的历史静默 bug（回归探针，最高优先级）

| ID | 复现场景 | 断言（**改造后必须成立**） | 对应知识点 |
|---|---|---|---|
| **R-BUG1** | 把 TBox 原型的 `requiresFailure` 值（`FM_Instability`）与 SMARTS 推断值（`Instability`）混用 | `query_ontology` 的 `why` 必须出现 `failure:labeled`；命中率 >0；若为 0 → `FAIL`，不得静默继续 | K-C6 / K-G3 |
| **R-BUG2** | 用文本正则口径给工具链算 `constraint_recall` | 必须**同时**报文本口径与工具证据口径，两列都在结果 JSON 里；缺一列 → `FAIL` | K-C6 / K-A3 |
| **R-BUG3** | 奖励探针里 `score=None` 触发 `float()` 异常 | `n_error>0`，批次标记 `STALE`，`n_routes` 不得被写成 0 冒充「真无分歧」 | K-C6 / Q07 |

> 这三条是 U3 的硬门。**改造前它们全部静默通过**，改造后必须显式 FAIL/STALE。

---

## 2. Prompt 契约测试（对应 `04` 的 8 份模板）

| 模板 | 触发信号 | 断言 | 阈值 |
|---|---|---|---|
| T1 编辑生成 | 20 条固定分子 | 输出含 `fidelity`；`proven/establishes` 出现率；`[REASONING]` 含 failure 段；evidence 在原文可查 | 100% / 0% / 100% / ≥0.95 |
| T2 工具链 | 8 分子 × 7 轮 | 每轮可 grep 到 6 个契约字段；verdict 链完整；无 verdict 时 finalize 次数 | 100% / 100% / 0 |
| T3 抽取 | 6 案例 + 故意篡改 `vocab_hash` | 篡改时返回 `{"status":"STALE"}`；正常时零发明 IRI；每层 evidence 三元组齐全 | 100% / 0 / 100% |
| T4 L2 | 705 分子（已有 gold） | `learning_basis` 覆盖；10 类全部出现在 `l2_labels` 或 `unmentioned_types`；薄证据时不输出标签 | 100% / 100% / 0 标签 |
| T5 分类 | 40 分子（golden+crossdocked） | L0 与 `analyze()` 逐字段一致；crossdocked 的 L2 泄漏率；Type S 有 `file:line` | 100% / 0 / 100% |
| T6 GRPO | 混合池 `mixed_000` | 组内 `std(R_env)>0.1` 的 prompt 占比；连续 3 批无变化时触发 KILL_ARGUMENT | ≥60%（S1 实测 87.5%）/ 100% |
| T7 claim gate | 论文 5 个主结论 | 每条有 fidelity + TDAL 四维 + joint + weakest_dimension；WEAK 段落无 `demonstrate` | 100% / 0% |
| T8 reviewer | 盲审一轮 | 输入不含作者推理/修复记录；wording-only 轮判 `round_invalid` | 100% / 100% |

---

## 3. Verdict 链与编排测试（对应 U1）

| ID | 断言 | 阈值 |
|---|---|---|
| V-01 | 6 态取值只出现在 `PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR` | 越界 0 |
| V-02 | `overall == worst(verdict_chain)`（构造含 1 个 FAIL 的链验证） | 100% |
| V-03 | 任一 `ERROR` → `finalize` 被阻断 | 100% |
| V-04 | 每个边界逐字复述 4 类硬约束字段（不是摘要，字符串精确匹配） | 100% |
| V-05 | 下游 **CONSUME** 上游 verdict，不重新计算（对比两次调用同一判定结果） | 一致率 100% |
| V-06 | ROUTED 合法缺失写进 `na_verdicts`，不伪造 PASS | 伪造数 0 |
| V-07 | `spec_hash` 可复算；词表升级后旧缓存自动失效 | 100% |

---

## 4. 证据规范与领域自适应测试（对应 U2）

| ID | 断言 | 来源知识点 |
|---|---|---|
| E-01 | `EVIDENCE_NORM.json` 只有一个写入者；每条 profile 带 `learning_basis` | K-E1 / K-E3 |
| E-02 | 文献少于 3 篇时写 `unknown — defaulting to conservative`，不发明规范 | K-B7 |
| E-03 | `learning_confidence<0.7` 时退回 `general` + WARN，不应用学习特征 | K-E4 |
| E-04 | `joint = T×D×A×L`，任一维 0 → ≤WEAK；`missing_inputs` → ≤MODERATE；joint 不四舍五入 | K-A2 / K-A3 |
| E-05 | Limitations **点名** `weakest_dimension` | K-A3 |
| E-06 | 门禁阈值（`std>0.1`、`Spearman≥0.3` 等）在 `EVIDENCE_NORM.json` 里可查到出处 | K-E2 |

---

## 5. 写作与阴性结果测试（对应 U4）

| ID | 断言 | 来源 |
|---|---|---|
| W-01 | AI 腔黑名单扫描零命中；零道歉词；每个 hedge 带数值界 | K-F1 |
| W-02 | 每段 ≥1 具体锚点；报 per-class N 与 CI | K-F2 / K-F5 |
| W-03 | 阴性结果（LoRA 零增益、GRPO 饱和、SA 代价、validity 更低）全部出现在 Limitations，且**不在 contribution 列表** | K-F4 |
| W-04 | 16 条 bib 每层 EXISTENCE/METADATA/CONTEXT 都有记录，wrong-context 数 0 | K-B3 |
| W-05 | `compile.sh` 前置 quality gate：G1–G7 全 PASS 才生成 PDF；零 error 零 warning | K-F7 / K-F9 |
| W-06 | 泄漏 scrub（工具名/伪造作者/`\cite{TODO}`）re-grep 零命中 | K-F3 |
| W-07 | 3 轮无实质响应 → KILL；`round_invalid` 计数可查 | K-F6 |

---

## 6. 前后端集成测试（对应 U1–U5）

| ID | 断言 | 备注 |
|---|---|---|
| I-01 | 6 组新 GET 均 200 且符合三态契约（loading / error / empty + 下一步按钮） | 沿用 S5 的 T-S5-09 |
| I-02 | `/api/status.api_registration_errors == {}` | paperapp 既有硬门 |
| I-03 | 门禁超时**不显示**「已自动通过」，只显示 BLOCKED + 原因 | V2_DELTA C25 |
| I-04 | 方向表单缺 `falsifiable_claim` 时无法提交 | V2_DELTA C26 / T-V2-22 |
| I-05 | `overall` 在前端显示为最差值而非平均绿 | K-C7 |
| I-06 | 人工对 claim 的 PASS/BLOCK 生成 `HumanDecision` 并被后续边界逐字复述（`decision_propagation_rate=1.0`） | 复用 H15 |
| I-07 | **194 项既有测试全绿、16 硬门不退化** | 不可破的稳定性基线 |
| I-08 | `bash scripts/test_all.sh` → `ALL_GREEN` | 交付门 |

---

## 7. 测试分层与执行顺序

```
L0 回归探针（R-BUG1~3）      ← 先跑，测量本身失效就别谈效果
L1 prompt 契约（T1~T8）
L2 verdict 链（V-01~07）
L3 证据规范（E-01~06）
L4 写作门禁（W-01~07）
L5 前后端集成（I-01~08）
L6 既有 194 项回归
```

**一票否决项**：`R-BUG3` / `V-02` / `E-04` / `I-07` 任一失败，整批不算通过。

---

## 8. 与现有 `COMPREHENSIVE_TEST_PLAN.md` 的关系

- 分子框架已有 T0–T9 分层测试与 GRPO G1–G17 门禁；
- 本文件是**论文生成侧**的补充，重点在「证据链 / claim / 写作」，
  两者通过 `verdict_chain.py` 共用同一套 6 态 verdict；
- G1–G17 的阈值来源由 `EVIDENCE_NORM.json` 提供（解决 Q11「阈值拍脑袋」）。
