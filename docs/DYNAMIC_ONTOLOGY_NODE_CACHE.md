# 动态本体 · LLM 新节点缓存与增量回写设计

> 版本 1.0 · 2026-11-15
> 配套主文档：[SCIFORGE_INTEGRATION_BLUEPRINT.md](SCIFORGE_INTEGRATION_BLUEPRINT.md)
> 目标：回答「**每次使用结果后，LLM 创建的节点怎么缓存、怎么复用、怎么按步骤新增进图**」，给出可直接编码的数据结构、算法、API 与测试。

---

## 1. 先把「缓存」拆成三个不同的问题

用户口语里的「给 LLM 创建的节点加缓存」实际上混合了三件互相独立的事，混在一起做必然失败：

| # | 问题 | 缓存对象 | 命中条件 | 命中后做什么 |
|---|---|---|---|---|
| Q1 | **幂等**：同一输入别重复调 LLM | LLM 的原始输出（文本/JSON） | `request_key` 完全相同 | 直接返回缓存输出，**不调 LLM** |
| Q2 | **复用**：以前生成过的概念节点，这次别再造一个 | 提案 / 已注册节点的 `canonical_id` | 规范化 id 相同，或向量近邻 ≥ 阈值且**同论文同阶段** | 复用并 `GENERATED_BY` 指向原 run，`use_count++` |
| Q3 | **累积**：这次跑完新学到的东西，下次能直接用 | 动态类注册 + `Lesson` + `use_count` | 类 `status=active` 且在有效期内 | 作为先验注入 prompt / 直接构建应用节点 |

**Q1 是缓存，Q2 是实体解析，Q3 是本体演化**。本设计用三层缓存分别对应，绝不用一个 dict 糊在一起。

> 一个容易犯的错：用向量相似度做 Q2 的跨论文复用。若 A 论文的「fragment coarse-graining」与 B 论文的相似概念被合并，就会制造跨论文假事实 —— 这正是上一轮 GGR 诊断出的 `identity_pullback` 类问题。所以 **Q2 的向量近邻只允许在同一 `paper_id + stage` 内做幂等重放**。

---

## 2. 四态生命周期 + 双时间模型

借鉴 Graphiti/Zep（arXiv:2501.13956）的 episode 与 bi-temporal，但用项目已有的 `POGraph` + JSON 快照实现：

```
                    ┌──────────────── 不删除，标 valid_to ───────────────┐
                    ▼                                                    │
  LLM 输出 → proposed ──align/validate 通过──▶ validated ──规则+证据+批准──▶ registered
                 │                                │                          │
                 │ 校验失败                       │ 冲突/证据不足             │ supersedes
                 ▼                                ▼                          ▼
             rejected(留档)                 proposal 保留等待            deprecated
```

| 状态 | 是否在 `app_generation.json` | `attribution` | 说明 |
|---|---|---|---|
| `proposed` | ❌ | `llm_proposal` | 只写 `node_cache/proposals/`，可带 `confidence` 与原始输出 |
| `validated` | ❌ | `llm_proposal` | 字段契约 + 证据优先级 + 门都过，但尚未获准注册 |
| `registered` | ✅ | `llm_proposal`（保留！） | 可增量合并进应用图；带 `registration_id`、`use_count` |
| `deprecated` | 保留但 `valid_to` 非空 | 同上 | **不删除**，新版本用 `supersedes` 指向它 |

**双时间字段**（每个提案与注册项都有）：

```json
{"valid_from": "2026-11-15T10:00:00Z",
 "valid_to": null,
 "recorded_at": "2026-11-15T10:00:03Z",
 "run_id": "run:2411.06608:20261115T100000Z"}
```

`valid_from/valid_to` 是事实有效期，`recorded_at` 是系统记录时间 —— 两条时间线分开，才能回答「这个节点在当时的 run 里是否生效」。

> `attribution` **晋升后也不改**。这是 `po/store.py` 用 Assertion reification 区分「分析者关联 / 作者声明」的初衷：一个由 LLM 提出的节点，即使被批准入图，也必须永远能被识别为「LLM 提案」而非「论文客观事实」。语义层 6 类不接受 `attribution="llm_proposal"` 的节点。

