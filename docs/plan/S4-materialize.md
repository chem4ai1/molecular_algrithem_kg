# S4 · 增量回写、失效传播、最小重算与跨 run 回放

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 把一次 run 里 `registered` 的 LLM 新节点**安全增量写回** `app_generation.json`，并实现失效、最小重算与 `LESSONS.json` 回放 |
| 依赖 | S0（`verify_rebuild`、文件锁）、S1（四态/晋升/日志）、S2（`PaperSpec`）、S3（完整 run + events） |
| 上游文档 | `../DYNAMIC_ONTOLOGY_NODE_CACHE.md` §6.3 / §7；`../SCIFORGE_INTEGRATION_BLUEPRINT.md` §4.1 / §9 P4 |
| 周期建议 | 5–6 个工作日 |
| 一句话验收 | `PROMOTION_LOG.jsonl` 只增行；语义层图 sha 不变；语义层单节点变更时 `stale_recompute_scope < 5%` |
| 硬门 | H8（+ H1/H2/H5/H7 不退化） |

> S4 是**唯一允许写 `app_generation.json`** 的阶段。S0 的 `allow_incremental_write` 在本阶段才置 `true`，且每次写前强制执行 `verify_rebuild()`。

---

## 1. 后端设计

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/paperapp/materialize.py` | `materialize(run_id, graph)` 六步流水线 + `MATERIALIZE_REPORT.json` |
| 新建 | `src/capfactory/paperapp/replay.py` | `LESSONS.json` / `RUN_PREPRINT.md` 跨 run 回放；`avoid` 硬排除 |
| 新建 | `src/capfactory/paperapp/invalidate.py` | 4 类失效触发 + `dependency_index` 反查 + `stale` 标记 |
| 新建 | `src/capfactory/paperapp/dependency_index.py` | 语义节点 → 应用节点反向索引（增量维护） |
| 新建 | `src/capfactory/web/static/paperapp_diff.html` | 回写 diff 视图 + stale 面板 |
| 新建 | `tests/test_paperapp_s4.py` | §6 的 18 项 |
| 修改 | `src/capfactory/paperapp/registry.py` | `bump_usage()` 移入统一实现；registry 增加 `last_used / source_runs` |
| 修改 | `src/capfactory/web/paperapp_api.py` | `/materialize*`、`/invalidate*`、`/stale*`、`/lessons*` |
| 修改 | `src/capfactory/paperapp/cli.py` | `materialize / invalidate / stale / replay / audit-promotions` |
| 修改 | `src/capfactory/config.yaml` | `allow_incremental_write: true`；`stale.threshold`、`min_reuse` |
| 修改 | `src/capfactory/applayer/builder.py` | `build_task_layer(..., registered_nodes=...)` 接入真实路径（S0 只做了等价验证） |

### 1.2 `materialize(run_id, graph)` 六步（**顺序不可换**）

```
1. 收集：从 node_cache/proposals/ 取本 run 全部提案
        从 S3 的 26 verdict 里确认对应阶段均无 BLOCKED/ERROR
2. 三步流水线：align() → validate() → can_promote()/promote()
   → 得到 registered 节点集合 R（每条带 evidence_ids + run_id + attribution）
3. 构造 delta = {nodes:[...], assertions:[...]}
   · 每个节点带 layer="application", task="generation", derived_from, miner,
     attribution="llm_proposal", evidence_ids, source_version, run_id
   · 每条 Assertion 带 attribution="llm_proposal", evidence_ids
4. verify_rebuild(delta)：全量重建 ≡ 上一版 ⊕ delta
   → 不一致 → reason_code="DRIFT"，**拒绝回写**并报 diff 前 20 条
5. 文件锁写 app_generation.json（fcntl.flock + 原子 replace）
   同步：registry.use_count / last_used / source_runs；PROMOTION_LOG 追加
6. 写 MATERIALIZE_REPORT.json + events.ndjson + LESSONS.json
   报告字段：n_proposed / n_validated / n_registered / n_rejected /
            n_conflicts / cache_hit_rate / semantic_graph_sha_before/after /
            rebuild_equivalence / files_written
