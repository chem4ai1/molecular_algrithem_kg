# 指导 · 治理、启动与输出契约（14 份）

> **覆盖源文件**：`artifact-registry.md`(194) · `assurance-contract.md`(247) · `integration-contract.md`(248) · `output-protocol.md`(197) · `output-manifest.md`(84) · `output-versioning.md`(82) · `output-language.md`(42) · `project-architecture-contract.md`(208) · `startup-protocol.md`(155) · `skill-config.md`(192) · `effort-contract.md`(170) · `pipeline-integrity.md`(126) · `grounding-check.md`(80) · `plugin-router.md`(100)
> **一句话**：这组文件定义了「每个 skill 启动时必须先做什么、产出写到哪、谁能改配置、什么永远不可调」。先读这一份，再读其它指南。

---

## 1. 权威顺序（冲突时照这个裁决）

```
output-protocol.md        ← 目录布局唯一权威（v5.2 规则）
artifact-registry.md      ← 产物契约（名/生产者/消费者/schema/verifier）
integration-contract.md   ← 五组件接线与验证
schemas/*.schema.json     ← 字段级契约（见 schemas-guide.md）
SKILL.md 散文 / 示例      ← 最低优先级；示例与 registry 冲突时 registry 赢
```

> `artifact-registry.md` 明确：若它的 Path 列与 `output-protocol.md` 不一致，**是 registry 有 bug**。加/移产物时**先改 `output-protocol.md` 的目录树，再镜像 registry**。

---

## 2. 每个 skill 启动时必做的 5 步（`startup-protocol.md`，强制）

> 「No skill is allowed to start without first checking and consuming the domain signature.」

| 步 | 动作 | 失败处理 |
|---|---|---|
| 1 | 检查 `refine-logs/domain-signature.json` 是否存在 | 不存在 → 记 WARNING「No domain signature found. Using default behavior.」→ 跳到 Step 5 用默认值 |
| 2 | 读签名，抽 8 个字段 | `domain_profile.evidence_type/primary_domain`、`methodology_profile.verification_approach`、`writing_profile.style/citation_format`、`failure_mode_profile.common_failures`、`data_profile.data_availability`、`evidence_norm_profile`(v6.0) |
| 3 | 查 `domain-signature-consumer.md` 中**本 skill** 的消费规则 | 无对应节 → 用通用默认 |
| 4 | 应用规则并**写日志** | 格式：`Domain adaptation applied: [skill] → [field] = [value]` |
| 5 | 用适配后的参数跑主流程 | 任一规则应用失败 → WARNING + 继续用默认 |

**这是「领域适配自动化」的具体机制，不是建议**；每个下游 skill 独立在启动时读文件，orchestrator 不把签名正文注入 prompt。

示例（`/idea-discovery`）：`evidence_type → perspective_weights`；`/adversarial-falsification`：`common_failures → domain_failure_modes`。

---

## 3. 三条互相独立的配置轴

### 3.1 `effort`（深度/成本，`effort-contract.md`）

| 值 | token 倍数 | 隐含 assurance |
|---|---:|---|
| `lite` | ~0.4x | `draft` |
| `balanced` | 1x（默认） | `draft` |
| `max` | ~2.5x | `submission` |
| `beast` | ~5–8x | `submission` |

**每 skill 的档位表**（节选）：`research-lit` 找到论文 6-8 / 10-15 / 18-25 / 40-50；`idea-discovery` idea 数 4-6 / 8-12 / 12-16 / 20-30，MCTS 轮数 3 / 4 / 4-5 / 6；`novelty-check` 最近工作 top-3 / top-5 / top-8 / top-10+；`experiment-plan` seeds 1 / 3 / 5 / 5，baseline 族 2 / 3 / 4 / 5+。

### 3.2 `assurance`（审计严格度，`assurance-contract.md`）

| 值 | 行为 |
|---|---|
| `draft` | 审计仅在内容检测器命中时跑；**允许静默 skip**；Phase 6 仍出 Final Report |
| `submission` | 所有强制审计**必须输出 6 态 verdict 之一**；禁静默 skip；`paper-writing` Phase 6 调 `verify_paper_audits.sh`，非零退出阻断 Final Report；报告标 `submission-ready: yes/no` |