---

## 3. 三层缓存架构

```
┌─ L1 请求级幂等缓存  node_cache/requests/<request_key>.json ─────────┐
│  key = sha256(sorted_json(cache_identity))                         │
│  value = RequestCacheEntry（原始输出 + 六哈希 + 时间戳 + llm 元数据）│
│  命中 → llm_calls = 0，直接把输出交给 align()                      │
└────────────────────────────┬───────────────────────────────────────┘
                             │ 未命中 → 调 LLM → 写 L1 → 解析成提案
                             ▼
┌─ L2 节点提案缓存  node_cache/proposals/<proposal_id>.json ──────────┐
│  LLMNodeProposal（候选类/实例/关系 + evidence + embedding + 状态）│
│  近邻索引 node_cache/index.json（复用 storage/semantic/vector 1024d）│
│  冲突 → conflicts/CONFLICT_LOG.jsonl，不自动合并                  │
└────────────────────────────┬───────────────────────────────────────┘
                             │ validate + promote
                             ▼
┌─ L3 动态注册中心  dynamic_tbox/registry.json ──────────────────────┐
│  DynamicClassRegistration（类）+ NodeCacheEntry（已注册实例）      │
│  + relations.json + PROMOTION_LOG.jsonl (append-only)              │
│  + snapshots/dyn-x.y.z.json（可 diff / 可回滚）                    │
└────────────────────────────┬───────────────────────────────────────┘
                             │ materialize() 增量合并
                             ▼
                  app_generation.json（只增 registered）
```

### 3.1 `cache_identity`（键的四维版本绑定，缺一不可）

```python
cache_identity = {
    "task": "generation",
    "stage": "4broad",                      # SciForge 阶段 id
    "input_fp": sha256(sorted(input_node_ids) + sorted(related_attr_digest)),
    "semantic_fp": sha256(read_bytes("storage_cf/sciforge/batch10_semantic_v4.json")),
    "tbox_version": SEMANTIC_TBOX_VERSION + "@" + DYNAMIC_TBOX_VERSION,
    "prompt_version": "gap_miner@v3",
    "model_id": "qwen2.5-72b-instruct",
    "effort": "balanced",
}
request_key = "rq:" + sha256(json.dumps(cache_identity, sort_keys=True, ensure_ascii=False))
```

**任何一维变化都会自然产生新 key → `cache_miss`**，不需要显式失效广播。这比「改代码时手动清缓存」可靠得多，也与 `web/data_api.py` 的 `stamp` 缓存思路一致但更严格。

`input_fp` 只取**该阶段实际读取的节点与属性摘要**，不是整图哈希 —— 否则语义层任何一处改动都会让全部 26 阶段缓存失效。受影响范围由 §7 的 `dependency_index` 精确计算。

### 3.2 L1 的向量近邻（可选、有界）

对同一 `stage + model_id` 的缓存项，可用 1024 维嵌入做 ANN 召回，阈值 **0.92**：

| 相似度 | 动作 |
|---|---|
| ≥ 0.98 且 `input_fp` 相同 | `reuse`（等价重放） |
| 0.92–0.98 | 只作为**候选提示**注入 prompt，输出仍走完整验证，**不算命中** |
| < 0.92 | miss |

> 显式禁止：不同 `paper_id` 之间的相似输出互相复用。防止「A 论文的 gap 被搬到 B 论文」。

---

## 4. 四个核心数据结构

### 4.1 `RequestCacheEntry`（L1）

```json
{
  "request_key": "rq:9f2c...",
  "cache_identity": {"task": "generation", "stage": "4broad", "...": "..."},
  "stage": "4broad",
  "paper_id": "paper:2411.06608",
  "raw_output": {"gaps": [{"gap_id": "GAP-01", "...": "..."}]},
  "output_sha": "sha256:...",
  "prompt_sha": "sha256:...",
  "input_sha": "sha256:...",
  "code_sha": "sha256:...",
  "model_id": "qwen2.5-72b-instruct",
  "prompt_version": "gap_miner@v3",
  "tokens_in": 1840, "tokens_out": 612,
  "recorded_at": "2026-11-15T...",
  "hit_count": 0,
  "n_proposals": 2
}
```

