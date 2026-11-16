# P2 · `idea-discovery` — 文献锚定的 MCTS 选题器

> **解析对象**：`SciForge-OSS-master/skills/meta-skills/idea-discovery/SKILL.md`（v1.7.2，295 行）
> **功能批次**：① 领域与选题层
> **机械对应代码**：`scripts/gap_gate.py`、`scripts/dep_gate.py`、`scripts/detect_device.py`、`scripts/security_scan.py`、`scripts/s2_ladder_gate.py`
> **性质判断**：**契约型 skill**，但它是 8 个 meta-skill 中**脚本耦合最紧**的一个 —— v6.0 的 gap chain 由 `gap_gate.py` 硬门强制。

---

## 1. 身份卡

| 项 | 值 |
|---|---|
| `name` / `version` | `idea-discovery` / `1.7.2` |
| `type` / `role` | `meta-skill` / `research-idea-generation` |
| 管线阶段 | **Phase 2**（v6.0 顺序：Phase 4broad 广搜 → **Phase 2** → 2.5 → 2.5b → 3） |
| 阶段模式 | **`[MUST]`** |
| 人工检查点 | Phase 3→4 之前的「最终 idea 选定」由人做；本 skill 只产出 1–3 个候选 |
| 核心不变量 | 「第一个 idea 很少是最好的」→ MCTS ≥ 4 轮后才能提交 |

---

## 2. 解决什么问题

### 2.1 三个具体病灶

| 病灶 | 现有机制 | 出处 |
|---|---|---|
| **先拍脑袋再找文献** | v6.0 literature-first gap chain：Phase 4broad 先产出 `GAP_REPORT.md`，之后才允许 gap 锚定 / novelty 预筛 / Round 2–4 打分 | CRUX arXiv:2607.27191 失败模式 #1 |
| **「thin results packaged as findings」** | 每个被提升的 idea 必须引用一个真实 `gap-id`（或限量的 `exploratory` 槽） | 同上 |
| **AI 反复生成已被杀死的 idea** | `failed_ideas.json` + TF-IDF 余弦 > 0.78 硬拒 + prompt 软注入 | v3.1 反重复记忆 |

### 2.2 一个重要的架构选择

main SciForge 在 MCTS 产出 0 个 idea 时会回退到 legacy demo/pilot 实验。**OSS 明确禁止**：降级只能是「放宽视角重新 ideation」或「交还人类重新界定问题」，绝不能拿一个 demo 实验冒充真的 toy/full 门。

---

## 3. 对应论文生成的哪个阶段

| 维度 | 说明 |
|---|---|
| DAG 位置 | `1b → 4broad → **2** → 2.5(证伪) → 2.5b(EG) → 3(novelty) → 4targeted → 5(method-registry)` |
| 并行组 | **Group A**：Phase 4broad 与 Phase 2 Round 1 可并行「头脑风暴」，但 gap 锚定、novelty 预筛、Round 2–4 打分**必须等 GAP_REPORT.md 可读** |
| 前置 | 冻结的 Q-id（INV-G1）、`domain-signature.json`、`references.bib`、`GAP_REPORT.md` |
| 后继 | `/adversarial-falsification`、`/novelty-check`、`/method-registry`、`/invariant-check` |
| 门 | `gap_gate.py` PASS 才能越过 Phase 4broad 边界；本阶段门 = ≥1 idea 且 MCTS 收敛 |
| 回退 | L1（2.5 WEAKENED → 回 Phase 2，3 轮）；L2（FALSIFIED → 淘汰该 idea）；L7/L9/L11（BA 回溯，全局共享 ≤2 轮） |

---

## 4. 对应「论文 / 算法 / 代码 / 数据」的哪个模块、哪个部分

| 层次 | 对应模块 | 具体部分 | 本 skill 的作用 |
|---|---|---|---|
| **论文层** | Introduction 的 gap / contribution | `gap_anchor`、`insight`、`novelty_delta` | 直接决定 Intro 里「哪个空白被填上、相对谁不同」 |
| **论文层** | 核心主张 | `falsifiable_claim` | 决定全篇要验证的那句话，也是 Phase 14 kill-argument 的靶子 |
| **算法层** | 方法框架 / 机制链 | `mechanism`、4 视角（theoretical / computational / qualitative / empirical） | 决定后续 `METHOD_REGISTRY` 里方法是推导型、仿真型、机理型还是估计型 |
| **算法层** | 假设与边界 | `boundary`、`critical_assumptions` | 为 2.5 证伪提供攻击面，为 6a 推导提供前提 |
| **代码层** | 可执行性规格 | `requires_gpu_gb` / `requires_packages` / `code_snippet` / `data_sources` | Type-A 四项机械检查的输入；决定 idea 是否进 MCTS |
| **代码层** | 依赖声明 | `requires_packages` | 与 `dep_gate.py` 的 `dependencies.json` 允许清单对齐 |
| **数据层** | 数据可得性 | `data_required` / `data_sources` / 6 轴里的 `data-readiness` | 决定实验是否能落地，数据源不可达直接零成本淘汰 |
| **数据层** | 跨 run 经验 | 兄弟 workspace 的 `output/RUN_PREPRINT.md` 与 `LESSONS.json` | 把系统自己的失败/部分结果当作一等锚定证据（`PREPRINT:<run-id>#<gap>`） |