可独立覆盖：`effort: balanced, assurance: submission` = 正常深度 + 严格审计。**拆轴的起因**：曾出现 `effort: beast` 生成的却是 draft 质量、三个投稿门全被内容检测器跳过。

### 3.3 Hard Invariants（**任何 effort 都不能改**）

| 设置 | 固定值 |
|---|---|
| Reviewer reasoning effort | maximum |
| DBLP/CrossRef 引用校验 | on |
| Reviewer independence | on |
| Experiment integrity / Sanity check | on |
| Mandatory audit emission | always（submission 下） |
| `AUTO_PROCEED` / `difficulty` | 由用户决定，与 effort 正交 |

### 3.4 `skill-config.md`（集中公共旋钮）

优先级：`skill-config` 的 registered public knobs 由 `AGENT_DOC.md` 覆盖，再被单次调用参数覆盖；**改动必须可追溯**（Transparency 节）。读法：skill 启动时 `read_knob(name)`，不要在各 skill 里散落硬编码常量。

---

## 4. 输出协议（`output-protocol.md` + 三个子契约）

### 4.1 目录树（v6.0 两层分离，权威）

```
{problem_id}/
├── README.md / PROBLEM.md / AGENT_DOC.md        ← 入口层
├── .sciforge/                                   ← 隐藏状态层（durable + resumable）
│   ├── RUNSTATE.json / MANIFEST.md / APPROVAL_LOG.txt / PIPELINE_STATUS.md
│   ├── verdicts/   ← 22 个机器 verdict，平铺固定名 + PIPELINE_VERDICT_SUMMARY.md
│   ├── logs/ refine-logs/ audits/ tmp/
├── literature/ methods/ derivations/ src/ experiments/ logs/ figures/ paper/ output/
```

- 目录**按需惰性创建**，不预建空骨架；
- 机器 verdict → `.sciforge/verdicts/`；叙述报告 → `.sciforge/audits/`；科学交付物 → 可见层；
- 旧版本路径（v5.2 `verdicts/`、pre-v5.2 各阶段目录）是 **read-only fallback**，读取时回退但**写入一律用新路径**；
- 合法不产生的 verdict 必须在 `VERIFICATION_ROUTING.json` 的 `na_verdicts` 声明。

### 4.2 双写协议（`output-versioning.md`）

每个交付物写两份：**带时间戳的归档副本 + 固定名的最新副本**。时间戳格式锁定；stage-scoped 路径按阶段归属。收尾时 `tmp/` 清理（这是唯一允许删除的目录）。

### 4.3 MANIFEST（`output-manifest.md`）

`.sciforge/MANIFEST.md` 是 **append-only**：每个 skill 进入时做 Pre-Flight Check，产出后追加一行（时间 / skill / 产物路径 / hash / verdict）。**禁止改写已有行**。

### 4.4 长跑恢复（`output-protocol.md §Long-Horizon Resume Contract`）

`.sciforge/RUNSTATE.json` 在每个边界与每个人工检查点重写：`current_phase / last_completed_boundary / next_action / status / pending_approvals / budget_snapshot`。启动时若存在未完成 RUNSTATE：先 `validate_verdicts.py` 校验 verdict trail → 迁移旧路径产物 → 从 `next_action` 继续。

### 4.5 语言（`output-language.md`）

`language=chinese` 只本地化**叙述性文本**（报告、说明、对话）；**不本地化**机器字段名、verdict 枚举、路径、LaTeX 命令、schema key。

---

## 5. 产物注册表（`artifact-registry.md`）——加新产物的 SOP

**规则**：只要「下游行为依赖某个上游文件的存在或内容」，该文件**必须**登记。未登记 = advisory，任何 skill 不得拿它当门。

两类历史故障正是它要治的：① **Phantom artifacts**（ producer 写 `CLAIMS_FROM_RESULTS.md`，consumer 找 `CLAIM_VERDICT.md`，双方都以为契约成立，链静默断裂）；② **Schema drift**（producer 加了 `PREREG_HASH`，三个消费者没跟，预注册锁对它们形同虚设）。