> 六哈希中的 `code_sha / input_sha / output_sha` 与 `reprospec/scoring.py::claim_anchors()` 三哈希同构；新增 `prompt_sha / model_id / prompt_version` 三项，构成 LLM 输出的完整锚。

### 4.2 `LLMNodeProposal`（L2）

```json
{
  "proposal_id": "prop:000123",
  "request_key": "rq:9f2c...",
  "run_id": "run:2411.06608:20261115T100000Z",
  "status": "proposed",
  "kind": "instance",
  "candidate_class": "ResearchGap",
  "registration_id": "dcls:0007",
  "canonical_id": "appgap:2411.06608:fragment_attachment_enumeration",
  "attrs": {"gap_id": "GAP-01", "gap_type": "method_blank",
            "statement": "...", "priority": "high"},
  "relation_candidates": [
    {"relation": "SUPPORTED_BY", "target": "appsrc:..."},
    {"relation": "ANCHORS", "target": "appidea:..."}
  ],
  "derived_from": ["paper:2411.06608", "sourcepaper:..."],
  "evidence_ids": ["appev:..."],
  "attribution": "llm_proposal",
  "layer": "application",
  "task": "generation",
  "miner": "paperapp.miners.gap_miner",
  "confidence": 0.86,
  "embedding": [0.012, "..."],
  "validation": {"field_contract": "PASS", "evidence_rank": 2,
                 "gates": [], "conflicts": []},
  "valid_from": null, "valid_to": null,
  "recorded_at": "2026-11-15T...",
  "supersedes": ""
}
```

**`kind` 三值**：`instance`（新节点）/ `class`（LLM 想发明一个新类）/ `relation`（新关系）。`class` 与 `relation` 提案**默认不自动批准**，必须人工或规则显式注册（见 §6）。

### 4.3 `NodeCacheEntry`（L3 实例注册项）

```json
{
  "canonical_id": "appgap:2411.06608:fragment_attachment_enumeration",
  "registration_id": "dcls:0007",
  "proposal_id": "prop:000123",
  "status": "registered",
  "layer": "application", "task": "generation",
  "use_count": 7,
  "first_seen": "2026-11-15T...",
  "last_used": "2026-11-20T...",
  "valid_from": "2026-11-15T...", "valid_to": null,
  "source_runs": ["run:...", "run:..."],
  "evidence_ids": ["appev:..."],
  "spec_hash": "sha256:...",
  "supersedes": "",
  "deprecated_reason": ""
}
```

### 4.4 `PromotionRecord`（append-only 日志行）

```json
{"ts": "2026-11-15T...", "proposal_id": "prop:000123",
 "from": "validated", "to": "registered",
 "rule": "rule:gap_gate_pass AND evidence_count>=1 AND reuse_count>=3",
 "approver": "human:zengshuxin", "run_id": "run:...",
 "registry_version": "dyn-1.3.0", "canonical_id": "appgap:..."}
```

### 4.5 `DynamicClassRegistration`

字段见 [SCIFORGE_INTEGRATION_BLUEPRINT.md](SCIFORGE_INTEGRATION_BLUEPRINT.md) §6.2。关键点：**类注册与实例写入分离**，类不在 `status=active` 时，其实例只能停在 `proposed`。

---

## 5. 对齐与去重算法（Q2）

复用 `ontology/metrics.py::align_metric_name()` 的三态，扩成四态。