```

**第 4 步是整套设计的安全底座**：如果增量回写与全量重建不一致，缓存就成了第二个真相源，前端会展示与重建不同的图。

### 1.3 `dependency_index.json`

```json
{
  "schema_version": "1.0",
  "semantic_sha": "sha256:...",
  "by_semantic_node": {
    "paper:2411.06608": ["appgap:2411.06608:...", "appidea:...", "appclaim:..."],
    "benchmark:zinc":   ["appcontract:zinc", "appmetric:..."]
  },
  "by_app_node": {"appgap:...": ["paper:2411.06608", "sourcepaper:..."]},
  "updated_at": "..."
}
```

**增量维护**：每次 `materialize` 后只更新本轮 delta 涉及的键；语义层图变更时用 `sha256` 逐节点比对 6001 个节点找出真正变化的 id（不是整图重扫应用节点）。

### 1.4 四类失效触发

| 触发 | 影响范围 | 动作 |
|---|---|---|
| `semantic_fp` 变化 | `dependency_index` 反查命中的**受影响应用节点** | 标 `stale`，只重跑相关阶段（不是 26 个） |
| `DYNAMIC_TBOX_VERSION` 变化 | 用该类/关系的全部注册项 | `revalidate()`；不通过标 `valid_to` + `deprecated` |
| `prompt_version` / `model_id` 变化 | 对应 `request_key` 自然 miss | 新 key 重新生成，旧缓存**保留可对照** |
| 显式 `invalidate(key)` / `supersedes` | 指定项 | `valid_to=now`，写 `PROMOTION_LOG`；**不删文件** |

`deprecated` 节点保留在图中但带 `valid_to`，前端以灰行显示；新版本用 `supersedes` 指向旧项。

### 1.5 `replay.py`（跨 run）

```
读上一批 run 的 LESSONS.json（4 类：failed_experiments / idea_rollbacks /
code_errors / what_worked，每条带 evidence + lesson）
  → 作为下一 run 的 prior：
     · what_worked → 起种子、提高 use_count
     · failed_experiments / idea_rollbacks / code_errors.avoid → **硬排除**
  → 写 REPLAY_CONTEXT.json 到新 run 目录，附 source_run_ids
```

**红线**：失败是可复用的判断，永远不是贡献；不得静默丢弃；阴性结果按 `result-to-claim` 的 negative-result discipline 进 Limitations。

### 1.6 配置项变化

```yaml
paperapp:
  allow_incremental_write: true      # S0 为 false
  min_reuse: 3
  stale:
    recompute_scope_ceiling: 0.05    # H8 指标
    max_stages_per_invalidation: 6
