# 指导 · 实验阶梯、执行与消融（3 个 support skill）

> **覆盖**：`experiment-ladder`(75) · `experiment-execution`(647，最长) · `ablation-planner`(81)
> **DAG 位置**：Phase 6b / 6c → Phase 10；三个 skill 分别被 `s2_ladder` / `budget_floor` / `s2_ablation` 边界门强制。

---

## 1. 三者如何串成一条证据链

```
METHOD_REGISTRY.md + EXPERIMENT_MATRIX.json
   ↓
experiment-execution (toy)  ── RESULT.json + .SMOKE.json ──► toy gate
   ↓ PASS
experiment-ladder (subset → full) ── S2_LADDER.json ──► 6c 边界 s2_ladder 门
   ↓ GOOD + strict full-set improvement
experiment-execution (full, background) ── DISPATCH/STATUS/RESULT ──► budget_floor + s2_ablation
   ↓
ablation-planner (5–6 plans + AblCritic) ── ABLATION_LEDGER.json ──► Phase 10 s2_ablation 门
   ↓
result-to-claim
```

> 三者产物都在 `.sciforge/audits/`（`S2_LADDER.json` / `ABLATION_LEDGER.json`）或 `experiments/`，属于**未注册类**：不受 `validate_verdicts.py` 扫描，改由 `scripts/s2_ladder_gate.py` / `s2_ablation_gate.py` / `smoke_gate.py` 硬查。别把它们搬进 `.sciforge/verdicts/`。

---

## 2. `experiment-execution`（647 行，Phase 6b toy + 6c full）

| 项 | 内容 |
|---|---|
| Purpose | 两段式实验：toy → gate → full 派发到后台 |
| 输入 | `FINAL_PROPOSAL.md`（选定 idea）、`domain-signature.json`、`METHOD_REGISTRY.md`、`.sciforge/DEVICE.json` |
| 输出 | `EXPERIMENT_REPORT.md`（toy）、`FULL_EXPERIMENT_DISPATCH.json`、`DISPATCH.json`、`STATUS.json`、`RESULT.json`、`.SMOKE.json`、`.sciforge/DEVICE.json`、`experiments/*/README.md/INDEX.md` |
| 关键 | 两阶段 + **async dispatch** + 学科无关；v3.2 代理自动挂载 |

### 2.1 执行前必须过的三道门（顺序不能反）

| 顺序 | 门 | 脚本 | 作用 |
|---|---|---|---|
| 1 | 依赖声明 | `dep_gate.py` | 所有 import root 必须在 `dependencies.json`；标准库自动放行 |
| 2 | 静态安全 | `security_scan.py` | full-mode 脚本是 agent 写的、直接跑宿主，**必须在 smoke 之前**静态扫描（`ast.walk` + 正则，不执行代码） |
| 3 | 冒烟 | `smoke_gate.py` | 每个 `DISPATCH.json/STATUS.json` 组必须有同级 `{id}.SMOKE.json` 且 `smoke_result=PASS`；**smoke 时间晚于最后一次 STATUS 更新 → WARN**（说明脚本在 smoke 之后被改） |

> `smoke_gate.py` 的契约原话：「a full dispatch that completes without first writing `.SMOKE.json` is invalid regardless of whether the experiment ultimately succeeded」。它来自真实事故：Q-SGD-BS-GAP 跑了 184 秒却没有 smoke。

### 2.2 Toy gate（Phase 6b，最难的一条）

- 门：`RESULT.json status=PASS ∧ core_claim_validated=true`；
- **FAIL 判定条件很严**：必须「显著为负 **且** ≥2 seeds 可复现」才触发 `KILL-or-PIVOT`：
  - `PIVOT` → 回 Phase 5 重注册方法并重新 hash lock（**≤2 次**）；
  - `KILL` → 写 `KILL_ARGUMENT.json` → 人工检查点 → 回 Phase 2 换 idea（走 BA，全局 ≤2 轮）；
- `TIMEOUT/ERROR` → 各 1 次重试；`INCONCLUSIVE` → 1 次重设计；
- **toy FAIL ≠ BA**：这是 kill idea（in-phase），不是「idea 本身错了」的回 Phase 2。混淆会导致 BA 预算被误消耗。

### 2.3 Full gate（Phase 6c）

必须同时满足：`DISPATCH.json` 生成 + 后台进程启动确认 + **`budget_floor.satisfied == true`** + `S2_LADDER.json` PASS。

`budget_floor` 五项（`BUDGET_FLOOR.schema.json` 的 fixture 钉死）：`routes_explored`（≥2 或给出否决证据）、`matrix_completion`(100%)、`seed_budget`、`failure_records`、`remaining_budget_declaration`。`completion_justification[]` 每项 `{route, status, evidence}`。

**跨字段硬规则**：`budget_floor.satisfied == false` 时**禁止**写 `verdict: PASS`（只允许 `IN_PROGRESS`/`BLOCKED`）；`PASS` 必须带 `completion_justification`。不满足 → `IN_PROGRESS`，**不得进入 Phase 10**。

### 2.4 时序与后台

- toy 预估 `≤5 min` 前台；`>5 min` 派 `toy_bg` 后台；
- toy verdict 在 **6c dispatch 边界**读；`toy_bg` 仍在跑 → **跳过 6c**（不发 full），继续 Phase 7+ 非实验工作，Phase 10 复查；
- **绝不 busy-wait**；full 强制后台，管线继续 7–16；
- Phase 10 用已完成的 live job 结果并注明 "experiment pending"；
- 数据集/权重下载也走后台派发，**网络问题永不跳过**（`background-dispatch-protocol.md` v2.2）。