```
align(proposal, graph, registry) -> AlignResult

1. 确定性规范化
   canonical_id = id_template.format(arxiv, slug(normalize(label)))
   normalize = 小写 + 去停用词 + 全半角统一 + 别名表（复用 resolve_relation 思路）

2. 精确命中
   if canonical_id in L3:
       → action="reuse", use_count += 1, GENERATED_BY 指向原 run
       → 返回（不新建节点、不调 LLM）

3. 受控词表判定（类与关系）
   cls = default_registry.get(PAPERAPP_CLASS_VOCAB).canonical(candidate_class)
   if cls is None:
       → action="proposal", reason="unregistered_class"，写 CONFLICT_LOG
       → 绝不发明新类

4. 同域向量近邻【仅同一 paper_id + stage】
   near = ann_search(proposal.embedding, filter={paper_id, stage}, k=5)
   if near[0].score >= 0.98 and near[0].input_fp == proposal.input_fp:
       → action="reuse"（等价重放）
   elif near[0].score >= 0.92:
       → action="proposal", reason="ambiguous_duplicate"，写 CONFLICT_LOG
       → 不自动合并
   else:
       → action="proposal"（新候选）

5. 输出 AlignResult {action, canonical_id, node_id, conflicts[], proposal_reason}
```

**`action` 取值**：`reuse | registered | proposal | deprecated`（前三个与 `align_metric_name()` 完全兼容，便于渐进替换）。

**冲突日志格式**（每行一条）：

```json
{"ts":"...", "proposal_id":"...", "near_id":"...", "score":0.943,
 "reason":"ambiguous_duplicate", "resolution":"hold_for_human"}
```

---

## 6. 验证与晋升（Q3）

### 6.1 `validate(proposal)` → `validated`

按 `semantic/provenance.py` 的 5 级证据优先级打分，再过 4 项：

| 检查 | 判据 | 失败 |
|---|---|---|
| 字段契约 | 所有 `required` 字段在 `DynamicClassRegistration.fields` 内；值类型匹配 | `rejected` |
| 类已注册 | `registry[candidate_class].status == "active"` | 保持 `proposed` |
| 证据 | ≥1 条 `evidence_ids`，且优先级 ≤ 5 | 保持 `proposed` |
| 门 | `gates.py` 对应阶段 verdict ∈ `{PASS, WARN}` | `rejected` |

> 复用 `E_CONTRACTS` 的「NON_LLM 优先」：能由 AST/表格/规则得到的字段，不接受 LLM 提案覆盖。若提案与 NON_LLM 事实冲突，直接 `rejected` 并记冲突。

### 6.2 `promote(proposal)` → `registered`

```
def can_promote(p, registry, policy) -> (bool, reason):
    if p.status != "validated":                 return False, "not_validated"
    if p.attribution != "llm_proposal":         return False, "missing_attribution"
    if not registry[p.candidate_class].active:  return False, "class_not_active"
    if p.kind in ("class", "relation") and not human_approved(p):
                                                return False, "needs_human_approval"
    if p.validation.evidence_rank > 2:          return False, "weak_evidence"
    if policy.require_reuse and p.use_count < policy.min_reuse:  # 默认 3
                                                return False, "reuse_below_threshold"
    if semantic_promotion(p) and not (non_llm_evidence(p) and human_approved(p)):
                                                return False, "semantic_layer_protected"
    return True, "ok"
```

**五条硬规则（不可绕过）**：

1. `attribution="llm_proposal"` 的节点**永不**写 `batch10_semantic_v4.json`；
2. 晋升到**语义层属性**必须有 NON_LLM 证据（AST / 表格 / 规则 / 哈希）+ 人工批准，且走 `semantic/apply.py` 的既有回填链，不走缓存；
3. 晋升到**应用图**只需类 active + 证据 + 门 + 复用计数，可自动；
4. 新类 / 新关系必须人工批准（防本体膨胀）；
5. 每次晋升写 `PROMOTION_LOG.jsonl`，原提案文件**保留不删**，注册项带 `supersedes` 可回滚。

### 6.3 回写 `materialize(run)`

```
1. 收集本 run 全部 proposals
2. 对每条：align → validate → 尝试 promote
3. 汇总 registered 节点，构造 delta = {nodes:[...], assertions:[...]}
4. 校验：build_task_layer("generation") 全量结果 与
         (上一版 app_generation.json ⊕ delta) 逐节点/逐断言一致
         —— 不一致即拒绝回写并报 DRIFT
5. 加文件锁写 app_generation.json；更新 registry 的 use_count / last_used
6. 写 LESSONS.json（复用 schema/capability.py::Lesson）与 events.ndjson
7. 输出 MATERIALIZE_REPORT.json：
   {n_proposed, n_validated, n_registered, n_rejected, n_conflicts,
    cache_hit_rate, semantic_graph_sha (须与 run 前一致)}
```