**登记 4 步**：
1. 在 `output-protocol.md` 的目录树加固定名；
2. 在 `artifact-registry.md` 加一行：Artifact / Path / Producer / Consumers / Schema enforced by / Verifier；
3. 在 `schemas/` 建同名 schema 并注册到 `validate_verdicts.py` 的 `REGISTRY`（见 [schemas-guide.md](schemas-guide.md) §7）；
4. 用 fixture workspace 跑验证器。

**三条跨切面 Schema Invariants**：① 每个 audit verdict 用 6 态词汇；② 每个 audit JSON 带 `audited_input_hashes`；③ 目录布局与 `output-protocol.md` 一致。

> Registry 里还有一批「**未注册类**」产物（`S2_LADDER.json`、`ABLATION_LEDGER.json`、`NODES.json`、`CLAIM_ANCHORS.json`、`REP.json`、`AUDIT_TRAIL.json` 等）放在 `.sciforge/audits/` 或 `.sciforge/nodes/`，**它们不被 `validate_verdicts` 扫描**，改由 `s2_*` / `claim_anchor_gate` 等边界门强制。别把它们误加到 verdicts 目录。

---

## 6. 接线与完整性

| 文件 | 你要做什么 |
|---|---|
| `integration-contract.md` | 按「Required components」清单核对 5 个组件是否齐；用 §Enforcement 的方法逐个验证；照 §Live integration registry 记录。它专门治「verifier 路径写死在 skill 里，实际脚本改名后静默失效」 |
| `pipeline-integrity.md` | 每个 Phase 入口做 Integrity Check：列 Phase-Specific Prerequisites → 写 Integrity Check Log（规定格式）→ 出 Decision。前置不满足就别推进 |
| `grounding-check.md` | 写稿/给结论前走 Grounding Checklist，产出 Overall Verdict；这是轻量的「有没有凭空断言」自检 |
| `plugin-router.md` | **非约束咨询层**：可选插件（额外文献库、绘图指南、领域知识）的输出**永不**产生注册产物、**永不**触发 INV-X、**永不**改变管线语义。删掉 `research-plugins/` 不能破坏任何注册契约 |
| `project-architecture-contract.md` | README.md 用 GitHub 风格（Problem / Key Result / Pipeline Status / Directory Layout / How to Reproduce / Artifacts）；工作区卫生规则对**所有**调用生效，不只 auto-pipeline；Phase 16 跑 Cleanliness Audit |

---

## 7. 工作区卫生（Phase 16 与每次调用）

不得出现：顶层 stray `*.log`、stray JSON/TXT、`__pycache__` / `.pytest_cache` / `.DS_Store`、空目录；必须有 run README。对应脚本 `scripts/workspace_hygiene.py`。这一条来自真实事故：ARC-Bench 两轮评估发现 cwd 相对路径垃圾泄漏进了产物。

---

## 8. 检查清单

**每个 skill 进入时**
- [ ] 5 步 startup protocol 已跑，且写了 `Domain adaptation applied: …` 日志（或明确 WARNING 用默认）
- [ ] 读了本 skill 在 `domain-signature-consumer.md` 的消费规则
- [ ] `skill-config` 的 knob 已解析，优先级正确
- [ ] MANIFEST Pre-Flight 通过

**每次写产物**
- [ ] 路径符合 `output-protocol.md` 两层分离；机器 verdict 进 `.sciforge/verdicts/`
- [ ] 双写（时间戳副本 + 固定名副本）
- [ ] MANIFEST 追加一行（append-only）
- [ ] 若产物被下游依赖 → 已在 `artifact-registry.md` 登记

**收尾**
- [ ] `RUNSTATE.json` 反映最终 `next_action`
- [ ] `validate_verdicts.py --strict --require-complete` 通过
- [ ] 工作区卫生通过
- [ ] `submission` 模式下 `verify_paper_audits.sh` 非零即阻断，已标 `submission-ready`

---

## 9. 与框架的对应

参见 [APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) §1 的 P1「单一写入者」、P5「判定靠 exit code」、P6「降级不等于跳过」、P7「可复现 = 源码+输入+哈希」——本组文件就是这四条原则的原始出处。`RUNSTATE` / `RUN_BUDGET` / `ArtifactRegistry` 对应框架 §4.1 治理层类。
