# S1 · 三层缓存、四态生命周期、对齐与晋升

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 实现 `nodecache / align / validate / promote` 四个模块，让 LLM 输出可缓存、可去重、可验证、可晋升，且**永远不污染语义层** |
| 依赖 | S0（`registry.json` active 判定、`verify_rebuild()`、CLI 骨架） |
| 上游文档 | `../DYNAMIC_ONTOLOGY_NODE_CACHE.md` 全文；`../SCIFORGE_INTEGRATION_BLUEPRINT.md` §7、§9 P1 |
| 周期建议 | 5–6 个工作日 |
| 一句话验收 | 同一 `request_key` 第二次 `llm_calls == 0`；任何 `attribution="llm_proposal"` 节点都不在语义层图里 |
| 硬门 | H4 / H5（见 [`README.md`](README.md) §5） |

> S1 **不接真实 LLM 调用**（用可注入的 `call_llm` stub），只把缓存与生命周期的确定性部分做实。真实模型接入放到 S2。

---

## 1. 后端设计

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/paperapp/nodecache.py` | L1 请求缓存 + L2 提案缓存 + `cache_identity` / `request_key` / `get_or_call` / `invalidate` |
| 新建 | `src/capfactory/paperapp/align.py` | 规范化 / 受控词表 / 向量近邻 / 三态→四态 |
| 新建 | `src/capfactory/paperapp/validate.py` | 字段契约 / 证据优先级 / 门判定 |
| 新建 | `src/capfactory/paperapp/promote.py` | `can_promote` / `promote` / `bump_usage` / append-only 日志 |
| 新建 | `src/capfactory/paperapp/schemas.py` | 4 个 dataclass + `to_dict/from_dict` + JSON Schema 导出 |
| 新建 | `src/capfactory/web/static/paperapp_cache.html` | 缓存浏览器 |
| 新建 | `tests/test_paperapp_s1.py` | §6 的 20 项 |
| 修改 | `src/capfactory/web/paperapp_api.py` | 追加 `/api/v10/paperapp/cache/*` 与 `/proposals/*`、`/promote` |
| 修改 | `src/capfactory/paperapp/cli.py` | `cache-status / cache-invalidate / promote / audit-isolation` |
| 修改 | `src/capfactory/config.yaml` | `paperapp.cache:` 段（阈值、TTL 策略、版本） |
| 修改 | `src/capfactory/schema/capability.py` | `Capability` 追加 8 字段（**只追加，不改既有字段**） |

### 1.2 目录结构（全部在 `storage/` 工作区内）

```
storage/sciforge/node_cache/
├── requests/<request_key>.json        # L1
├── proposals/<proposal_id>.json       # L2
├── conflicts/CONFLICT_LOG.jsonl       # append-only
└── index.json                         # 近邻索引 + dependency_index 预留
storage/sciforge/dynamic_tbox/
├── registry.json                      # S0 已有
├── nodes/<canonical_id 的 slug>.json  # L3 已注册实例
├── PROMOTION_LOG.jsonl                # S0 已有，S1 写晋升行
└── snapshots/                         # S0 已有
```

### 1.3 `cache_identity`（四维版本绑定，缺一不可）

```python
def cache_identity(task, stage, input_nodes, graph, *, effort, model_id,
                   prompt_version, dynamic_version):
    return {
      "task": "generation",
      "stage": stage,
      "input_fp": sha256(sorted(input_node_ids) + sorted(related_attr_digest)),
      "semantic_fp": sha256(read_bytes(SEMANTIC_GRAPH)),
      "tbox_version": SEMANTIC_TBOX_VERSION + "@" + dynamic_version,
      "prompt_version": prompt_version,
      "model_id": model_id,
      "effort": effort,
    }
request_key = "rq:" + sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False))
```

**`input_fp` 只取该阶段实际读取的节点与属性摘要**，不是整图哈希 —— 否则语义层一处改动会让 26 阶段缓存全失效。

### 1.4 四态生命周期

| 状态 | 落盘位置 | 进 `app_generation.json` | `attribution` |
|---|---|---|---|
| `proposed` | `node_cache/proposals/` | ❌ | `llm_proposal` |
| `validated` | 同上（状态字段更新，原文件保留） | ❌ | `llm_proposal` |
| `registered` | `dynamic_tbox/nodes/` | ✅（S4 才真正写） | `llm_proposal`（**永不改**） |
| `deprecated` | 保留，`valid_to` 非空 | 保留 | 同上 |

双时间字段：`valid_from / valid_to / recorded_at`；`supersedes` 指向被替代项；**不删除任何文件**。

### 1.5 四个核心 dataclass（`schemas.py`）

| 类 | 关键字段 |
|---|---|
| `RequestCacheEntry` | `request_key, cache_identity, stage, paper_id, raw_output, output_sha, prompt_sha, input_sha, code_sha, model_id, prompt_version, tokens_in/out, recorded_at, hit_count, n_proposals` |
| `LLMNodeProposal` | `proposal_id, request_key, run_id, status, kind(instance/class/relation), candidate_class, registration_id, canonical_id, attrs, relation_candidates, derived_from, evidence_ids, attribution, layer, task, miner, confidence, embedding, validation, valid_from/to, recorded_at, supersedes` |
| `NodeCacheEntry` | `canonical_id, registration_id, proposal_id, status, layer, task, use_count, first_seen, last_used, valid_from/to, source_runs, evidence_ids, spec_hash, supersedes, deprecated_reason` |
| `PromotionRecord` | `ts, proposal_id, from, to, rule, approver, run_id, registry_version, canonical_id` |

`Capability` 追加：`cache_key, prompt_hash, model_id, input_sha, output_sha, valid_from, valid_to, use_count` —— 复用 `schema/capability.py` 已有的 `version / maturity / lessons / provenance / verification / artifact_ids`。

### 1.6 公开接口（签名冻结）

```python
# nodecache.py
def get_or_call(identity: dict, call_llm, *, out_dir) -> tuple[RequestCacheEntry, bool]
def put_proposal(entry, raw, *, out_dir) -> LLMNodeProposal
def load_proposals(run_id, *, out_dir) -> list[LLMNodeProposal]
def invalidate(key, *, reason, out_dir) -> dict

# align.py
def canonical_id(cls, label, *, paper_id) -> str
def align(proposal, graph, registry, *, out_dir) -> AlignResult  # reuse|registered|proposal|deprecated

# validate.py
def validate_proposal(p, spec, gates, *, out_dir) -> LLMNodeProposal

# promote.py
def can_promote(p, registry, policy, *, approver="") -> tuple[bool, str]
def promote(p, *, approver, out_dir) -> PromotionRecord
def bump_usage(canonical_ids, run_id, *, out_dir) -> dict
```

统一返回：`{"ok": bool, "action": str, "reason_code": str, "files": [...]}`；失败不向编排器抛异常，由 S3 的 `gates.py` 转成 6 态 verdict。

### 1.7 对齐算法（5 步）

```
1. canonical_id = id_template.format(arxiv, slug(normalize(label)))
   normalize = 小写 + 去停用词 + 全半角统一 + resolve_relation 别名表
2. 精确命中 L3 → action=reuse, use_count++, GENERATED_BY 原 run
3. 受控词表（default_registry / PAPERAPP_CLASS_VOCAB）判定类与关系
   → 词表外：action=proposal, 写 CONFLICT_LOG, 绝不发明新类
4. 向量近邻【仅同 paper_id + stage】
   ≥0.98 且 input_fp 相同 → reuse
   0.92–0.98             → proposal + ambiguous_duplicate 冲突，不自动合并
   <0.92                 → proposal（新候选）
5. 返回 AlignResult{action, canonical_id, node_id, conflicts[], proposal_reason}
```

> **禁止跨论文复用**：不同 `paper_id` 的 0.99 相似提案也必须是 `proposal`。这一条由 T-S1-07 锁死。

### 1.8 晋升规则

```
can_promote(p) 必须全过：
  p.status == "validated"
  p.attribution == "llm_proposal"
  registry[p.candidate_class].status == "active"
  p.kind in ("class","relation") → 必须 human_approver 非空
  p.validation.evidence_rank <= 2
  p.use_count >= policy.min_reuse (默认 3；S1 单测可用 0)
  semantic_promotion(p) → 必须 NON_LLM 证据 + human_approver
```

五条硬规则见 `../DYNAMIC_ONTOLOGY_NODE_CACHE.md` §6.2。S1 只实现规则与日志，**不执行回写**（S4）。

---

## 2. 构建步骤（Step 1–12）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | `config.yaml` 加 `paperapp.cache:`（阈值 0.92/0.98、min_reuse=3、embedding_dim=1024、stub_model_id） | `cli status` 打印阈值 |
| 2 | `schemas.py` 四个 dataclass + `to_dict/from_dict` | 单测 T-S1-01 |
| 3 | `nodecache.cache_identity/request_key` | 同输入两次同 key；改任一维 → 不同 key（T-S1-02） |
| 4 | `get_or_call`（stub `call_llm` 计数器） | 第二次 `hit=True`、`llm_calls=0`（T-S1-03） |
| 5 | `put_proposal` / `load_proposals` + append-only 写 | 文件数 = 提案数（T-S1-04） |
| 6 | `align.canonical_id` + 受控词表分支 | 词表外类 → `proposal` + 冲突日志（T-S1-05/06） |
| 7 | 向量近邻（用 `numpy` 余弦，1024 维；不引入 faiss 依赖） | 阈值三档 + 跨论文隔离（T-S1-07/08） |
| 8 | `validate_proposal`：字段契约 + 证据优先级（`semantic/provenance.py` 5 级）+ 门 | 证据缺失/门 FAIL → 保持 `proposed`（T-S1-09/10） |
| 9 | `promote.can_promote/promote/bump_usage` | 五条规则各一条测试（T-S1-11..15） |
| 10 | `audit-isolation` CLI：扫语义层图找 `attribution="llm_proposal"` | 输出 `0` 且 `ok=true`（T-S1-16） |
| 11 | `paperapp_api` 追加 6 个 API + `paperapp_cache.html` | `/api/status` 无注册错误；页面 5 面板有数据 |
| 12 | `smoke.sh` 追加 3 项缓存 API；跑全量 | 15/15；H4/H5 全过 |

---

## 3. 修正清单

| # | 坑 / 触发信号 | 修法 | 回归 |
|---:|---|---|---|
| C1 | `json.dumps` 未 `sort_keys` → 同内容不同 key | 强制 `sort_keys=True, ensure_ascii=False` + 单测 | T-S1-02 |
| C2 | `semantic_fp` 每次读 6001 节点全图，缓存写变慢 | 用文件字节 sha256（软链一致），不解析图 | T-S1-17 |
| C3 | 向量近邻被发现跨论文复用 0.99 相似 gap | filter 强制 `paper_id + stage` 双条件；把这一条写进文档与测试 | T-S1-07 |
| C4 | 0.92–0.98 被当 reuse → 事实串味 | 该区间只记 `ambiguous_duplicate`，不算命中 | T-S1-08 |
| C5 | 晋升后把 `attribution` 改成 `author_stated` | `promote()` 禁止修改 `attribution`，加断言 | T-S1-16 |
| C6 | `PROMOTION_LOG.jsonl` 被重写而非追加 | 打开模式 `"a"`，测试比对行数 | T-S1-14 |
| C7 | `Capability` 追加字段破坏既有 8 个测试 | 用 `field(default=...)`，不改任何既有字段类型 | H11 |
| C8 | 提案文件被「清理」导致无法回滚 | 只标 `valid_to`/`deprecated`，不删文件 | T-S1-18 |
| C9 | stub `call_llm` 在真实接入时忘记替换 | `call_llm` 是显式可注入参数，S2 才注入真实实现 | T-S1-03 |
| C10 | `embedding` 维度与现有 1024 维索引不一致 | 配置项 `embedding_dim=1024` + 维度断言 | T-S1-19 |

---

## 4. 前端相应设计（缓存浏览器）

### 4.1 页面 `/paperapp/cache`（`paperapp_cache.html`）

沿用 `repro.html` 深色 CSS 变量与 `esc()/tbl()`。五个面板：

| 面板 | 数据源 | 关键展示 |
|---|---|---|
| L1 请求缓存 | `/api/v10/paperapp/cache/requests` | `request_key` 短码、stage、`hit_count`、`output_sha` 短码、`model_id`、recorded_at、命中率 |
| L2 提案缓存 | `/api/v10/paperapp/cache/proposals` | 提案表格：id / status 徽章 / class / canonical_id / confidence / evidence 数 |
| 提案详情抽屉 | `/api/v10/paperapp/proposals/{id}` | 完整 `attrs`、`relation_candidates`、六哈希、`validation` 结果、原始 `raw_output` 折叠区 |
| 冲突 | `/api/v10/paperapp/cache/conflicts` | 冲突条目：proposal_id / near_id / score / reason / resolution |
| L3 注册中心 | `/api/v10/paperapp/cache/nodes` | canonical_id / use_count / first_seen / last_used / valid_to / supersedes |

### 4.2 API 契约

| 路径 | 方法 | 200 响应 | 错误/空态 |
|---|---|---|---|
| `/api/v10/paperapp/cache/requests` | GET | `{items:[...], count, hit_rate, llm_call_reduction}` | 空目录 → `{items:[],count:0,hit_rate:0}`，**不 404** |
| `/api/v10/paperapp/cache/proposals?status=&limit=` | GET | `{items:[...], count, by_status:{...}}` | `status` 非法 → 400 `{reason_code:"bad_status"}` |
| `/api/v10/paperapp/proposals/{id}` | GET | 完整 `LLMNodeProposal` | 不存在 → 404 `{reason_code:"proposal_not_found"}` |
| `/api/v10/paperapp/cache/conflicts` | GET | `{items:[...], count}` | 空 → `items:[]` |
| `/api/v10/paperapp/cache/nodes` | GET | `{items:[...], count}` | 空 → `items:[]` |
| `/api/v10/paperapp/promote` | POST | `{ok, action, reason_code, promotion}` | 未批准的类/关系 → 403 `{reason_code:"needs_human_approval"}` |
| `/api/v10/paperapp/cache/invalidate` | POST | `{ok, key, valid_to}` | key 不存在 → 404 |

所有列表 API **默认 `limit=200`** 并对 `raw_output` 做截断（避免把 6001 节点量级数据灌进浏览器）。

### 4.3 状态机与交互

- 状态徽章色：`proposed`(warn) / `validated`(acc) / `registered`(ok) / `deprecated`(mut) / `rejected`(bad)；
- 点提案行 → 右侧抽屉展示详情；抽屉内「晋升」按钮仅在 `status=validated` 且 `can_promote` 预检通过时可用；
- 「晋升」二次确认弹窗必须显示 `approver` 输入框（人工批准凭据）与 `rule`；
- 「失效」按钮 → 调 `cache/invalidate`，行变灰显示 `valid_to`；**不删行**；
- 顶部汇总条：`cache_hit_rate / n_proposed / n_registered / promotion_rate / 隔离审计 ok`；
- 加载/空/错三态齐全；所有 `fetch` 用 `Promise.allSettled`，单面板失败不影响其它。

### 4.4 调试快捷入口

页面右上「复制 request_key」「复制 output_sha」「查看原始 JSON（新 tab）」三个按钮，直接对应 §5 的调试命令。

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `cache_identity` | 每阶段调用前 | 提案详情抽屉 | `python3 -m capfactory.paperapp.cli debug-key --stage 4broad` | `cache_key_built` | 8 个维度齐全 | 缺 `tbox_version` | C1 |
| 2 | `requests/<key>.json` | L1 未命中后写 | L1 面板 | `cat storage/sciforge/node_cache/requests/<key>.json` | `llm_called` / `cache_hit` | 六哈希齐全 | `output_sha` 为空 | 检查 raw_output 序列化 |
| 3 | `hit_count` 变化 | 命中时 | L1 面板命中率 | `cli cache-status` | `cache_hit` | 第二次 == 1 | 一直 0 | C1/C2 |
| 4 | `proposals/<id>.json` | LLM 输出解析后 | L2 面板 | `cat .../proposals/<id>.json` | `proposal_created` | status=proposed | 直接 registered | 检查类 active 判定 |
| 5 | `AlignResult` | align 后 | 详情抽屉 + 冲突面板 | `cli debug-align --proposal <id>` | `aligned` | 四态之一 | 出现 `unknown` | 词表/阈值配置错 |
| 6 | `CONFLICT_LOG.jsonl` | 冲突时 | 冲突面板 | `tail -n 20 .../CONFLICT_LOG.jsonl` | `conflict_recorded` | 只增行 | 被重写 | C6 |
| 7 | `validation` 字段 | validate 后 | 详情抽屉 | 同上 | `validated` / `rejected` | 有 `evidence_rank` | rank > 2 仍 validated | 检查门 |
| 8 | `PROMOTION_LOG.jsonl` | promote 后 | L3 面板 + 抽屉 | `tail -n 20 .../PROMOTION_LOG.jsonl` | `promoted` | 行数 == 晋升次数 | 行数减少 | C6 |
| 9 | `nodes/<slug>.json` | registered | L3 面板 | `cat .../dynamic_tbox/nodes/<slug>.json` | `node_registered` | `use_count>=0` | `attribution` 被改 | C5 |
| 10 | `deprecated` 项 | invalidate/supersedes | L3 灰行 | `cli audit-isolation` | `invalidated` | `valid_to` 非空 | 文件消失 | C8 |
| 11 | 隔离审计结果 | 每次 run 结束 | 顶部汇总条 | `cli audit-isolation` | `isolation_checked` | 语义层命中 0 | >0 | **立即停止** |
| 12 | API 注册状态 | 服务启动 | `/api/status` | `curl -s localhost:8091/api/status` | — | `{}` | `paperapp_api` 报错 | S0 C1 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S1-01 | 单元 | 4 个 dataclass 往返 | `from_dict(to_dict(x)) == x` |
| T-S1-02 | 单元 | key 确定性 + 四维绑定 | 同 identity 同 key；改 4 维任一 → key 变 |
| T-S1-03 | 集成 | `get_or_call` stub | 第二次 `hit=True`、`llm_calls==0`、`output_sha` 相同 |
| T-S1-04 | 单元 | 提案落盘 | 文件数 == 提案数，内容 JSON 可解析 |
| T-S1-05 | 单元 | `canonical_id` 规范化 | 全半角/大小写/别名归一后一致 |
| T-S1-06 | 单元 | 词表外类 | `action=proposal` + 冲突日志 1 行 |
| T-S1-07 | 单元 | **跨论文隔离** | 不同 `paper_id` 的 0.99 相似提案 → 不 reuse |
| T-S1-08 | 单元 | 阈值三档 | 0.99+同 input_fp→reuse；0.94→proposal；0.85→proposal |
| T-S1-09 | 单元 | 证据缺失 | 保持 `proposed`，`reason_code="weak_evidence"` |
| T-S1-10 | 单元 | 门 FAIL | 保持 `proposed`/`rejected`，不进 validated |
| T-S1-11 | 单元 | 类未 active | `can_promote=False, "class_not_active"` |
| T-S1-12 | 单元 | kind=class 无 approver | `False, "needs_human_approval"` |
| T-S1-13 | 单元 | 语义层晋升无 NON_LLM 证据 | `False, "semantic_layer_protected"` |
| T-S1-14 | 单元 | append-only 日志 | 晋升 3 次后日志恰好 3 行且原行未变 |
| T-S1-15 | 单元 | `bump_usage` | `use_count` 递增、`last_used` 更新 |
| T-S1-16 | 集成 | **隔离审计 H5** | 语义层图里 `attribution="llm_proposal"` 节点数 == 0 |
| T-S1-17 | 性能 | `semantic_fp` | 计算 < 200 ms（不解析图） |
| T-S1-18 | 单元 | deprecated 不删除 | 文件仍存在、`valid_to` 非空 |
| T-S1-19 | 单元 | embedding 维度 | 恒 1024，配置变化即报错 |
| T-S1-20 | API | 6 个缓存端点 | 200 + 空态结构正确；`/promote` 未批准 → 403 |

**夹具**：`tests/fixtures/paperapp_s1/` 内放 2 个 stub LLM 输出、3 个提案（含跨论文近似）、1 个冲突、1 个未注册类。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s1 -v
python3 -m capfactory.paperapp.cli audit-isolation
python3 -m unittest discover -s tests -p "test_*.py" -v
bash scripts/smoke.sh http://127.0.0.1:8091
```

---

## 7. 验收标准（签字表）

### 7.1 硬门

| 门 | 判据 | 实测值 |
|---|---|---|
| H4 缓存幂等 | T-S1-03 通过；`llm_calls==0` | `______` |
| H5 LLM 节点隔离 | `audit-isolation` 命中 0；语义层 sha 与 S0 基线一致 | `______` |
| H1/H2/H3 不退化 | 重跑 S0 三闸门 | `______` |
| H9 API 注册 | 6 个新端点注册无错 | `______` |
| H11 回归 | 8 既有 + 12(S0) + 20(S1) 全过 | `____/____` |

### 7.2 指标

| 指标 | 目标 |
|---|---|
| `cache_hit_rate`（重复跑同一论文） | ≥ 0.90 |
| `promotion_rate`（registered/proposed） | 0.2–0.6（过高说明门松，过低说明门紧） |
| `provenance_coverage` | 100%（每个提案有 `evidence_ids + run_id + attribution`） |
| 提案详情 API 响应 | < 300 ms |

### 7.3 退出条件与人工签字

- 交付 6 个新模块、20 项测试结果、缓存浏览器截图、隔离审计输出；
- **人工签字项**：确认 `PROMOTION_LOG.jsonl` 只增行；确认无任何提案被写进 `batch10_semantic_v4.json`；确认 `kind=class` 的晋升必须填 `approver`；
- 任一硬门不过 → 不得进入 S2。

---

## 8. 交付物与回滚

**交付**：6 个新文件 + 4 个修改文件 + `tests/test_paperapp_s1.py` + 夹具 + `docs/plan/S1_CACHE_REPORT.md`（实测指标）。

**回滚**：
1. git 恢复 4 个修改文件；`paperapp_api._V10` 回退到 S0 的 4 条路由；
2. `node_cache/` 与 `dynamic_tbox/nodes/` 归档到 `storage/sciforge/_archive_s1/`，**不删除**；
3. `config.yaml` 的 `paperapp.cache:` 段移除；
4. 重跑 `bash scripts/smoke.sh` 确认回到 S0 的 12/12。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| `get_or_call` / `request_key` | S2/S3 每个阶段适配器的 LLM 调用统一入口 |
| `LLMNodeProposal` | S2/S3 生成、S4 增量回写、S5 提案详情面板 |
| `align / validate / promote` | S4 `materialize()` 的三步流水线 |
| `CONFLICT_LOG.jsonl` | S5 冲突面板、S6 指标报告 |
| `audit-isolation` | S4 每次回写前、S6 回归 |
| `Capability` 追加字段 | S3 运行时节点、S4 `use_count` 回写 |
| 缓存浏览器 5 面板 | S5 整合为「缓存」tab |
