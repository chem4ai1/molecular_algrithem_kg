# S2 · 26 阶段编排前半（阶段 0–5）与 `compile_paperspec()`

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 把 SciForge 前 11 个阶段落地为确定性图编译 + 4 个动态应用类 + 阶段门，产出幂等 `PaperSpec` |
| 依赖 | S0（注册表 / 等价闸门）、S1（缓存 / 提案 / 对齐 / 验证） |
| 上游文档 | `../SCIFORGE_INTEGRATION_BLUEPRINT.md` §5（26 行映射表）、§9 P2；`docs/skills/05-orchestrator/auto-pipeline-guide.md` §2 |
| 覆盖阶段 | `0 → 1 → 1a → 1b → 4broad → 2 → 2.5 → 2.5b → 3 → 4targeted → 5`（11 个） |
| 周期建议 | 6–7 个工作日 |
| 一句话验收 | `compile_paperspec()` 连续两次 `spec_hash` 相同；全程零 LLM 编译；4 个动态类在 `registry.json` 里 `status=active` |
| 硬门 | H6（+ H1/H2/H5 不退化） |

---

## 1. 后端设计

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/paperapp/paperspec.py` | `PaperSpec` dataclass + `compile_paperspec(graph, paper_id)` + `compute_hash()` |
| 新建 | `src/capfactory/paperapp/phasegraph.json` | 26 节点 DAG（本阶段先填 11 个 `reads/produces/gate`） |
| 新建 | `src/capfactory/paperapp/gates.py` | 6 态 verdict 封装（复用 `sciforge/contracts.py::VERDICT_STATES/validate_verdict()`） |
| 新建 | `src/capfactory/paperapp/runner.py` | 阶段分发骨架（本阶段支持 `stage=N` 单跑与 `stage=all` 前半链） |
| 新建 | `src/capfactory/paperapp/miners/__init__.py` | 4 个 miner 注册 |
| 新建 | `.../miners/domain_miner.py` | 阶段 1b：`DomainProfile` + `EvidenceNormProfile` |
| 新建 | `.../miners/gap_miner.py` | 阶段 4broad：`ResearchGap`（gap-id / 引用 / 判别动词三正则） |
| 新建 | `.../miners/idea_miner.py` | 阶段 2：`IdeaNode` / `IdeaDAG` / `MCTSRound` |
| 新建 | `.../miners/verdict_miner.py` | 阶段 2.5/3/5：`GateVerdict`（6 态） |
| 新建 | `src/capfactory/web/static/paperapp_timeline.html` | 前半时间线页 |
| 新建 | `tests/test_paperapp_s2.py` | §6 的 18 项 |
| 修改 | `src/capfactory/web/paperapp_api.py` | 追加 `/api/v10/paperapp/spec*`、`/stages*`、`/runs*` |
| 修改 | `src/capfactory/paperapp/cli.py` | `run --stage`、`debug-stage`、`spec-show`、`audit-gates` |
| 修改 | `src/capfactory/paperapp/registry.py` | 预置 4 个类注册项（**通过 `register_class()` 走正常流程，不直接改 JSON**） |
| 修改 | `src/capfactory/config.yaml` | `paperapp.pipeline:` 段（effort、stage 白名单、max_debug_tries） |
| 修改 | `src/capfactory/po/vocab.py` | `PAPERAPP_CLASS_VOCAB` 补齐 4 个正式类 |

### 1.2 四个动态类（S2 只注册这 4 个）

| 类 | parent_class | producer_stage | 关键字段 | id_template |
|---|---|---|---|---|
| `DomainProfile` | `ResearchQuestion` | `1b` | `evidence_type, reasoning_paradigm, learning_confidence, evidence_norm_profile` | `appdomain:<arxiv>:<slug>` |
| `ResearchGap` | `ResearchQuestion` | `4broad` | `gap_id, gap_type, statement, evidence_ids, priority` | `appgap:<arxiv>:<slug>` |
| `IdeaNode` | `Algorithm` | `2` | `perspective, six_axis, insight, novelty_delta, falsifiable_claim, mechanism, boundary, gap_anchor` | `appidea:<arxiv>:<slug>` |
| `GateVerdict` | `EvaluationResult`（运行时类） | `2.5/3/5` | `stage, state, reason_code, evidence_ids, run_id` | `appverdict:<run>:<stage>` |

> `DomainProfile` 是**单一写入者**：只有阶段 1b 能写，1a 的 hint 只入 `node_cache/proposals/` 且 `status=proposed`，与 SciForge `domain-signature` 约束一致。

### 1.3 `PaperSpec` 数据结构

```python
@dataclass
class PaperSpec:
    paper_id: str
    arxiv_id: str
    spec_hash: str
    semantic_sha: str                 # 语义层图 sha
    dynamic_tbox_version: str
    domain_profile: dict | None
    gaps: list[dict]
    ideas: list[dict]
    frontier: list[dict]
    method_lock: dict | None
    stage_order: list[str]            # 11 个阶段 id
    verdicts: dict[str, str]          # stage -> 6 态
    warnings: list[str]
    def compute_hash(self) -> str: ...   # 全字段 sort_keys + sha256
    def save(self, out_dir) -> str: ...  # REPRO_SPEC.json 风格：PAPER_SPEC.json
    def load(cls, path): ...
