# S6 · 修正闭环、全量回归、性能与最终报告

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 关闭 S0–S5 全部修正项，完成全量回归 / 性能 / 安全 / 故障注入演练，产出可复现的最终报告与实测指标 |
| 依赖 | S0–S5 全部完成且各自硬门通过 |
| 上游文档 | `../SCIFORGE_INTEGRATION_BLUEPRINT.md` §10–§12；本计划 [`README.md`](README.md) §5/§8 |
| 周期建议 | 4–5 个工作日 |
| 一句话验收 | 11 个硬门全部通过、8 项验收指标达标、64 条修正项闭环、最终报告可一键复现 |
| 硬门 | H1–H11 全量复验 |

---

## 1. 后端设计（修正与收尾）

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/paperapp/report.py` | 汇总 8 项指标 → `INTEGRATION_REPORT.md` + `INTEGRATION_METRICS.json` |
| 新建 | `scripts/test_all.sh` | 一键：单测 → 冒烟 → 审计 CLI → 报告（**新增脚本，不改现有 4 个**） |
| 新建 | `tests/test_paperapp_s6.py` | §6 的 14 项 |
| 新建 | `docs/plan/S6_FINAL_REPORT.md` | 实测值签字报告（本阶段产出） |
| 修改 | `src/capfactory/paperapp/cli.py` | `report / selftest / audit-all` 三个子命令 |
| 修改 | `scripts/smoke.sh` | 补 `selftest` 与 `audit-all` 摘要端点（可选） |
| 修改 | `src/capfactory/config.yaml` | 锁定生产阈值（阈值只允许在此改，代码不硬编码） |

### 1.2 修正闭环：64 条 `C` 项的收口方式

| 阶段 | 条数 | 关闭方式 |
|---|---:|---|
| S0 | 8 | 每条有对应 `T-S0-xx`；在报告中列「触发信号 → 是否已出现过 → 处理」 |
| S1 | 10 | 同上 |
| S2 | 10 | 同上 |
| S3 | 12 | 同上 |
| S4 | 12 | 同上 |
| S5 | 12 | 同上 |
| **合计** | **64** | 报告生成 `FIX_CLOSURE.json`：`{id, stage, regression_test, status, evidence}` |

**规则**：任何 `C` 项若在实际实施中出现过但对应测试未覆盖，必须**补测试后再关闭**；不允许仅写「已注意」。

### 1.3 性能基线

| 项 | 目标 | 测量方式 |
|---|---|---|
| `compile_paperspec` 全量 | < 15 s | `time cli spec-show --arxiv 2411.06608` |
| `verify_rebuild` 全量 | < 30 s | `time cli verify-rebuild` |
| `materialize` 单次 | < 20 s | `MATERIALIZE_REPORT.duration_ms` |
| 单测总耗时 | < 60 s | `time python3 -m unittest discover -s tests` |
| 26 阶段 run（stub） | < 180 s | `RUNSTATE.duration_ms` |
| `/overview` 响应 | < 300 ms | curl `-w %{time_total}` |
| `/graph/nodes?limit=200` | < 300 ms | 同上 |
| 首屏请求数 | ≤ 3 | 浏览器 Network 面板 |

**超标的修正顺序**：先查是否误把 6001 节点全量灌入（S5 C7），再查 `semantic_fp` 是否每次解析图（S1 C2），最后才考虑索引优化。**不得用降低阈值或跳过门的方式提速**。

### 1.4 安全检查

| 检查 | 判据 |
|---|---|
| AST 白名单 | 复用 `reprospec.executor.check_script_safety()`，禁止 `os.system` / 网络 / 文件写 |
| 路径穿越 | 所有 run/proposal id 只含 `[A-Za-z0-9:._-]`，`Path.resolve()` 后必须仍在 `storage/` 内 |
| 输入转义 | 前端统一 `esc()`；后端 JSON 不由字符串拼接生成 |
| 无裸 traceback | API 错误统一 `{ok:false, reason_code, detail}`，detail 截断 200 字 |
| 无删除操作 | 全仓 grep `rm -rf` / `shutil.rmtree` / `os.remove`，命中必须逐条评审（缓存只标 `valid_to`） |
| 依赖声明 | 新 import 必须已声明；不引入新的第三方依赖 |

### 1.5 迁移与兼容

| 项 | 处理 |
|---|---|
| `graph_source.py` 读 `batch10_app_v1.json` | **保持不动**；动态节点走 `/api/v10/paperapp/graph/nodes` |
| `app_reproduction.json` / 语义层图 | 全程只读，sha 与 S0 基线一致 |
| 旧页面 4 个 URL | 302 到单页 tab，报告链接不失效 |
| `Capability` 追加 8 字段 | 全部有默认值，既有 8 个测试不退化 |
| `TASK_SPECS` 只加字符串声明 | `classes/relations` tuple 未改，H3 保持 |
| 上游 xKG-main 的 798 项回归口径 | **不写入本项目验收**，用实际 `tests/` 8+ 新增项 |

---

## 2. 构建步骤（Step 1–12）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | 汇总 64 条 `C` 项 → `FIX_CLOSURE.json` 草稿 | 每条有 `regression_test` 字段 |
| 2 | 逐条核对：测试是否存在、是否真的覆盖触发信号 | 缺的补测试（补完再进下一步） |
| 3 | `report.py` 实现 8 项指标采集 + Markdown/JSON 双输出 | 报告字段与 README §7 指标一致 |
| 4 | `scripts/test_all.sh` 串起单测/冒烟/审计/报告 | 一条命令跑完，退出码正确 |
| 5 | 性能基线实测（8 项，各跑 3 次取中位数） | 全部达标或登记超标项 |
| 6 | 安全检查 6 项（含 grep 删除操作） | 0 高危；每条豁免有理由 |
| 7 | 故障注入演练（§5 表） | 每次都能被门/页面正确降级 |
| 8 | 兼容走查：`graph_source` / 旧页面 / `Capability` / `TASK_SPECS` | H3 + H9 通过 |
| 9 | 多篇回归：至少 3 篇（有仓库 / 无仓库 / 表格异常） | 降级均为真实数据缺陷，不伪装 PASS |
| 10 | 双跑一致性：同 `request_key` 两次 run | `output_sha` 相同、`llm_call_reduction` 可量化 |
| 11 | 生成 `S6_FINAL_REPORT.md` + `INTEGRATION_METRICS.json` | 11 硬门签字表填满实测值 |
| 12 | 人工评审 + 归档 `docs/plan/` 各阶段报告 | 见 §7 |

---

## 3. 修正清单（S6 自身）

| # | 坑 | 修法 | 回归 |
|---:|---|---|---|
| C1 | 用「降低阈值」让指标达标 | 阈值只在 `config.yaml`，测试锁定；报告中列阈值前后值 | T-S6-03 |
| C2 | 回归里出现 skip-as-pass | 测试输出断言无 `skipped` / `expectedFailure` 被当通过 | T-S6-01 |
| C3 | `FIX_CLOSURE.json` 只写「已注意」无测试证据 | 每条必须有 `regression_test` + `evidence` | T-S6-02 |
| C4 | 性能测量只跑 1 次受抖动影响 | 各跑 3 次取中位数，记录 3 个原始值 | T-S6-04 |
| C5 | 故障注入后忘记恢复 | 每个演练有 `restore` 步骤 + 恢复后 `audit-all` | T-S6-07 |
| C6 | 报告里的命令含旧路径（`.venv-linux` / `tests/Phase`） | 用 README §6 命令总表逐条核对 | T-S6-08 |
| C7 | `test_all.sh` 吞掉失败（末尾 `exit 0`） | `set -e` + 分步骤输出 + 汇总退出码 | T-S6-09 |
| C8 | 语义层 sha 在演练中被误改且未恢复 | 演练前后各记一次 sha 并断言相等 | T-S6-06 |

---

## 4. 前端相应设计（最终走查）

### 4.1 三态与降级最终检查（6 个 tab × 4 种状态 = 24 格）

| tab | 加载 | 空 | 错误 | 冻结 |
|---|---|---|---|---|
| T1 总览 | 骨架条 | 注册表未初始化提示 | `reason_code` + 重试 | 红条 + 禁 POST |
| T2 编排 | 26 卡片骨架 | 未编译提示 + 「运行一次」 | 面板级错误 | 同上 |
| T3 运行 | 进度条 | 无 run 提示 | 事件流失败独立降级 | 同上 |
| T4 缓存 | 表格骨架 | 无提案提示 | 详情抽屉错误态 | 同上 |
| T5 回写 | diff 骨架 | 未回写提示 | DRIFT 409 展开 diff | 同上 |
| T6 图节点 | 列表骨架 | 筛选无结果提示 | 详情抽屉错误态 | 同上 |

### 4.2 调试面板最终形态

`/debug/health` 增加：`FIX_CLOSURE` 状态、`test_all.sh` 最近一次退出码、8 项指标最近值、语义层 sha 与基线差异（应为 0）。面板提供「复制完整诊断包」按钮：把 `overview + debug/health + 最近 50 事件 + State.errors` 打包成一个 JSON 文本，便于贴进 issue。

### 4.3 与 S5 的关系

S6 **不新增页面**；只做走查、补三态遗漏、把调试面板接到 `report.py` 的指标上。任何新组件必须复用 `paperapp.css/js`。

---

## 5. 中间结果展示与调试计划表（S6 收尾与演练）

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `FIX_CLOSURE.json` | Step 1–2 | 调试面板 | `cat storage/sciforge/paperapp/FIX_CLOSURE.json` | — | 64 条各有测试 | 缺证据 | C3 |
| 2 | 单测输出 | Step 4 | 终端 + 报告 | `python3 -m unittest discover -s tests -v` | — | 无 skip-as-pass | 有 skipped | C2 |
| 3 | `smoke.sh` 输出 | Step 4 | 终端 | `bash scripts/smoke.sh` | — | 全绿 | FAIL | 按端点查 |
| 4 | `INTEGRATION_METRICS.json` | Step 3 | T1 + 调试面板 | `cli report --json` | `report_generated` | 8 项齐全 | 缺项 | 修 report.py |
| 5 | 性能原始值 ×3 | Step 5 | 报告附表 | `time cli verify-rebuild` | — | 中位数达标 | 超标 | §1.3 顺序修正 |
| 6 | 安全扫描结果 | Step 6 | 报告 | `grep -rnE 'rm -rf|shutil.rmtree|os.remove' src/capfactory/paperapp` | — | 0 高危 | 命中 | 逐条评审 |
| 7 | 故障注入演练记录 | Step 7 | 报告 + 调试面板 | 见下表 | 演练事件 | 均被正确降级 | 出现假 PASS | 补门 |
| 8 | 多篇回归报告 | Step 9 | T3 + 报告 | `cli run --arxiv <aid> --effort balanced` | 各 run events | 降级原因真实 | 伪装 PASS | 回查门 |
| 9 | 双跑一致性 | Step 10 | T4 命中率 | `cli cache-status` | `cache_hit` | `output_sha` 相同 | 不同 | 查 cache_key |
| 10 | 语义层 sha（演练前后） | Step 7/12 | header 常驻 | `sha256sum .../batch10_semantic_v4.json` | — | 相等 | 不等 | **立即停止** |
| 11 | `S6_FINAL_REPORT.md` | Step 11 | `docs/plan/` | `cat docs/plan/S6_FINAL_REPORT.md` | — | 11 硬门有实测值 | 空白 | 补签字 |
| 12 | `test_all.sh` 退出码 | Step 4/12 | CI | `bash scripts/test_all.sh; echo $?` | — | 0 | 非 0 | C7 |

### 5.1 故障注入演练矩阵（Step 7）

| # | 注入 | 期望表现 | 恢复 |
|---:|---|---|---|
| F1 | 故意构造不一致 delta | `materialize` 返回 `DRIFT`，前端按钮禁用，图 sha 不变 | 删除该 delta 记录 |
| F2 | 改 `semantic_fp` | 全部 `request_key` miss；`dependency_index` 只标受影响节点 | 恢复原图 |
| F3 | 改 `DYNAMIC_TBOX_VERSION` | 相关注册项 `revalidate` → `deprecated` + `valid_to` | 恢复版本号 |
| F4 | 停掉一个 `/api/v10` 端点 | 对应面板错误态，其余 5 tab 正常 | 恢复路由 |
| F5 | 构造跨论文 0.99 相似提案 | `action=proposal`，不复用 | 删除测试提案（标 `valid_to`） |
| F6 | 人为写 `attribution="llm_proposal"` 到语义层副本 | `audit-isolation` 报 >0 | **用副本**，恢复基线 |
| F7 | 截断 `events.ndjson` | `resume` 从 `next_action` 继续、`replay_ok` 可检出 | 恢复原文件 |
| F8 | `budget_floor.satisfied=false` 却写 PASS | 跨字段后检拒绝 | 修正 verdict |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S6-01 | 回归 | 全量单测 | 8 既有 + S0–S5 全部通过，**无 skip-as-pass** |
| T-S6-02 | 单元 | `FIX_CLOSURE` | 64 条，每条 `regression_test` 存在且测试真实存在 |
| T-S6-03 | 单元 | 阈值锁定 | 代码里无硬编码 0.92/0.98/6.0/8.0/3，全部来自 config |
| T-S6-04 | 性能 | 8 项基线 | 各 3 次取中位数，全部达标 |
| T-S6-05 | 安全 | 路径穿越 | `../../etc/passwd` 类 id 被拒，resolve 后仍在 `storage/` |
| T-S6-06 | 安全 | 无删除/语义层冻结 | grep 无高危；演练前后 sha 相等 |
| T-S6-07 | 演练 | F1–F8 | 每项期望表现成立且 `restore` 后 `audit-all` 通过 |
| T-S6-08 | 文档 | 命令一致性 | 报告中每条命令都能在 README §6 找到、路径真实存在 |
| T-S6-09 | 脚本 | `test_all.sh` | 失败时退出码非 0，不吞异常 |
| T-S6-10 | 集成 | 多篇回归 | 3 篇降级原因均为真实数据缺陷 |
| T-S6-11 | 集成 | 双跑一致 | 同 key 两次 `output_sha` 相同、`llm_call_reduction` 可量化 |
| T-S6-12 | API | `report` / `selftest` / `audit-all` | 200 + 11 硬门摘要 |
| T-S6-13 | 前端 | 24 格三态走查 | 6 tab × 4 态均有正确表现、零 console error |
| T-S6-14 | 签字 | `S6_FINAL_REPORT.md` | 11 硬门 + 8 指标实测值填满、可一键复现 |

**命令**：
```bash
bash scripts/test_all.sh
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-all
PYTHONPATH=src python3 -m capfactory.paperapp.cli report
python3 -m unittest tests.test_paperapp_s6 -v
```

---

## 7. 验收标准（签字表）

### 7.1 11 个硬门（全部复验）

| 门 | 判据 | 实测值 |
|---|---|---|
| H1 语义层冻结 | sha == S0 基线 | `______` |
| H2 重建等价 | `verify_rebuild().ok` | `______` |
| H3 基础契约 | 6/8/9 不变 | `______` |
| H4 缓存幂等 | `llm_calls==0` | `______` |
| H5 LLM 节点隔离 | 命中 0 | `______` |
| H6 spec 幂等 | 两次 hash 相同 | `______` |
| H7 门完整 | 26/26 verdict | `______` |
| H8 回写可追溯 | append-only + 100% provenance | `______` |
| H9 API 注册 | `{}` | `______` |
| H10 冒烟全绿 | `smoke.sh` 全 PASS | `____/____` |
| H11 回归全绿 | 累计 126 项全过 | `____/____` |

### 7.2 8 项验收指标（来自上游蓝图 §12）

| 指标 | 目标 | 实测 |
|---|---|---|
| `cache_hit_rate` | ≥ 0.90（重复跑同论文） | `______` |
| `llm_call_reduction` | 第二次跑下降 ≥ 50% | `______` |
| `n_new_nodes_per_run` | 四态分类计数齐全 | `______` |
| `promotion_rate` | 0.2–0.6 | `______` |
| `semantic_graph_hash_stable` | true | `______` |
| `rebuild_equivalence` | 100% | `______` |
| `provenance_coverage` | 100% | `______` |
| `stale_recompute_scope` | < 5% | `______` |

### 7.3 退出条件与人工签字

- `FIX_CLOSURE.json` 64 条全 closed；`S6_FINAL_REPORT.md` 11 硬门 + 8 指标填满；
- 3 篇回归 + 双跑一致性 + F1–F8 演练记录归档；
- **人工签字项**：确认无任何物理删除缓存/节点的操作；确认 `graph_source.py` 与 `app_reproduction.json` 未改；确认所有阈值来自 `config.yaml`；确认 `test_all.sh` 可一键复现报告；
- 全部通过 → 项目从「计划」转入「可交付」，`docs/plan/README.md` 进度看板全部勾选。

---

## 8. 交付物与回滚

**交付**：`report.py`、`scripts/test_all.sh`、`tests/test_paperapp_s6.py`、`FIX_CLOSURE.json`、`INTEGRATION_METRICS.json`、`INTEGRATION_REPORT.md`、`docs/plan/S6_FINAL_REPORT.md`、6 个阶段报告、截图与演练记录。

**回滚**：S6 只新增报告/脚本/测试，不改核心链路；如需回退，移除 `test_all.sh` 与 `report` 子命令即可，S0–S5 产物保持不变。演练注入的临时数据一律标 `valid_to` 并归档到 `storage/sciforge/_archive_s6_drills/`，**不删除**。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| `INTEGRATION_REPORT.md` / `INTEGRATION_METRICS.json` | 项目交付文档、后续迭代基线 |
| `scripts/test_all.sh` | CI / 日常回归 |
| `FIX_CLOSURE.json` | 调试面板、后续 issue 追踪 |
| 8 项指标 | `/overview` 聚合端点（S5）、T1 总览面板 |
| `S6_FINAL_REPORT.md` | `docs/plan/README.md` 进度看板签字依据 |