```

---

## 2. 构建步骤（Step 1–12）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | `dependency_index.py`：从 `app_generation.json` 构建一次全量索引 | `by_semantic_node` 覆盖 6001 个语义 id 中被引用者 |
| 2 | `invalidate.py` 四类触发 + `stale` 标记 | 单测 T-S4-01..04 |
| 3 | `materialize.py` 六步骨架（第 4 步先只返回 `ok` 不写） | `DRIFT` 时 `files_written=[]` |
| 4 | 接 S1 的 `align/validate/promote` | `n_registered` 与 `PROMOTION_LOG` 增行一致 |
| 5 | 接 S0 的 `verify_rebuild()` + 文件锁 | 并发两次 `materialize` 无写坏 |
| 6 | 真实写 `app_generation.json`（**先在副本上跑**） | 副本与全量重建逐断言一致后才切正式 |
| 7 | `registry.bump_usage` / `source_runs` 同步 | `use_count` 递增、`last_used` 更新 |
| 8 | `replay.py` + `REPLAY_CONTEXT.json` | `avoid` 项在新 run 提案里不出现 |
| 9 | `MATERIALIZE_REPORT.json` + events | `semantic_graph_sha_before == after` |
| 10 | `paperapp_api` 4 组 API + `paperapp_diff.html` | diff 视图显示 node/assertion 增删 |
| 11 | `smoke.sh` 追加 3 项；最小重算实测 | `stale_recompute_scope < 5%` |
| 12 | 全量回归 + H8 签字 | 见 §7 |

---

## 3. 修正清单

| # | 坑 / 触发信号 | 修法 | 回归 |
|---:|---|---|---|
| C1 | 跳过 `verify_rebuild` 直接写 → 缓存成第二真相源 | 第 4 步硬门；`DRIFT` 即拒绝 | T-S4-05 |
| C2 | 多 run 同时回写把 JSON 写坏 | `flock` + 原子 `os.replace`；写副本再切 | T-S4-06 |
| C3 | `storage_cf` 与 `storage` 双路径写导致两份 | 统一 `storage_cf`（软链） | T-S4-07 |
| C4 | 语义层单节点变更触发 26 阶段全量重跑 | `dependency_index` 反查 + 只标受影响节点 | T-S4-03 |
| C5 | deprecated 节点被物理删除 → 审计链断 | 只标 `valid_to` + `supersedes` | T-S4-08 |
| C6 | `PROMOTION_LOG.jsonl` 被重写 | `"a"` 模式 + 行数断言 | T-S4-09 |
| C7 | `use_count` 在 replay 后被清零 | 只增不减，`source_runs` 去重追加 | T-S4-10 |
| C8 | `LESSONS.avoid` 被 LLM 忽略 | 在 `align()` 之前做硬排除，不进 prompt 就算命中 | T-S4-11 |
| C9 | `attribution` 写入时被改成 `author_stated` | 构造 delta 时断言 `== "llm_proposal"` | T-S4-12 |
| C10 | 回写后忘记更新 `PaperSpec.spec_hash` | `materialize` 成功后强制重编译并记 `spec_hash_before/after` | T-S4-13 |
| C11 | `materialize` 写 `app_reproduction.json` | 静态检查：该文件 sha 不变 | T-S4-14 |
| C12 | 失效时清空整个缓存目录 | 只标 `valid_to`；归档优先 | T-S4-04 |

---

## 4. 前端相应设计（回写 diff + stale 面板）

### 4.1 页面 `/paperapp/diff`（`paperapp_diff.html`）

| 区域 | 数据源 | 展示 |
|---|---|---|
| 回写概览 | `/api/v10/paperapp/materialize/report?run=` | `n_proposed / n_validated / n_registered / n_rejected / n_conflicts` 五个数字卡；`rebuild_equivalence` 徽章 |
| 节点 diff | `/api/v10/paperapp/materialize/diff?run=` | 新增节点表（id / type / class / evidence 数 / attribution）+ 新增断言表（source/relation/target）；`-` 删除项应为 0（deprecated 不删） |
| 等价性 | 同上 | `n_missing / n_extra / n_attr_diff / n_rel_diff` 四个计数 + diff 前 20 条 |
| stale 面板 | `/api/v10/paperapp/stale` | 受影响语义节点 → 受影响应用节点 → 需重跑阶段；`stale_recompute_scope` 百分比进度条 |
| 晋升日志 | `/api/v10/paperapp/promotions?limit=100` | append-only 行表：ts / proposal / from→to / rule / approver |
| 回放上下文 | `/api/v10/paperapp/replay?run=` | `source_run_ids`、`what_worked` 条目、`avoid` 硬排除条目 |

### 4.2 API 契约

| 路径 | 方法 | 200 | 错误/空态 |
|---|---|---|---|
| `/api/v10/paperapp/materialize/report?run=` | GET | `MATERIALIZE_REPORT.json` 全量 | 未回写 → 404 `not_materialized` |
| `/api/v10/paperapp/materialize/diff?run=` | GET | `{nodes_added:[], assertions_added:[], nodes_removed:[], equivalence:{...}}` | — |
| `/api/v10/paperapp/stale` | GET | `{items:[...], scope, ceiling, stages_to_rerun[]}` | 无 → `items:[], scope:0` |
| `/api/v10/paperapp/promotions?limit=` | GET | `{items:[...], count, append_only:true}` | 空 → `items:[]` |
| `/api/v10/paperapp/replay?run=` | GET | `{source_run_ids, what_worked[], avoid[], n_hard_excluded}` | — |
| `/api/v10/paperapp/invalidate` | POST | `{ok, key, valid_to, affected_nodes[]}` | key 不存在 → 404 |
| `/api/v10/paperapp/materialize` | POST | `{ok, report, files_written}` | `DRIFT` → 409 `{reason_code:"DRIFT", diff:[...]}` |

### 4.3 状态与交互

- 「执行回写」按钮默认**禁用**，仅当 `rebuild_equivalence.ok=true` 且当前用户填入 `approver` 后可用；
- 回写返回 409 DRIFT → 展开 diff 面板，红色高亮，禁止重试直到修复（前端不提供「强制写入」）；
- stale 进度条超 `ceiling` 变红并显示「需检查 dependency_index」；
- 晋升日志表按 ts 倒序，附「只增行」校验徽章（前端按相邻 ts 单调性自检）；
- 「失效」操作二次确认，成功后该行变灰显示 `valid_to`，**不从表格移除**；
- 三态齐全；`fetch` 全 `allSettled`；大表默认 `limit=100` + 分页。

### 4.4 与既有页面关系

不改 `graph_source.py`；diff 视图通过 `/api/v10` 直读 `app_generation.json` 与 run 产物。S5 收拢为「回写」tab。

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `dependency_index.json` | Step 1 / 每次回写 | stale 面板 | `cat storage/sciforge/node_cache/index.json` | `index_rebuilt` | 反向键齐全 | 空索引 | 重建索引 |
| 2 | `delta`（内存） | materialize 第 3 步 | diff 视图 | `cli materialize --dry-run --run <id>` | `delta_built` | 节点带 7 个必填字段 | 缺 `derived_from` | 修 delta 构造 |
| 3 | `REBUILD_EQUIVALENCE.json` | 第 4 步 | 等价性面板 | `cli verify-rebuild --delta <file>` | `rebuild_checked` | `ok=true` | `DRIFT` | **拒绝回写**，C1 |
| 4 | `app_generation.json` | 第 5 步 | diff 视图 | `sha256sum .../app_generation.json` | `app_written` | 与全量重建一致 | 两路径 sha 不同 | C3 |
| 5 | `PROMOTION_LOG.jsonl` | 第 5 步 | 晋升日志 | `cli audit-promotions` | `promoted` | 行数只增 | 行数减少 | C6 |
| 6 | `registry.use_count` | 第 5 步 | L3 面板 | `cli cache-status` | `usage_bumped` | 递增 | 被清零 | C7 |
| 7 | `MATERIALIZE_REPORT.json` | 第 6 步 | 回写概览 | `cat .../MATERIALIZE_REPORT.json` | `materialized` | `semantic_sha_before==after` | 不等 | **立即停止** |
| 8 | `LESSONS.json` | run 16 / 回写 | 产物树 | `cat .../LESSONS.json` | `lesson_written` | 4 类齐全 | 缺类 | 回 16 |
| 9 | `REPLAY_CONTEXT.json` | 新 run 启动 | 回放面板 | `cli replay --run <id>` | `replayed` | `avoid` 生效 | `avoid` 提案仍出现 | C8 |
| 10 | `stale` 标记 | 失效触发 | stale 面板 | `cli stale --scope` | `invalidated` | `scope<5%` | 超阈值 | C4 |
| 11 | `valid_to` / `supersedes` | 失效/升级 | L3 灰行 + diff | `cli cache-status --all` | `deprecated` | 文件仍在 | 文件消失 | C5 |
| 12 | `spec_hash_before/after` | 回写后重编译 | 回写概览 | `cli spec-show --arxiv <aid>` | `spec_recompiled` | 值变化且可复算 | 未变化 | C10 |
| 13 | 语义层 sha | 全程 | 全局常量展示 | `sha256sum .../batch10_semantic_v4.json` | — | 与 S0 基线一致 | 不一致 | 停止 + 恢复 |
| 14 | `app_reproduction.json` sha | 全程 | 全局常量展示 | 同上（改用该文件） | — | 不变 | 变化 | C11 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S4-01 | 单元 | 四类失效触发 | 各自产生正确的 `stale`/`deprecated`/`cache_miss`/`valid_to` |
| T-S4-02 | 单元 | `dependency_index` 构建 | 每个应用节点都有反向键 |
| T-S4-03 | 集成 | **最小重算** | 语义层单节点变更 → `stale_recompute_scope < 0.05` |
| T-S4-04 | 单元 | 不删缓存 | `invalidate` 后文件仍存在、`valid_to` 非空 |
| T-S4-05 | 集成 | **DRIFT 拒写** | 构造不一致 delta → `reason_code=DRIFT`、`files_written=[]` |
| T-S4-06 | 并发 | 两 run 同时回写 | JSON 完好、无丢失、锁生效 |
| T-S4-07 | 单元 | 双路径一致 | `storage_cf` 与 `storage` 的 sha 相同 |
| T-S4-08 | 单元 | deprecated 不删节点 | 图中节点仍在、`valid_to` 非空、`supersedes` 指向新项 |
| T-S4-09 | 单元 | append-only 日志 | 3 次回写后日志行数单调增、原行未变 |
| T-S4-10 | 单元 | `bump_usage` | `use_count` 只增、`source_runs` 去重 |
| T-S4-11 | 集成 | `LESSONS.avoid` 硬排除 | 被排除提案不进入新 run 的 `align()` |
| T-S4-12 | 单元 | attribution 保持 | delta 与落盘节点 `attribution=="llm_proposal"` |
| T-S4-13 | 集成 | 回写后重编译 | `spec_hash` 变化且可复算 |
| T-S4-14 | 集成 | 只写目标图 | `app_reproduction.json` 与语义层 sha 不变 |
| T-S4-15 | 单元 | `MATERIALIZE_REPORT` 字段 | 14 个字段齐全、两 sha 相等 |
| T-S4-16 | API | 7 个端点 | 200/404/409 语义正确；DRIFT 不被包装成 200 |
| T-S4-17 | 前端 | diff 视图 | 新增/删除分列、删除数为 0、DRIFT 时按钮禁用 |
| T-S4-18 | 回归 | 全量 | 8+S0 12+S1 20+S2 18+S3 20+S4 18 全过 |

**夹具**：`tests/fixtures/paperapp_s4/` 放一份 3 节点语义图 + 2 条 delta + 1 份故意不一致的 delta + 2 个 run 的 `LESSONS.json`。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s4 -v
PYTHONPATH=src python3 -m capfactory.paperapp.cli materialize --run <run_id> --dry-run
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-promotions
PYTHONPATH=src python3 -m capfactory.paperapp.cli stale --scope
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. 验收标准（签字表）

### 7.1 硬门

| 门 | 判据 | 实测值 |
|---|---|---|
| H8 回写可追溯 | `PROMOTION_LOG` 只增行；每个 registered 节点带 `evidence_ids + run_id + attribution` | `______` |
| H2 重建等价 | 每次回写前 `verify_rebuild().ok=true` | `______` |
| H1 语义层冻结 | `semantic_sha_before == after == S0 基线` | `______` |
| H5 隔离 | `audit-isolation` 命中 0 | `______` |
| H11 回归 | 96 项累计全过 | `____/____` |

### 7.2 指标

| 指标 | 目标 |
|---|---|
| `stale_recompute_scope` | < 5%（语义层单节点变更） |
| `materialize` 单次耗时 | < 20 s |
| `promotion_rate` | 0.2–0.6 |
| `provenance_coverage` | 100% |
| `rebuild_equivalence` | 100% 通过 |

### 7.3 退出条件与人工签字

- 交付两次真实回写（含一次故意 DRIFT 被拒）、`MATERIALIZE_REPORT.json`、18 项测试结果、diff 页面截图；
- **人工签字项**：确认 `allow_incremental_write=true` 且第 4 步硬门未被绕过；确认无节点被物理删除；确认 `LESSONS.avoid` 生效；
- 硬门不过 → 不得进入 S5。

---

## 8. 交付物与回滚

**交付**：5 个新文件 + 5 个修改文件 + `tests/test_paperapp_s4.py` + 夹具 + `MATERIALIZE_REPORT.json` 样例 + `docs/plan/S4_MATERIALIZE_REPORT.md`。

**回滚**：
1. 用 S0 基线恢复 `app_generation.json`（`bash scripts/rebuild.sh` 可重建等价版本）；
2. `allow_incremental_write` 回 `false`；
3. 回写过的注册项标 `valid_to` + `deprecated_reason="rollback_s4"`，**不删**；
4. `dependency_index.json` 重跑 Step 1；
5. 重跑 `bash scripts/smoke.sh` 回到 S3 的 22/22。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| 已回写的 `app_generation.json` | S5 图节点面板、S6 指标基线 |
| `dependency_index` / `invalidate` | S5 stale tab、S6 失效演练 |
| `REPLAY_CONTEXT.json` | S5 回放面板、S6 跨 run 指标 |
| `MATERIALIZE_REPORT.json` | S5 回写 tab、S6 最终报告 |
| `materialize()` 六步 | S6 回归用例的基准流程 |
| `paperapp_diff.html` | S5 整合为「回写」tab |