> 第 4 步是整套设计的**安全底座**：增量回写必须是全量重建的等价优化，否则缓存就成了第二个真相源。

---

## 7. 失效与最小重算

### 7.1 四类触发

| 触发 | 影响范围 | 动作 |
|---|---|---|
| `semantic_fp` 变化 | 由 `dependency_index` 反查依赖了变更节点的应用节点 | 标 `stale` → 只重跑相关阶段（**不是全量重跑**） |
| `DYNAMIC_TBOX_VERSION` 变化 | 用该类/关系的全部注册项 | `revalidate`，不通过的标 `valid_to` + `deprecated` |
| `prompt_version` / `model_id` 变化 | 对应 `request_key` 自然 miss | 新 key 重新生成，**旧缓存保留可对照** |
| 显式 `invalidate(key)` / `supersedes` | 指定项 | `valid_to=now`，写 `PROMOTION_LOG` |

### 7.2 `dependency_index`

在 `node_cache/index.json` 维护反向依赖：

```json
{"paper:2411.06608": ["appgap:...", "appidea:...", "appclaim:..."],
 "benchmark:zinc":   ["appcontract:zinc", "appmetric:..."]}
```

语义层图变化时，用 `sha256` 逐节点比对 6001 个节点找出真正变化的 id，再查 `dependency_index` 得到受影响的应用节点集合 —— 与 `RUBRIC_TREE_LAYER.md` 的 `failed_branches`「只重判失败子树」是同一思想。

### 7.3 明确不做的失效方式

- 不删除缓存文件（append-only + `valid_to`）；
- 不做 TTL 定时清理（研究产物需要可回溯，过期靠 `valid_to` 标记）；
- 不用「清空整个缓存目录」来解决版本升级（靠 `cache_identity` 自然 miss）。

---

## 8. 溯源与防作弊

| 机制 | 落点 |
|---|---|
| 六哈希锚 | `code_sha / input_sha / output_sha / prompt_sha / model_id / prompt_version` |
|  Attribution 隔离 | `attribution="llm_proposal"` 永不改，语义层不接受 |
| 证据链 | 每个提案 ≥1 `evidence_ids`，按 `provenance.py` 5 级排序；`quote` 与 `title` 分开（引用标题不是逐字证据） |
| durable truth | `events.ndjson` append-only + `RUNSTATE` 派生快照，可崩溃恢复 |
| 单一写入者 | `domain-signature` 式约束：`DomainProfile` 只能由 1b 写；`registry.json` 只能由 `registry.py` 写 |
| 防抄期望值 | 数值节点必须从 `Benchmark.model_results` 原始行重算，不读 `LeaderboardEntry.value` 期望值 |
| 双跑一致 | 同一 `request_key` 两次执行 `output_sha` 必须相同 |
| 诚实降级 | 证据不足 → `proposal`/`BLOCKED`，不得为了晋升率编造证据 |

---

## 9. 与现有代码的精确接入点

| 新模块函数 | 复用的既有实现 | 位置 |
|---|---|---|
| `nodecache.cache_key()` | `ingest/arxiv.py` 的查询缓存键写法 | `src/capfactory/ingest/arxiv.py` L53-57 |
| `align.canonicalize()` | `resolve_relation()` 别名表 | `src/capfactory/reprospec/relations.py` |
| `align.three_state()` | `align_metric_name()` 三态 + `default_registry` | `src/capfactory/ontology/metrics.py` L130-163、`po/vocab.py` |
| `validate.field_contract()` | `E_CONTRACTS` / `NON_LLM` | `src/capfactory/semantic/extraction/contracts.py` |
| `validate.evidence_rank()` | 5 级证据优先级 | `src/capfactory/semantic/provenance.py` L3-8 |
| `promote.human_approval()` | `APPROVAL_LOG.txt` 模式 | `docs/skills/05-orchestrator/auto-pipeline-guide.md` §5 |
| `NodeCacheEntry` 成熟度字段 | `Capability(version, maturity, lessons, provenance)` | `src/capfactory/schema/capability.py` |
| `materialize.rebuild_equivalence()` | `build_task_layer()` 全量重建 | `src/capfactory/applayer/builder.py` |
| `materialize.write_nodes()` | `Concept` / `Assertion` 的 `attribution / evidence_ids` | `src/capfactory/po/store.py` L23-95 |
| `replay.lessons()` | `Lesson` + `RUN_PREPRINT.md` | `schema/capability.py` / SciForge Phase 16 |
| `gates.six_state()` | 6 态 verdict | `sciforge/contracts.py::VERDICT_STATES` / `validate_verdict()` |
| `invalidate.scope()` | `failed_branches` 最小重算 | `reprospec/rubric_tree.py` |