```

`compile_paperspec(graph, paper_id)` **纯确定性**：只读 `POGraph`、按 `registry.active_classes()` 过滤、按 id 排序、按 `spec_hash` 幂等；**不调用 LLM**。LLM 只用于产生 S1 的提案，提案被 `registered` 后才进图，再由编译器读图。

### 1.4 `phasegraph.json` 前 11 节点（示例 3 条）

```json
{"schema_version":"1.0","stages":[
 {"id":"0","name":"冻结 Q-id","mode":"MUST","reads":["problem"],
  "produces":["RUN_BUDGET.json","ProblemAnchor"],"gate":"inv_g1","next":["1"]},
 {"id":"4broad","name":"文献广搜","mode":"MUST","reads":["domain-signature.json","references.bib"],
  "produces":["GAP_REPORT.md","ResearchGap"],"gate":"gap_gate","next":["2"]},
 {"id":"2","name":"idea-discovery","mode":"MUST",
  "reads":["GAP_REPORT.md","domain-signature.json","IDEA_DAG.json"],
  "produces":["IDEA_DAG.json","IdeaNode","MCTSRound"],
  "gate":"type_a+gap_anchor+mcts>=4","next":["2.5"]}
]}
```

其余 8 条同样结构（`1`, `1a`, `1b`, `2.5`, `2.5b`, `3`, `4targeted`, `5`）。`validate_phasegraph()` 检查：无环、每条 `gate` 在 `gates.py` 有实现、每个 `produces` 有对应产物写手。

### 1.5 `gates.py`（复用项目已有 6 态）

```python
from ..sciforge.contracts import VERDICT_STATES, validate_verdict, verdict

def emit(stage, state, *, artifacts=(), reason_code="", evidence_ids=()) -> dict:
    d = verdict(state, artifacts=artifacts, reason_code=reason_code)
    d["stage"] = stage; d["evidence_ids"] = list(evidence_ids)
    problems = validate_verdict(d, strict=False)
    if problems: raise ValueError(f"invalid verdict: {problems}")
    return d