---

## 5. 做了什么（输入 → 处理 → 输出）

```
输入  Q-id + domain-signature.json + references.bib + GAP_REPORT.md
      + RUN_PREPRINT.md / LESSONS.json + failed_ideas.json + data/
  ↓
Step 0  冻结 Q-id（写入 FINAL_PROPOSAL Problem Anchor）
Step 1  文献感知：读 references.bib，避免直接重复
Step 2  4 视角生成 8–12 个 root 节点
Step 3  构造 IDEA_DAG.json（边 = depends_on，无环）+ Mermaid 可视化
Step 4  MCTS 4 轮（扩展 → 选择/仿真 → 反传 → 终选）
Step 5  FINAL_PROPOSAL.md（强制人工检查点）
Step 6  通知下游 method-registry / theory-derivation / invariant-check
输出  6 个 refine-logs 文件 + failed_ideas.json + BA_EVENT.json（触发时）
```

### 5.1 4 个通用视角（严禁学科专用框架）

| 视角 | 产出 | 典型 framing |
|---|---|---|
| `theoretical` | 从假设到结论的符号推导链 | "We establish [outcome] by deriving [chain] under [assumptions]" |
| `computational` | 数值合理性检验 | "We confirm [prediction] numerically via [sweep] in [regime]" |
| `qualitative` | 机理推理 | "We show [mechanism] implies [prediction] by [qualitative argument]" |
| `empirical` | 因果识别 / 参数估计策略 | "We recover [causal parameter] via [identification strategy] under [assumption]" |

> 明确禁止重新引入 economics DiD/IV/RDD、cs-ml SOTA、physics PNV 等学科专用框定。

### 5.2 6 轴预筛（idea-fit）

`novelty / feasibility / relevance / tractability / data-readiness / Engineering Grounding`，每轴三态 `OK / CONSTRAINED / BLOCKED`。**任一轴 BLOCKED → MCTS 前直接淘汰**；EG 轴的 BLOCKED 条件是「≥3 个子维度 = 0」（1–2 个只允许生成 AI Mitigation Plan，不淘汰）。

### 5.3 MCTS 4 轮与增量优化

| 轮 | 动作 |
|---|---|
| R1 Expansion | 8–12 root，按 6 轴打分 |
| R2 Selection+Simulation | 只对 borderline(0.4–0.6) 重打分；PASS(≥0.6) 轻量复核；FAIL(<0.4) 不重算；轻量推导草图验证 SymPy 能否闭环 |
| R3 Backpropagation | ≥0.6 提升，<0.4 拒绝，borderline 生成 2–3 个 child 再评分 |
| R4 Final | 选 top 1–3 写入 `FINAL_PROPOSAL.md`，人择其一 |

orchestrator 的增量 MCTS 把 4 轮压到约 2.5 轮等价（节省 40%）。

### 5.4 v6.0 gap anchoring（最关键的新增）

- 每个存活节点分配 `gap_anchor` = `GAP_REPORT.md` 里的 gap-id；
- `exploratory` 槽**每轮上限 2 个**（保留偶然性但不淹没链条）；
- 既无 gap-id 又无正当 exploratory 理由 → **relevance 轴封顶 0.5**，数学上无法达到 0.6 提升线；
- 所有锚定/重锚定决策追加到 `GAP_ANCHOR_LOG.md`；
- 广搜 WARN 或文献为空 → 锚定标 `pending-literature` 并如实记录，**禁止静默降级成猜测**。

### 5.5 Type-A / Type-B 解耦（v3.1，防「LLM 凭口味枪毙可行方案」）

| 层 | 内容 | LLM 成本 | 判定 |
|---|---|---|---|
| **Type-A** | GPU VRAM 估计（×1.5 安全系数 vs 可用显存）、数据源可达、依赖可导入、代码 AST 语法 | **0** | 确定性脚本；任一 FAIL 直接淘汰，`reason_code=type_a_*` |
| **Type-B** | Novelty / Soundness / Impact 加权多维权评 | LLM | 仅 Type-A PASS 后才进入 Phase 2.5 / 3 |

四个 `reason_code`：`type_a_gpu_oom_estimated` / `type_a_missing_data_source` / `type_a_missing_dependency` / `type_a_code_syntax_error`。