---

## 10. 公开 API（函数签名）

```python
# capfactory/paperapp/nodecache.py
def cache_identity(task, stage, input_nodes, graph, *, effort, model_id,
                   prompt_version, dynamic_version) -> dict
def request_key(identity: dict) -> str
def get_or_call(identity: dict, call_llm, *, out_dir) -> tuple[dict, bool]  # (entry, hit)
def put_proposal(entry: dict, raw: dict, *, out_dir) -> LLMNodeProposal
def load_proposals(run_id: str, *, out_dir) -> list[LLMNodeProposal]
def invalidate(key: str, *, reason: str, out_dir) -> dict

# capfactory/paperapp/registry.py
def register_class(spec: dict, *, approver: str, out_dir) -> DynamicClassRegistration
def active_classes(task: str, *, out_dir) -> frozenset[str]
def deprecate_class(name: str, *, reason: str, out_dir) -> dict
def validate_dynamic_tbox(*, out_dir) -> list[str]     # 返回问题列表，[] = 通过

# capfactory/paperapp/align.py
def canonical_id(cls: str, label: str, *, paper_id: str) -> str
def align(proposal, graph, registry, *, out_dir) -> AlignResult  # reuse|registered|proposal|deprecated

# capfactory/paperapp/validate.py
def validate_proposal(p, spec, gates, *, out_dir) -> LLMNodeProposal   # proposed -> validated

# capfactory/paperapp/promote.py
def can_promote(p, registry, policy, *, approver="") -> tuple[bool, str]
def promote(p, *, approver, out_dir) -> PromotionRecord
def bump_usage(canonical_ids, run_id, *, out_dir) -> dict

# capfactory/paperapp/materialize.py
def materialize(run_id, graph, *, out_dir, task="generation") -> MaterializeReport
def rebuild_equivalence(delta, *, task="generation") -> tuple[bool, list[str]]

# capfactory/paperapp/cli.py
# run / cache-status / cache-invalidate / promote / registry-audit / status
```

**统一返回约定**：所有写操作返回 `{"ok": bool, "action": str, "reason_code": str, "files": [...]}`；失败不抛异常到编排器，由 `gates.py` 转成 6 态 verdict。

---

## 11. 测试清单（`tests/test_paperapp_cache.py`）