```

**不做第二套 verdict**。所有阶段门返回这 6 态之一，`NOT_APPLICABLE` 必须写文件为证（不是静默 skip）。

### 1.6 阶段 0–5 的门定义

| 阶段 | 门 | 判据 | FAIL 去向 |
|---|---|---|---|
| 0 | `inv_g1` | Q-id 明确且内容哈希可算 | 交人（BLOCKED） |
| 1 | `rep_plan_present` | `REP.json` 含 11 个阶段 id 与 fallback 条件 | 回 1 重建 |
| 1a | `hint_only` | hint 只写 `node_cache/proposals/`，不写图 | WARN 继续 |
| 1b | `learning_confidence>=0.7` | 单一写入者 | 默认 general + WARN |
| 4broad | `gap_gate` | gap-id 正则 + 逐块引用 + 判别动词（照 SciForge `gap_gate.py`） | 回 4broad 重检索（≤3 轮） |
| 2 | `type_a + gap_anchor + mcts>=4` | Type-A 四项零 LLM、promoted idea 有 gap-id、≥4 轮 MCTS | 无 idea → BLOCKED |
| 2.5 | `falsifiable` | ≥1 次反例尝试 + 假设健康 | WEAKENED → L1 回 2 |
| 2.5b | `eg_dimensions` | EG 8 子维，0 值 < 3 | 淘汰该 idea |
| 3 | `novelty_converge` | 复合分 ≥0.6 且至多 1 survivor | 无 survivor → L3 放宽重评 1 轮 |
| 4targeted | `collision_precheck` | 每个 survivor 一次定向检索 + 碰撞日志 | 回 4targeted |
| 5 | `hash_lock` | 方法注册表 §3 SHA256 锁定 | 漂移 → L4 重建（≤3 轮） |

---

## 2. 构建步骤（Step 1–12）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | `phasegraph.json` 写全 26 个 id（后半先标 `enabled=false`）+ `validate_phasegraph()` | 无环；`gate` 名与 `gates.py` 对照表一致 |
| 2 | `po/vocab.py` 补齐 4 类；`registry.register_class()` 预置 4 项 | `active_classes("generation")` 恰好 4 个 |
| 3 | `paperspec.py` dataclass + `compute_hash/save/load` | 连续两次 `spec_hash` 相同（T-S2-02） |
| 4 | `compile_paperspec()` 只读图编译 | 输出 `stage_order` 11 个；`warnings` 如实记录缺证据项 |
| 5 | `gates.py` 封装 6 态 + `validate_verdict` | 非法 state → `ValueError`（T-S2-04） |
| 6 | `miners/domain_miner.py`：从 `Paper` 集合与 `Evidence` 抽 `DomainProfile` | 只写一次；第二次调用是 no-op（单一写入者） |
| 7 | `miners/gap_miner.py`：三正则（gap-id / citation / discriminator） | 每个 gap 至少 1 个已验证 cite key（T-S2-06） |
| 8 | `miners/idea_miner.py`：DAG 无环校验 + 6 轴 + MCTS 4 轮计数 | 有环 → 降级 `required=False` 并 warning |
| 9 | `miners/verdict_miner.py`：把阶段门结果写成 `GateVerdict` 节点 | 每个阶段恰好 1 个 verdict 节点 |
| 10 | `runner.py`：`run --stage 4broad` 单跑 + `events.ndjson` 追加 | 事件可 `replay()` 重现同一状态 |
| 11 | `paperapp_api` 追加 5 个 API + `paperapp_timeline.html` | `/api/v10/paperapp/stages` 返回 11 个启用阶段 |
| 12 | `smoke.sh` 追加 3 项；全量回归 + H6 | 见 §7 |

---

## 3. 修正清单

| # | 坑 / 触发信号 | 修法 | 回归 |
|---:|---|---|---|
| C1 | 阶段编号 `4broad` 排在 `2` 前面，用数字排序会错 | `stage_order` 显式列表，禁止 `sorted()` 数字排序 | T-S2-01 |
| C2 | `compile_paperspec` 里混入 LLM 结果 → 不幂等 | 编译器只读 `POGraph`；LLM 输出先经 S1 提案缓存与注册 | T-S2-02/03 |
| C3 | 1a hint 被下游直接消费 | hint 只入 `proposals/`，`compile_paperspec` 只认 `registered` 的 `DomainProfile` | T-S2-05 |
| C4 | 自造 6 态词汇，与 `sciforge/contracts.py` 分叉 | 直接 import `VERDICT_STATES/validate_verdict` | T-S2-04 |
| C5 | `gap_gate` 只查整篇引用，漏掉「某块 gap 无引用」 | 按 gap 块逐块检查（照 SciForge `gap_gate.py` 的 `re.split`） | T-S2-06 |
| C6 | 跨论文模块混入本篇 idea（GGR 实测问题） | `IdeaNode` 生成时按 `paper_id` 命名空间过滤；`canonical_id` 带 arxiv | T-S2-08 |
| C7 | `inputs/outputs` 中文词元被拆成单字造伪数据流 | 复用 `reprospec/compiler.py::_as_list()` 思路，字符串整体作词元 | T-S2-09 |
| C8 | `runner` 写图 | 只写 run 目录与 `node_cache/`；图写入统一交 S4 `materialize` | T-S2-10 |
| C9 | `events.ndjson` 与 `RUNSTATE` 双写不一致 | events 是 durable truth，RUNSTATE 由 `replay()` 派生 | T-S2-11 |
| C10 | 前端时间线把 26 阶段一次渲染卡顿 | 只渲染启用的 11 个；S3 再加其余 | S5 性能项 |

---

## 4. 前端相应设计（前半时间线）

### 4.1 页面 `/paperapp/timeline`（`paperapp_timeline.html`）

| 区域 | 数据源 | 展示 |
|---|---|---|
| 顶部汇总 | `/api/v10/paperapp/status` + `/spec` | paper_id、`spec_hash` 短码、`dynamic_tbox_version`、11/26 阶段启用数 |
| 时间线 | `/api/v10/paperapp/stages` | 11 个阶段卡片：id / 名称 / mode 徽章 / verdict 6 态色 / `n_in` / `n_out` / 耗时 |
| 单阶段抽屉 | `/api/v10/paperapp/stages/{id}?run=<run_id>` | `reads[]` / `produces[]` 文件名 + 每文件存在性 / gate 判据 / verdict 详情 / `events` 最近 20 条 |
| PaperSpec | `/api/v10/paperapp/spec?arxiv=<aid>` | 可折叠 JSON（`domain_profile / gaps / ideas / frontier / stage_order / verdicts / warnings`） |
| 门审计 | `/api/v10/paperapp/gates/audit` | 缺 verdict 的阶段列表、`NOT_APPLICABLE` 是否有文件为证 |

### 4.2 API 契约

| 路径 | 方法 | 200 | 错误/空态 |
|---|---|---|---|
| `/api/v10/paperapp/stages` | GET | `{stages:[...], enabled:11, total:26}` | — |
| `/api/v10/paperapp/stages/{id}?run=` | GET | `{stage, reads, produces, gate, verdict, events[], files_status{}}` | 未跑 → `{verdict:null, events:[]}`（不是 404） |
| `/api/v10/paperapp/spec?arxiv=` | GET | 完整 `PaperSpec` | 未编译 → 404 `{reason_code:"spec_not_built"}` |
| `/api/v10/paperapp/runs` | GET | `{runs:[{run_id, arxiv, started_at, status, last_stage}]}` | 空 → `runs:[]` |
| `/api/v10/paperapp/gates/audit` | GET | `{ok, missing:[], not_applicable_without_file:[], validate_verdict_issues:[]}` | — |
| `/api/v10/paperapp/run` | POST | `{run_id, stages_completed:[], verdicts:{}}` | `stage` 非法 → 400 |

### 4.3 状态与交互

- 6 态色映射：`PASS`=ok 绿、`WARN`=warn 橙、`FAIL/NOT_APPLICABLE`=acc 蓝灰、`BLOCKED/ERROR`=bad 红、未跑=mut；
- 点阶段卡片 → 抽屉；抽屉里「重跑此阶段」按钮 → `POST /run {"stage": id}`，完成后局部刷新该卡片（不整页重载）；
- `spec_hash` 附复制按钮；「重新编译」按钮 → 显示前后 hash 是否一致（幂等可视化）；
- 空态：未跑阶段显示 `未运行`（不是空白卡片）；错误态：抽屉显示 `reason_code` 与 traceback 首 5 行；
- 所有 `fetch` 用 `allSettled`，单面板失败不影响时间线。

### 4.4 与 S0/S1 页面的关系

S0 状态页与 S1 缓存页保持独立 URL；S5 统一用顶部 tab 收拢。本阶段**不重复实现**缓存面板。

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `phasegraph.json` | Step 1 | 时间线卡片顺序 | `python3 -m capfactory.paperapp.cli stages` | — | 26 id、11 enabled、无环 | 数字排序错乱 | C1 |
| 2 | 4 个 active 类 | Step 2 | `/registry` 面板 | `cli registry-audit` | `class_registered` ×4 | `active_classes==4` | 类未 active 却有 IdeaNode | C3 |
| 3 | `PAPER_SPEC.json` | 每次编译 | PaperSpec 面板 | `cli spec-show --arxiv 2411.06608` | `spec_compiled` | 两次 `spec_hash` 相同 | hash 漂移 | C2 |
| 4 | `DomainProfile` | 1b | spec 折叠区 | `cli debug-stage --stage 1b` | `domain_written` | 恰好 1 个节点 | 出现 2 个 | 单一写入者被破坏 |
| 5 | `domain-signature-hint` 提案 | 1a | 缓存浏览器 L2 | `cli debug-key --stage 1a` | `proposal_created` | `status=proposed` | 出现在 spec 里 | C3 |
| 6 | `GAP_REPORT.md` + `ResearchGap` | 4broad | 阶段抽屉 | `cli debug-stage --stage 4broad` | `gap_gate_checked` | 每块有引用 | `unsupported gap` | C5 |
| 7 | `IDEA_DAG.json` | 2 | 阶段抽屉 | `cli debug-stage --stage 2` | `mcts_round` ×4 | 无环、`required` 数合理 | 出现跨论文模块 | C6 |
| 8 | `FALSIFICATION_RECORD.json` | 2.5 | 门审计面板 | `cli audit-gates` | `falsification_attempted` | ≥1 次反例 | 缺失 | 回 2.5 |
| 9 | `FRONTIER_MAP.json` / `survivor` | 3 | PaperSpec `frontier` | `cli debug-stage --stage 3` | `novelty_converged` | 至多 1 survivor | 多个 survivor | L3 重评 |
| 10 | `METHOD_REGISTRY` hash | 5 | 阶段抽屉 | `cli debug-stage --stage 5` | `hash_locked` | sha 可复算 | 漂移 | L4 重建 |
| 11 | `GateVerdict` 节点 | 每阶段结束 | 卡片徽章 | `cli audit-gates` | `verdict_emitted` | 11 个阶段各 1 个 | 缺/重复 | C4 |
| 12 | `events.ndjson` | 每步 | 抽屉最近 20 条 | `cat storage/sciforge/paperapp/<run>/events.ndjson \| tail -20` | 全部步骤 | `replay()` 能重现 | 与 RUNSTATE 不一致 | C9 |
| 13 | `RUNSTATE.json` | 每边界 | 顶部汇总 | `cli status --run <run_id>` | `state_saved` | 派生自 events | 被手改 | 用 replay 重建 |
| 14 | 前半 run 产物目录 | run 结束 | `/runs` 列表 | `ls storage/sciforge/paperapp/<run>/` | — | 每阶段至少 1 文件 | 空目录 | 检查写手 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S2-01 | 单元 | `validate_phasegraph` | 26 id、无环、`4broad` 在 `2` 前 |
| T-S2-02 | 集成 | **spec 幂等 H6** | 连续两次 `compile_paperspec().spec_hash` 相同 |
| T-S2-03 | 集成 | 零 LLM 编译 | 注入会抛异常的 `call_llm`，编译仍成功 |
| T-S2-04 | 单元 | 6 态封装 | 非法 state → ValueError；合法 → `validate_verdict()==[]` |
| T-S2-05 | 集成 | 1a hint 隔离 | hint 不出现在 `PaperSpec.domain_profile` |
| T-S2-06 | 单元 | gap_gate 逐块引用 | 3 个 gap 块其中 1 块无引用 → BLOCKED |
| T-S2-07 | 单元 | gap 判别动词 | 「more research is needed」被拒 |
| T-S2-08 | 单元 | 跨论文模块过滤 | `2608.06956` 模块不进本篇 `IdeaNode` |
| T-S2-09 | 单元 | 中文词元 | `"完整分子结构"` 不被拆成单字 |
| T-S2-10 | 集成 | runner 不写图 | run 前后 `app_generation.json` sha 不变 |
| T-S2-11 | 集成 | events 重放 | `replay(events) == RUNSTATE` |
| T-S2-12 | 单元 | 单一写入者 | 1b 调用两次只产生 1 个 `DomainProfile` |
| T-S2-13 | 单元 | MCTS ≥4 | 少于 4 轮 → verdict=BLOCKED |
| T-S2-14 | 单元 | 环降级 | 环内 idea `required=False` + warning |
| T-S2-15 | 单元 | `NOT_APPLICABLE` 有文件 | 无文件 → `audit-gates` 报错 |
| T-S2-16 | API | 6 个端点 | 200 + 空态正确；`/run` 非法 stage → 400 |
| T-S2-17 | 前端 | 时间线渲染 | 11 卡片、6 态色、空态「未运行」 |
| T-S2-18 | 回归 | 全量 | 8 既有 + S0 12 + S1 20 + S2 18 全过 |

**夹具**：`tests/fixtures/paperapp_s2/` 放 1 篇论文的最小语义图（Paper + 2 AlgorithmModule + 2 SourcePaper + 1 Benchmark）、`GAP_REPORT.md` 三块样例、`IDEA_DAG.json` 含 1 个环。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s2 -v
PYTHONPATH=src python3 -m capfactory.paperapp.cli run --arxiv 2411.06608 --stage 4broad
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-gates
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. 验收标准（签字表）

### 7.1 硬门

| 门 | 判据 | 实测值 |
|---|---|---|
| H6 spec 幂等 | 两次 `spec_hash` 相同；注入异常 LLM 仍成功 | `______` |
| H1/H2/H5 不退化 | 语义层 sha 不变；`verify_rebuild` ok；隔离审计 0 | `______` |
| H9 API 注册 | 6 个新端点无注册错误 | `______` |
| H11 回归 | 58 项累计全过 | `____/____` |

### 7.2 指标

| 指标 | 目标 |
|---|---|
| `compile_paperspec` 耗时（全量 6001 节点） | < 15 s |
| 前半 11 阶段单 run 事件数 | 30–80（过少说明漏记，过多说明重复） |
| `GateVerdict` 覆盖率 | 11/11 阶段各 1 个，6 态合法 |
| `NOT_APPLICABLE` 有文件为证 | 100% |

### 7.3 退出条件与人工签字

- 交付 11 个阶段产物样例、`PAPER_SPEC.json`、18 项测试结果、时间线截图；
- **人工签字项**：确认 `phasegraph.json` 里后 15 个阶段仍 `enabled=false`；确认 `runner` 未写任何图文件；确认 `spec_hash` 可复算；
- 硬门不过 → 不得进入 S3。

---

## 8. 交付物与回滚

**交付**：11 个新文件 + 5 个修改文件 + `tests/test_paperapp_s2.py` + 夹具 + `docs/plan/S2_PIPELINE_FRONT_REPORT.md`。

**回滚**：
1. git 恢复 5 个修改文件；`phasegraph.json` 归档到 `storage/sciforge/_archive_s2/`；
2. S2 注册的 4 个类标 `status=deprecated` + `valid_to`（**不删除**，保留审计链）；
3. run 产物保留在 `paperapp/<run_id>/` 供排查；
4. 重跑 `bash scripts/smoke.sh` 回到 S1 的 15/15。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| `PaperSpec` / `spec_hash` | S3 后半阶段的输入锚、S4 回写校验、S5 spec 面板 |
| `phasegraph.json` 后 15 节点 | S3 填充 `enabled=true` 与 gate |
| `runner.py` 骨架 | S3 扩到全 26 阶段 + 回退 L1–L13 |
| `gates.py` 6 态封装 | S3/S4/S6 所有门与审计 |
| `events.ndjson` | S4 回写依据、S5 事件面板、S6 崩溃恢复 |
| 时间线页 | S3 扩成 26 卡片；S5 整合为「编排」tab |