### 5.6 反垃圾 idea 的 6 个必填字段

`insight`（科学洞见，非「用了什么技术」）/ `novelty_delta`（相对最近 1–2 篇的具体差异）/ `falsifiable_claim`（什么结果会证伪）/ `mechanism`（机理因果链）/ `boundary`（何时失效）/ `gap_anchor`。任一命中 garbage signal → MCTS 前淘汰；人工检查点前再做二次自检，不合格回 Step 2 重生成（上限 1 轮）。

### 5.7 BA（Backtracking-After）

三种触发：① 6c 全量 FAIL 但 toy 曾 PASS；② Phase 8 logic FATAL「实验数据与推导结论矛盾」；③ Phase 14 kill-argument 成立。执行：写 `BA_EVENT.json` → 回 Phase 2，Round 1 排除原 idea 及其子树，Round 2 允许「显式否定原假设」的新候选 → 2 轮仍无合格 idea → `BLOCKED + BA_EXHAUSTED`。

> **BA ≠ in-phase fallback**：前者是「idea 本身错了」回 Phase 2（2 轮），后者是「执行出错」回相邻阶段（3 轮）。toy FAIL 属于后者（kill idea，不回 Phase 2）。

---

## 6. 运用了哪些关键知识节点

| 节点（类） | 关键属性 | 关系 |
|---|---|---|
| `ProblemAnchor`（Q-id） | `problem_id`, INV-G1 内容哈希 | `ROOT_OF →` `IdeaDAG` |
| `IdeaNode` | `id`, `perspective`, `framing`, `insight`, `novelty_delta`, `falsifiable_claim`, `mechanism`, `boundary`, `gap_anchor`, `6-axis scores`, `eg_average` | `DEPENDS_ON →` `IdeaNode`（DAG 无环）；`PROMOTED_TO →` `FinalProposal` |
| `Gap` | `gap_id`, `statement`, `citation_tokens`, `discriminator` | `ANCHORS →` `IdeaNode`；`FROM →` `GAP_REPORT.md` |
| `ExploratorySlot` | `justification`, `cap=2/round` | `SUBSTITUTE_FOR →` `Gap` |
| `MCTSRound` | `round_no`, `nodes_scored`, `promotions`, `rejections`, `children` | `REFINES →` `IdeaNode` |
| `TypeASpec` | `requires_gpu_gb`, `requires_packages[]`, `data_required`, `data_sources[]`, `code_snippet` | `GATES →` `IdeaNode`（零成本机械判定） |
| `FailedIdea` | `id`, `description`, `reason` | `TFIDF_SIMILARITY →` `IdeaNode`（>0.78 硬拒） |
| `RunPreprint` / `Lesson` | `gap_ids`, `fired_kill_arguments`, `failure_notes`, `what_worked`, `avoid` | `PRIOR_FOR →` `IdeaNode`；`hard_excludes →` Phase 6b |
| `BAEvent` | `triggered_by`, `original_idea_id`, `failed_evidence[]`, `reason` | `TRIGGERS →` `IdeaRegeneration`（≤2 轮） |
| `DomainProfile` | `method_frequencies{}` | `WEIGHTS →` 4 视角 |
| `FinalProposal` | `problem_anchor`, `selected_idea`, `rejected_alternatives[]`, `mcts_evidence` | `CONSUMED_BY →` `MethodRegistry` / `TheoryDerivation` / `InvariantCheck` |

---

## 7. 对应 `scripts/` 代码

### 7.1 `scripts/gap_gate.py` —— v6.0 gap chain 的硬门（S27）

这是「文献优先」从口号变成机器判定的地方。全文 84 行、纯 stdlib：

| 元素 | 代码 |
|---|---|
| gap-id 词法 | `GAP_ID = re.compile(r"(GAP-\d+\|#gap-[\w-]+\|\[GAP:?\s*\d+\])", re.I)`（L31） |
| 引用词法 | `CITATION = re.compile(r"(\[@[\w:-]+\]\|\[[A-Z][\w-]*,\s*\d{4}\]\|\b[A-Z][a-z]+(?: et al\.?)? \d{4}\b\|\(\d{4}\))")`（L32） |
| 判别动词词表 | `contradict / inconsistent / unsolved / not studied... / absence of / no study... / remains open / fail to explain / discrepancy / untested / not reported`（L33-37） |
| effort 门槛 | `MIN_GAPS = {"lite":1, "balanced":2, "max":3, "beast":4}`（L38），读 `SCIFORGE_EFFORT` |
| 逐块校验 | `blocks = re.split(r"\n(?=(?:GAP-\d+\|## GAP\|#gap-))", text)`；每个含 gap-id 的**块必须单独带引用**，否则报 `gap block(s) without citations`（L55-59） |
| 退出码 | `0 = PASS`，`2 = FAIL`（L63-80）；缺文件直接 FAIL 并提示「Phase 4broad broad-wave must produce GAP_REPORT.md before ideation anchors」 |