| # | 测试 | 判据 |
|---:|---|---|
| 1 | `request_key` 确定性 | 同一 identity 两次相同；`sort_keys=True` 下字段顺序无关 |
| 2 | 四维版本绑定 | 改 `semantic_fp` / `tbox_version` / `prompt_version` / `model_id` 任一 → key 变化 |
| 3 | L1 幂等 | 第二次 `get_or_call` 的 `llm_calls == 0` 且 `output_sha` 相同 |
| 4 | 精确命中复用 | 同 `canonical_id` → `action="reuse"`、`use_count++`、无新节点 |
| 5 | 受控词表 | 未注册类 → `action="proposal"` 且写 `CONFLICT_LOG` |
| 6 | 向量阈值 | 0.99+同 `input_fp` → reuse；0.94 → proposal 且不合并 |
| 7 | 跨论文隔离 | 不同 `paper_id` 的 0.99 相似提案**不**复用 |
| 8 | 四态流转 | proposed→validated→registered→deprecated 全路径，deprecated 不删除 |
| 9 | 语义层保护 | `attribution="llm_proposal"` 提案试图写语义层 → `reject` 且图哈希不变 |
| 10 | 新类需批准 | `kind="class"` 无 `approver` → `can_promote=False, "needs_human_approval"` |
| 11 | 证据不足 | `evidence_ids=[]` → 保持 `proposed` |
| 12 | NON_LLM 冲突 | 提案值与 AST/表格事实冲突 → `rejected` |
| 13 | 重建等价 | `build_task_layer ⊕ delta` 与全量重建逐节点/逐断言一致（**硬门**） |
| 14 | 增量回写 | `app_generation.json` 只增 `registered` 节点，`app_reproduction.json` 与语义层不变 |
| 15 | 最小重算 | 语义层单节点变更 → 只重算 `dependency_index` 命中的节点，`stale_recompute_scope` < 5% |
| 16 | append-only | `PROMOTION_LOG.jsonl` 只增行，无改写；快照可 diff |
| 17 | 六哈希 | `RequestCacheEntry` 六项齐全，`output_sha` 可复算 |
| 18 | 崩溃恢复 | `events.ndjson` 重放后 `RUNSTATE` 与 `registry.use_count` 一致 |

---

## 12. 一次完整时序示例

**Run 1（首次）**

```
P1b  learner 生成 DomainProfile
  → request_key miss → 调 LLM → 写 L1
  → 解析成 LLMNodeProposal(status=proposed, kind=instance)
  → align: 类 DomainProfile 未在 registry → CONFLICT_LOG, action=proposal
  → 人批准注册类 dcls:0001 (dyn-1.1.0)
  → 重跑该阶段：align 命中类 → validate 通过 → promote → registered
  → materialize: 等价性检查通过 → 增量写入 app_generation.json
  → events.ndjson + PROMOTION_LOG + LESSONS.json
```

**Run 2（同论文、同输入）**

```
P1b  → request_key HIT → llm_calls=0
     → align 精确命中 canonical_id → action=reuse, use_count=2
     → 无新节点、无回写
```

**Run 3（论文A 的相似问题出现在论文B）**

```
→ request_key miss（paper_id 不同，input_fp 不同）
→ align 向量 0.99 但 paper_id 不同 → 不复用，新建 proposal
→ 必须重新验证 evidence（引用来自 B 论文的 SourcePaper）
→ 避免跨论文假边
```

**Run 4（语义层图更新）**

```
→ semantic_fp 变化 → 全部 L1 新 key
→ dependency_index 找出受影响的 12 个应用节点 → 标 stale
→ 只重跑 4broad / 2 / 10 三个阶段（不是 26 个）
→ 旧注册项标 valid_to，新项 supersedes 指向旧项
```

---

## 13. 反模式清单

1. 用一个 `dict` 同时承担「LLM 输出缓存 / 节点去重 / 类注册」；
2. 用向量相似度跨论文合并事实节点；
3. 把 `validated` 直接当 `registered` 写入全量图；
4. 晋升后把 `attribution` 改成 `author_stated` 或 `semantic`；
5. 为了命中率删掉 `cache_identity` 里的版本维度、或降低阈值到 0.8；
6. 删除 deprecated 节点 / 清空缓存目录来做版本升级；
7. 让 LLM 自己发明新类并立即写实例；
8. 增量回写不做 `rebuild_equivalence` 校验（缓存变成第二真相源）；
9. 缓存里存「期望值」并在复现时读它（防抄期望值）；
10. 把 `title`/引用标题当 `quote` 证据（引用标题是书目证据，不是逐字引文）。

---

## 14. 与整体方案的衔接

本文件是 [SCIFORGE_INTEGRATION_BLUEPRINT.md](SCIFORGE_INTEGRATION_BLUEPRINT.md) §7 的完整展开：主文档负责「26 阶段怎么映射成动态本体」，本文件负责「LLM 新节点怎么缓存、复用、晋升、失效」。实现顺序按主文档 §9 的 P1 落地，P0 的等价性测试是本设计的前提。
