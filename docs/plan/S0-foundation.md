# S0 · 骨架、动态类注册与「重建等价性」闸门

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 建立 `capfactory/paperapp/` 骨架、动态类注册中心、**最小前端状态页**，并证明「增量回写 ≡ 全量重建」 |
| 依赖 | 无（起点） |
| 上游文档 | `../SCIFORGE_INTEGRATION_BLUEPRINT.md` §4/§6/§9 P0；`../DYNAMIC_ONTOLOGY_NODE_CACHE.md` §4.5 |
| 周期建议 | 3–4 个工作日 |
| 一句话验收 | **语义层图 SHA256 不变**，且 `rebuild(graph) ≡ rebuild(graph_prev) ⊕ delta` 逐断言一致 |
| 硬门 | H1 / H2 / H3（见 [`README.md`](README.md) §5） |

> S0 **不实现缓存、不实现 26 阶段、不接 LLM**。它只把「可扩展而不破坏现状」这件事证死。这一步没过，后面全部不得开工。

---

## 1. 后端设计

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/paperapp/__init__.py` | 统一导出 `DynamicClassRegistry` / `registry` / `PAPERAPP_STAGES` |
| 新建 | `src/capfactory/paperapp/tbox.py` | SciForge 26 阶段 → 应用类/关系映射表（**静态声明**，先只放阶段名与占位，S2/S3 填充） |
| 新建 | `src/capfactory/paperapp/registry.py` | 动态类注册中心（本阶段核心） |
| 新建 | `src/capfactory/paperapp/cli.py` | `status / verify-rebuild / registry-audit` 三个子命令（S1–S6 逐步扩） |
| 新建 | `src/capfactory/web/paperapp_api.py` | `/api/v10/paperapp/*` 的 `_V10` 路由表 + `register(app)` |
| 新建 | `src/capfactory/web/static/paperapp.html` | 基线状态页 |
| 新建 | `tests/test_paperapp_s0.py` | 见 §6 |
| 修改 | `src/capfactory/applayer/tasks.py` | `TASK_SPECS["generation"]` 追加 `dynamic_extends="capfactory.paperapp.registry"` 与 `materializer="capfactory.paperapp.materialize"` 两个**字符串声明**，不动 `classes`/`relations` tuple |
| 修改 | `src/capfactory/applayer/builder.py` | 增加可选参数 `registered_nodes: Iterable[Concept] | None = None` + 文件锁 + `verify_rebuild()`；**默认 `None` 时行为与现在逐字节一致** |
| 修改 | `src/capfactory/config.yaml` | 新增 `paperapp:` 段（见 §1.5） |
| 修改 | `src/capfactory/web/server.py` | `WEB_API_MODULES` 增加 `"paperapp_api"`（**必须**，否则 `/api/status` 会报 registration error） |

### 1.2 `DynamicClassRegistration` 结构（`registry.json` 的每一项）

```json
{
  "registration_id": "dcls:0001",
  "name": "DomainProfile",
  "parent_class": "ResearchQuestion",
  "layer": "application",
  "task": "generation",
  "producer_stage": "1b",
  "producers": ["paperapp.miners.domain_miner"],
  "consumers": ["idea_discovery", "verification_routing"],
  "fields": ["evidence_type", "reasoning_paradigm", "learning_confidence"],
  "relation_bindings": ["DERIVED_FROM", "CONSTRAINS"],
  "id_template": "appdomain:<arxiv>:<slug>",
  "promotion_rule": "rule:learning_confidence>=0.7",
  "status": "active",
  "tbox_version": "dyn-1.0.0",
  "first_seen": "2026-11-15T00:00:00Z",
  "valid_from": "2026-11-15T00:00:00Z",
  "valid_to": null,
  "use_count": 0,
  "evidence_ids": [],
  "supersedes": ""
}
```

**不变式**：
- `name` 必须在 `PAPERAPP_CLASS_VOCAB`（`po/vocab.py`）中；否则 `register()` 返回 `ok=False, reason_code="class_not_in_vocab"`；
- `relation_bindings` 每个关系必须能通过 `reprospec/relations.py::resolve_relation()` 解析；
- `status` 只能 `proposed | active | deprecated`；
- `class` 注册与 `instance` 写入分离：类非 `active` 时实例只能停在 `proposed`。

### 1.3 `registry.py` 公开接口

```python
def load_registry(*, out_dir=REGISTRY_DIR) -> Dict[str, Any]
def register_class(spec: dict, *, approver: str, out_dir=REGISTRY_DIR) -> Dict[str, Any]
def deprecate_class(name: str, *, reason: str, out_dir=REGISTRY_DIR) -> Dict[str, Any]
def active_classes(task: str = "generation", *, out_dir=REGISTRY_DIR) -> frozenset[str]
def validate_dynamic_tbox(*, out_dir=REGISTRY_DIR) -> List[str]   # [] 表示通过
def snapshot(*, out_dir=SNAPSHOT_DIR) -> str                       # 返回 dyn-x.y.z.json 路径
```

所有写操作返回 `{"ok": bool, "action": str, "reason_code": str, "files": [...]}`；写 `registry.json` 用 `os.replace` 原子替换 + `fcntl.flock` 文件锁；同时 append 一行到 `PROMOTION_LOG.jsonl`。

### 1.4 核心算法：`verify_rebuild()`（H2）

```
输入: graph_path = storage_cf/sciforge/batch10_semantic_v4.json
      prev_app    = storage_cf/sciforge/app_generation.json (上一版)
      delta       = {nodes:[...], assertions:[...]}  (registered 节点)

1. base = build_task_layer(base_graph, task="generation")   # 全量，纯确定性
2. incr = 深拷贝(prev_app); incr.apply(delta)               # 增量
3. 归一化：按 (id, type, sorted(attrs)) 与
            (source, target, relation, sorted(properties)) 各自排序
4. 逐项比对：n_missing / n_extra / n_attr_diff / n_rel_diff
5. 完全一致 → {"ok": True, "reason_code":"EQUIVALENT"}
   否则      → {"ok": False, "reason_code":"DRIFT", "diff": [...前 20 条...]}
6. 写 .sciforge/paperapp/REBUILD_EQUIVALENCE.json（带 semantic_sha / app_sha / ts）
```

> **为什么是硬门**：如果增量回写与全量重建不一致，缓存就成了第二个真相源，前端会展示与重建结果不同的图，后续所有溯源都失效。

### 1.5 `config.yaml` 新增段

```yaml
paperapp:
  cache_dir: storage/sciforge/node_cache
  registry_dir: storage/sciforge/dynamic_tbox
  run_dir: storage/sciforge/paperapp
  dynamic_tbox_version: dyn-1.0.0
  semantic_graph: storage_cf/sciforge/batch10_semantic_v4.json
  app_graph: storage_cf/sciforge/app_generation.json
  task: generation
  lock_file: storage/sciforge/.paperapp.lock
  allow_incremental_write: false     # S0 恒 false（只读验证）；S4 才允许 true
```

### 1.6 `paperapp_api.py` 的 `_V10`（照 `repro_api._V9` 范式）

```python
_V10 = [
  ("/api/v10/paperapp/status",            status,            "GET",  True),
  ("/api/v10/paperapp/registry",          registry_list,     "GET",  True),
  ("/api/v10/paperapp/registry/audit",    registry_audit,    "GET",  True),
  ("/api/v10/paperapp/verify-rebuild",    verify_rebuild_api,"GET",  True),
]
def register(app) -> int:
    existing = {getattr(r, "path", "") for r in app.routes}
    ...  # 与 repro_api.register 逐行同构
```

`status` 返回：`{ok, semantic_sha, app_sha, n_semantic_nodes, n_app_nodes, n_registered_classes, dynamic_tbox_version, api_errors}`。**不读 `graph_source.py`**，直接 `POGraph.load(app_graph)`。

---

## 2. 构建步骤（Step 1–10，每步即时验证）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | 记录基线：`sha256sum storage/sciforge/batch10_semantic_v4.json` 与 `app_generation.json`，存 `docs/plan/baseline_S0.json`（只追加，不覆盖） | 文件存在，两个 hash 有值 |
| 2 | 新建 `paperapp/` 包与 `tbox.py` 的 26 阶段 id 常量（只列 id/名称/前驱，不写实现） | `python3 -c "from capfactory.paperapp.tbox import STAGE_IDS; print(len(STAGE_IDS))"` → `26` |
| 3 | `po/vocab.py` 增加 `PAPERAPP_CLASS_VOCAB`（S0 先只放 4 个类名占位） | `test_vocab_standard` 不退化 |
| 4 | 实现 `registry.py` 六函数 + 文件锁 + 原子写 + append-only 日志 | 单测 `T-S0-01..04` |
| 5 | 实现 `builder.build_task_layer(..., registered_nodes=None)` 与 `verify_rebuild()` | 默认参数下与修改前的 `app_generation.json` 节点数、断言数完全一致（8853 / 现有值） |
| 6 | `tasks.py` 追加两个字符串声明 | `/api/v8/task/specs` 返回里能看到 `dynamic_extends` / `materializer` |
| 7 | `config.yaml` 新增段 + `config.py` 读取（若无读取点则只在 paperapp 内部 `yaml.safe_load`） | `python3 -m capfactory.paperapp.cli status` 能打印配置 |
| 8 | `web/paperapp_api.py` + `server.py` 注册 + `paperapp.html` | `curl /api/status` → `api_registration_errors == {}`；`curl /api/v10/paperapp/status` → 200 |
| 9 | `scripts/smoke.sh` 追加 2 项（`/api/v10/paperapp/status`、`/registry/audit`） | `bash scripts/smoke.sh` 12/12 |
| 10 | 跑 H1/H2/H3 全套 + 全量单测，把实测值写入 §7 签字表 | 见 §7 |

---

## 3. 修正清单（本阶段预判的坑）

| # | 坑 / 触发信号 | 修法 | 回归测试 |
|---:|---|---|---|
| C1 | 忘把 `paperapp_api` 加进 `WEB_API_MODULES` → `/api/v10/*` 全 404 | 按清单注册；`/api/status` 断言 `api_registration_errors == {}` | T-S0-08 |
| C2 | `graph_source.py` 默认读 `batch10_app_v1.json`，误以为 `app_generation.json` 会自动出现在既有页面 | **不改 graph_source**；动态节点只走 `/api/v10`；文档写明双图源 | T-S0-09 |
| C3 | `build_task_layer` 默认行为被改 → 8 个既有测试退化 | 只加可选参数，`registered_nodes=None` 分支与旧代码逐行相同 | H11 |
| C4 | `registry.json` 并发写坏（多 run 同时注册） | `fcntl.flock` + `os.replace` 原子替换 | T-S0-04 |
| C5 | 类未 active 就写实例 | `materialize` 在 S4 才允许；S0 `allow_incremental_write: false` 恒定 | T-S0-05 |
| C6 | `verify_rebuild` 比对受 dict 顺序影响误报 DRIFT | 归一化排序后再比；`properties` 也排序 | T-S0-06 |
| C7 | `storage_cf` 与 `storage` 双路径写导致两份不一致 | 统一用 `storage_cf`（软链），配置只保留一个真值 | T-S0-07 |
| C8 | 把上游 xKG-main 的 798 项回归 / `tests/Phase/` 写进验收命令 | 用本项目实际 `tests/` 8 个文件 + `unittest discover -s tests` | H11 |

---

## 4. 前端相应设计（S0 最小增量）

### 4.1 页面 `/paperapp`（`web/static/paperapp.html`）

复用 `repro.html` 的 CSS 变量、`esc()`、`tbl()`，不引入任何依赖。四个面板：

| 面板 | 数据源 | 展示内容 |
|---|---|---|
| 基线 | `/api/v10/paperapp/status` | `semantic_sha`（截断显示 + 复制按钮）、`app_sha`、节点数、动态类数、`dynamic_tbox_version` |
| 等价性 | `/api/v10/paperapp/verify-rebuild` | `ok` 徽章（绿/红）、`n_missing / n_extra / n_attr_diff / n_rel_diff`、前 20 条 diff |
| 注册中心 | `/api/v10/paperapp/registry` | 类表格：name / status / producer_stage / fields / use_count |
| 审计 | `/api/v10/paperapp/registry/audit` | 问题列表（空则显示「无问题」绿色） |

### 4.2 API 契约

| 路径 | 方法 | 响应 200 | 错误 |
|---|---|---|---|
| `/api/v10/paperapp/status` | GET | `{ok:true, semantic_sha, app_sha, n_semantic_nodes, n_app_nodes, n_registered_classes, dynamic_tbox_version, api_errors}` | 图文件缺失 → 503 `{ok:false, reason_code:"graph_missing"}` |
| `/api/v10/paperapp/registry` | GET | `{classes:[...], count, dynamic_tbox_version}` | 注册表缺失 → 200 + `{classes:[], count:0, initialized:false}`（**空态，不报错**） |
| `/api/v10/paperapp/registry/audit` | GET | `{ok, issues:[], validate_verdicts:["PASS"]}` | — |
| `/api/v10/paperapp/verify-rebuild` | GET | `{ok, reason_code, diff:[...], semantic_sha, app_sha}` | 超时 → 504 `{reason_code:"rebuild_timeout"}` |

### 4.3 状态与交互

- 页面加载并行发 4 个 `fetch`；`Promise.allSettled`，单个失败只让对应面板显示错误态，**不白屏**；
- 「重新校验」按钮 → 重新拉 `verify-rebuild`，按钮进入 `disabled + "校验中…"`；
- 加载态：每面板 `校验中…`；空态：`无数据`；错误态：显示 `reason_code` 与原始响应片段；
- `semantic_sha` 用 `<code class="mono">` 展示并附复制按钮（调试时最常用）。

### 4.4 与既有页面的关系

`home.html` 顶部导航**本阶段不加链接**（避免未完成时用户误入）；S5 统一加。页面可通过 URL 直接访问调试。

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `baseline_S0.json` | Step 1 | 文档 + 状态页「基线」 | `cat docs/plan/baseline_S0.json` | — | 两个 sha 非空 | 路径写成 `storage/` 与 `storage_cf/` 不一致 | 统一 `storage_cf` |
| 2 | `STAGE_IDS`（26 阶段常量） | Step 2 | 状态页不展示；CLI `status` | `python3 -m capfactory.paperapp.cli status` | — | `len==26` 且无环 | 前驱指向不存在阶段 | 修 tbox.py |
| 3 | `PAPERAPP_CLASS_VOCAB` | Step 3 | registry 面板 | `python3 -m unittest tests.test_vocab_standard -v` | — | 4 个占位类可读 | 与 `APP_CLASSES` 冲突 | 只增不改 |
| 4 | `registry.json` | Step 4 | registry 面板 | `cat storage/sciforge/dynamic_tbox/registry.json` | `PROMOTION_LOG.jsonl` 增行 | `validate_dynamic_tbox()==[]` | 类未 active 却有实例 | 回滚该实例 |
| 5 | `snapshots/dyn-1.0.0.json` | Step 4 | 状态页版本号 | `ls storage/sciforge/dynamic_tbox/snapshots/` | — | 可 diff | 快照缺失 | 重跑 `snapshot()` |
| 6 | `REBUILD_EQUIVALENCE.json` | Step 5/10 | 等价性面板 | `python3 -m capfactory.paperapp.cli verify-rebuild` | 事件 `rebuild_checked` | `ok=true` | `reason_code=DRIFT` | 看 diff 前 20 条 → 修 delta 构造 |
| 7 | 全量重建结果（内存） | Step 5 | 等价性面板计数 | `PYTHONPATH=src python3 -m capfactory.cli status` | — | 8853 节点 | 节点数变化 | C3 |
| 8 | `/api/v8/task/specs` 新字段 | Step 6 | 浏览器 devtools | `curl -s localhost:8091/api/v8/task/specs` | — | 有 `dynamic_extends` | 字段丢失 | 确认 `TASK_SPECS` 序列化路径 |
| 9 | `paperapp:` 配置 | Step 7 | 状态页 | `python3 -m capfactory.paperapp.cli status` | — | `allow_incremental_write=false` | 被误设 true | 立刻改回并跑 H2 |
| 10 | API 注册状态 | Step 8 | `/api/status` + 状态页 | `curl -s localhost:8091/api/status` | `app.state.api_registration_errors` | `{}` | `paperapp_api` 有错误 | C1 |
| 11 | 冒烟结果 | Step 9 | 终端 | `bash scripts/smoke.sh` | — | 12/12 | 任何 FAIL | 按失败路径查路由 |
| 12 | 语义层 sha | 全程 | 状态页常驻 | `sha256sum .../batch10_semantic_v4.json` | 事件 `semantic_sha_checked` | 与基线一致 | 不一致 | **立即停止**，从备份恢复 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S0-01 | 单元 | `register_class` 正常注册 | `ok=True`；`registry.json` 增 1 项；`PROMOTION_LOG` 增 1 行 |
| T-S0-02 | 单元 | 词表外类名 | `ok=False`, `reason_code="class_not_in_vocab"` |
| T-S0-03 | 单元 | `active_classes("generation")` | 只返回 `status=active` 且 `task=generation` |
| T-S0-04 | 并发 | 两进程同时注册 | 无 JSON 损坏、无丢行、`flock` 生效 |
| T-S0-05 | 单元 | 类未 active 时尝试写实例 | 被拒，`reason_code="class_not_active"` |
| T-S0-06 | 单元 | `verify_rebuild` 对键顺序不同但内容相同的两份结果 | `ok=True`（归一化生效） |
| T-S0-07 | 单元 | `storage_cf` 与 `storage` 写入同一文件 | sha 一致（软链） |
| T-S0-08 | API | `/api/status` 注册错误 | `api_registration_errors == {}` |
| T-S0-09 | 集成 | `graph_source.load()` 不受新增 API 影响 | 返回节点数与基线一致 |
| T-S0-10 | 集成 | `build_task_layer(registered_nodes=None)` | 与修改前 `app_generation.json` 逐节点/逐断言一致 |
| T-S0-11 | 集成 | `build_task_layer(registered_nodes=delta)` vs 全量 | `verify_rebuild()==EQUIVALENT` |
| T-S0-12 | 回归 | `unittest discover -s tests` | 8 个既有测试全过 |

**夹具**：`tests/fixtures/paperapp_s0/` 内放最小 3 节点语义图 + 2 条 delta（不读 6001 节点全量图，保证单测 < 1s）。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s0 -v
python3 -m unittest discover -s tests -p "test_*.py" -v
bash scripts/smoke.sh http://127.0.0.1:8091
```

---

## 7. 验收标准（签字表）

### 7.1 硬门（必须全过）

| 门 | 判据 | 实测值（实施时填写） |
|---|---|---|
| H1 语义层冻结 | 基线 sha == 收尾 sha | `____________` |
| H2 重建等价 | `verify_rebuild().ok == True`，diff 全 0 | `____________` |
| H3 基础契约 | 6 类 / 8 类 / 9 关系不变；`test_vocab_standard` PASS | `____________` |
| H9 API 注册 | `/api/status.api_registration_errors == {}` | `____________` |
| H11 回归 | 8 个既有测试 + 12 个新测试全过 | `____/____` |

### 7.2 指标（should）

| 指标 | 目标 |
|---|---|
| `verify_rebuild` 全量耗时 | < 30 s（6001 节点 + 8853 应用节点） |
| 单测总耗时 | < 5 s |
| 状态页 4 个 API 响应 | 各 < 500 ms |

### 7.3 退出条件与人工签字

- 交付 `baseline_S0.json`、`REBUILD_EQUIVALENCE.json`、12 项测试结果、截图（状态页四面板）；
- **人工签字项**：确认 `paperapp:` 配置里 `allow_incremental_write` 仍为 `false`；确认 `app_reproduction.json` 与 `batch10_semantic_v4.json` 未被写入；
- 任一硬门不过 → 不得进入 S1。

---

## 8. 交付物与回滚

**交付**：7 个新文件 + 4 个修改文件 + `tests/test_paperapp_s0.py` + `docs/plan/baseline_S0.json` + 本阶段实测报告（追加到 `docs/plan/S0_FOUNDATION_REPORT.md`）。

**回滚**：
1. `tasks.py` / `builder.py` / `server.py` / `config.yaml` 用 git 恢复（4 个文件，改动均为追加）；
2. 删除 `paperapp/` 包与 `paperapp.html`（**启用 `valid_to` 标记而非物理删除数据产物**）；
3. `dynamic_tbox/` 与 `node_cache/` 是新增目录，清空前先备份到 `storage/sciforge/_archive_s0/`；
4. 重跑 `bash scripts/rebuild.sh` 恢复派生层，`bash scripts/smoke.sh` 确认原 10 项全绿。

> 全程不使用 `rm -rf`；归档优先。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| `registry.json` / `validate_dynamic_tbox()` | S1（类 active 才能写实例）、S2/S3（阶段适配器注册新类）、S4（晋升）、S5（注册中心页） |
| `verify_rebuild()` | **S4 每次回写前强制调用**；S6 回归 |
| `paperapp.cli` 骨架 | S1–S6 持续扩展子命令 |
| `_V10` 路由范式 | S1–S5 每个新 API 都追加到同一张表 |
| `paperapp.html` 四面板 | S5 整合为「总览」页的一个 tab |
| `baseline_S0.json` | S6 最终报告对比基线 |