**语义**：一个「gap」若没有引用就是意见；若没有判别性动词（如「more research is needed」）就不能驱动真实选题。这正好补上了 LLM 最容易幻觉的环节。

### 7.2 `scripts/dep_gate.py` —— Type-A 的「依赖可导入」判定

全文 122 行，核心：

- 单一真相源 `kernel/config/dependencies.json`，`_allowed_roots()` 收集各 tier 的 root（L42-50）；
- `ast.parse` 遍历 `src/**.py` 与 `figures/**/render.py` 的所有 `Import` / `ImportFrom`，取根包名（L53-68）；
- `sys.stdlib_module_names` 自动放行标准库（L39）；
- `always_forbidden` roots（pip/setuptools）即便在 tier 里也 FAIL（L82-84）；
- 未声明 import → `violations` → `exit 2`（L109-113）。

> 脚本 docstring 明确分工：`dep_gate` 管 **import 什么**，`security_scan.py` 管 **代码怎么行为**（网络 / 凭证 / 破坏性操作）。二者加上 supply-chain = 完整依赖故事。

### 7.3 `scripts/detect_device.py` —— Type-A 的 GPU VRAM 判定

为 `requires_gpu_gb × 1.5 vs available VRAM` 提供设备侧事实；对应 `type_a_gpu_oom_estimated`。

### 7.4 `scripts/security_scan.py` —— AST 语法 + 行为扫描

对应 `type_a_code_syntax_error`；`dep_gate` 遇到 `SyntaxError` 会跳过（`security_scan already flags unparseable`），两脚本职责不重叠。

### 7.5 `scripts/s2_ladder_gate.py` / `s2_ablation_gate.py`

不直接约束 Phase 2，但构成 idea 后续「subset→full ladder / ablation ledger」的可证伪性基础；BA 触发时由 `STATUS.json` 与它们联动。

---

## 8. 产物与契约

| 产物 | 位置 | 消费者 |
|---|---|---|
| `IDEA_CANDIDATES.md` | `.sciforge/refine-logs/` | 人 / novelty-check |
| `IDEA_DAG.json` | 同上 | novelty-check（唯一输入） |
| `IDEA_DAG_VISUAL.md` | 同上 | 人（Mermaid，每轮更新） |
| `MCTS_LOG.md` | 同上 | 审计 / BA |
| `GAP_ANCHOR_LOG.md` | 同上 | novelty-check / auto-review-loop |
| `FINAL_PROPOSAL.md` | 同上 | method-registry / theory-derivation / invariant-check |
| `failed_ideas.json` | 同上 | 反重复记忆 |
| `BA_EVENT.json` | `.sciforge/verdicts/` | BA 回溯 |

---

## 9. 边界与反模式

- ❌ 文献没读完就给最终 PASS/BLOCKED；❌ 无 gap-id 仍提升 idea
- ❌ 用 demo/pilot 实验顶替 0-promoted 的降级
- ❌ 让 LLM 在预筛阶段以主观口味淘汰可行方案（Type-A 必须零 LLM）
- ❌ 学科专用框定；❌ 少于 4 轮 MCTS 就定案；❌ agent 自选最终 idea
- ❌ 把「toy FAIL」误当 BA（应 kill idea，不回 Phase 2）
- ✅ 一切锚定/重锚定留痕；未读到文献时如实 `pending-literature`

---

## 10. 对「分子算法设计」应用层本体的可迁移点

1. **gap-id 作为一等节点**：把 `GAP_REPORT.md` 的每条 gap 建成 `ResearchGap` 节点并带 `citation_tokens` + `discriminator`，idea 必须有 `ANCHORS` 边 —— 这与 capfactory 的 `ResearchQuestion / ClaimAnchor` 可直接对接。
2. **零成本硬筛先行**：分子设计里 `requires_gpu_gb` / 数据集是否可下载 / `rdkit`/`torch_geometric` 是否已声明，先由脚本判定，再让模型谈新颖性。这正好复用上一轮 GGR 的 `TRAIN_FEASIBILITY` 思路。
3. **机理字段强制化**：`mechanism` + `falsifiable_claim` + `boundary` 可直接映射为 `Mechanism` / `Claim` / `ApplicabilityBoundary` 节点，是后续 `SAU` 编译的天然输入。
4. **跨 run 记忆**：`RUN_PREPRINT.md` / `LESSONS.json` 与 capfactory 的 lineage / provenance 是同构的，只是粒度从「论文谱系」变成「自身实验史」。