### 2.5 设备

`detect_device.py` 按 `nvidia-smi → rocminfo → npu-smi → mps → cpu` 探测并写 `DEVICE.json`；**没有 CPU-first/GPU-first 默认**，由 domain + box 决定。这台机器实测 3×H100，但 torch 因 NCCL 符号错误不可用 —— 实际跑实验前必须先修环境（见 `capfactory/md/FULL_TRAIN_REPRODUCTION_DESIGN.md`）。

---

## 3. `experiment-ladder`（75 行，Phase 6b→6c）

| 项 | 内容 |
|---|---|
| Purpose | 阻止 subset 的偶然好结果变成 claim |
| 输入 | `experiments/subset/**`（baseline + candidate）、`experiments/full/**` |
| 输出 | `.sciforge/audits/S2_LADDER.json` |
| 门 | 6c 边界 `s2_ladder`：实验存在但 ladder 缺失/非法 → **FAIL**；无实验 → SKIP |
| Caps | `ENGINEER ≤2`；**ties 永不算法赢** |

状态机（`kernel/sciforge/s2/ladder.py`）：
```
subset baseline 复现 → 实现 candidate → Critic {BAD | ENGINEER | GOOD}
  BAD      → discard（按 L5/L7 回退，永不 promote）
  ENGINEER → 再调，总轮数 ≤2
  GOOD     → 跑 FULL set（须 fullset.verified=true）
full-set 复验：candidate 必须 STRICTLY 优于 baseline（方向感知）
```
另外声明的 `relative_gain_pct` 必须与重算值差 ≤ **0.15 pp**（算术不一致 = reward-hacking）。

---

## 4. `ablation-planner`（81 行，Phase 10）

| 项 | 内容 |
|---|---|
| Purpose | 「**no claim crosses phase 10 without component-level evidence**」——方法的哪一部分真正挣到了结果？ |
| 输入 | `METHOD_REGISTRY.md`（组件）、`experiments/full/**`（各 arm 结果） |
| 输出 | `.sciforge/audits/ABLATION_LEDGER.json` |
| 门 | Phase 10 `s2_ablation`：有实验却无 ledger → **FAIL** |
| Caps | **5–6 plans**（`SCIFORGE_ABLATION_MIN/MAX` 可给 micro-run 覆盖）；`AblCritic` 是机械的 |

规则：每个 plan `{id, component, hypothesis, metric}`；每个已执行结果由 `ablcritic(prev,new)` 给 `GOOD`（严格更好）/ `REFINE`（保留旧态）；`current_best` 必须等于历史最佳 GOOD，**回归或手改 ledger 直接 FAIL**（单调性）。

---

## 5. 对应脚本速查

| 脚本 | 管什么 |
|---|---|
| `scripts/smoke_gate.py` | `.SMOKE.json` 存在 + PASS + 时间新鲜 |
| `scripts/security_scan.py` | 执行前 AST 静态扫描（不执行代码） |
| `scripts/dep_gate.py` | import 白名单（与 security_scan 分工：一个管 import 什么，一个管代码怎么行为） |
| `scripts/detect_device.py` | `DEVICE.json` |
| `scripts/s2_ladder_gate.py` | 6c 边界 ladder 门 |
| `scripts/s2_ablation_gate.py` | Phase 10 边界消融门 |
| `scripts/s2_integrity_gate.py` | D2 path/download + **D3 frontier-teacher co-occurrence** 恒跑，D1 语义仅在 provider 可用时（内核内 fail-closed） |
| `scripts/s2_audit.py` | Phase 16 gain 算术 / split discipline / method↔code parity ≥80% |
| `scripts/claim_anchor_gate.py` | claim 引用的 `NODES.json` 节点存在且 outputs 哈希未漂移 |

---

## 6. 检查清单

**派发前**
- [ ] `dep_gate` + `security_scan` + smoke 三道门按顺序过
- [ ] `DEVICE.json` 已探测，backend 与代码一致
- [ ] `METHOD_BINDING.md` 处于 LOCKED，`EXPERIMENT_PLAN.md` 与之一致
- [ ] `.SMOKE.json` 已写且 `smoke_result=PASS`

**6b**
- [ ] `RESULT.json` 有 `status` 与 `core_claim_validated`
- [ ] FAIL 满足「显著负 + ≥2 seeds」才 KILL/PIVOT；否则按 TIMEOUT/INCONCLUSIVE 重试
- [ ] PIVOT 计数 ≤2；KILL 有 `KILL_ARGUMENT.json` + 人工检查点

**6c**
- [ ] 后台启动已确认，`DISPATCH.json` + `STATUS.json` 齐全
- [ ] `budget_floor` 五项全绿，否则 `IN_PROGRESS` 且不得进 Phase 10
- [ ] `S2_LADDER.json` Critic=GOOD、`engineer_rounds ≤2`、full-set 严格优于、gain 误差 ≤0.15pp

**Phase 10**
- [ ] `ABLATION_LEDGER.json` 5–6 plans、`current_best` 单调
- [ ] `NODES.json` / `CLAIM_ANCHORS.json` 已自动注册且哈希稳定

---

## 7. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中 `ExperimentMatrix / ExperimentNode / Result / DeviceProfile / SmokeEvidence / TripleHash` 来自本组；`s2_ladder` 与 `s2_ablation` 两个边界门是框架 §8「门速查」的一部分。
GGR 复现层的 `executor.execute_repro()`（subprocess + events + `debug_tries`）、`ladder.run_ladder()`（ties fail、3 态 Critic）、`MINIBATCH_PROBE` 与这里高度同构，可直接互为参照。
