# 跨阶段测试计划总表（测试挂钩 `T-Sn-xx`）

> 配套：[`README.md`](README.md) 总索引、S0–S6 各阶段文档 §6。
> 本表是**唯一编号真相源**：任何阶段文档新增测试必须在此登记；CI 按本表执行。
> 编号规则 `T-S<阶段号>-<两位序号>`；累计 **126 项**（8 既有回归 + 118 新增）。

---

## 1. 测试分层与运行方式

| 层 | 位置 | 运行 | 耗时目标 |
|---|---|---|---|
| 单元 | `tests/test_paperapp_s0.py … s6.py` | `python3 -m unittest tests.test_paperapp_s1 -v` | 各 < 5 s |
| 集成 | 同上（标记 `_fixture` 后缀的用例） | 同上 | 全流程 < 60 s |
| API 契约 | `scripts/smoke.sh` + 各 `T-Sn-xx` 中的 API 用例 | `bash scripts/smoke.sh http://127.0.0.1:8091` | < 30 s |
| 前端静态 | `html.parser` / `urllib` 检查 | `python3 -m unittest tests.test_paperapp_s5 -v` | < 3 s |
| 回归 | 既有 8 个测试 + 全部新增 | `python3 -m unittest discover -s tests -p "test_*.py" -v` | < 60 s |
| 演练 | S6 F1–F8 | `bash scripts/test_all.sh`（S6 起） | < 5 min |

**统一约定**：
- 全部在工作区路径运行；夹具放在 `tests/fixtures/paperapp_s<n>/`；
- 不调用真实 LLM、不跑真实 GPU、不做真实 LaTeX 编译（用 stub 产物）；
- 不使用删除命令；测试临时目录用 `tempfile.TemporaryDirectory()`（Python 标准库自动回收）；
- 测试不得 `skip` 冒充通过；`expectedFailure` 不允许用于硬门。

---

## 2. 编号总表

### 2.1 既有回归（基线，8 项）

| 编号 | 文件 | 作用 |
|---|---|---|
| B-01 | `tests/test_lifecycle.py` | 复现生命周期 |
| B-02 | `tests/test_nx_adapter.py` | nx 适配 |
| B-03 | `tests/test_paradigm_batch.py` | 范式批处理 |
| B-04 | `tests/test_reproduction_molminer.py` | MolMiner 复现 |
| B-05 | `tests/test_rubric_runtime.py` | rubric 运行时 |
| B-06 | `tests/test_rubric_tree.py` | rubric 树/失败分支 |
| B-07 | `tests/test_slice_baseline.py` | 切片基线 |
| B-08 | `tests/test_vocab_standard.py` | **词表契约（H3）** |

### 2.2 S0（12 项）· [S0-foundation.md](S0-foundation.md)

| 编号 | 类型 | 断言摘要 | 失败处理 |
|---|---|---|---|
| T-S0-01 | 单元 | 类正常注册 → `ok=True` + 日志增行 | 查 `register_class` |
| T-S0-02 | 单元 | 词表外类 → `class_not_in_vocab` | 查 vocab |
| T-S0-03 | 单元 | `active_classes` 过滤 | 查 status/task |
| T-S0-04 | 并发 | flock + 原子写无损坏 | 加锁 |
| T-S0-05 | 单元 | 类未 active 拒实例 | 查前置 |
| T-S0-06 | 单元 | 归一化消除 dict 顺序误报 | 修排序 |
| T-S0-07 | 单元 | `storage_cf`/`storage` sha 一致 | 统一路径 |
| T-S0-08 | API | `/api/status` 注册错误 `{}` | 补 `WEB_API_MODULES` |
| T-S0-09 | 集成 | `graph_source` 不受影响 | 禁止改 graph_source |
| T-S0-10 | 集成 | `registered_nodes=None` 与旧行为一致 | 回退 builder 改动 |
| T-S0-11 | 集成 | **H2** 全量 ≡ 增量 | DRIFT 拒写 |
| T-S0-12 | 回归 | 8 个既有测试全过 | 停下一阶段 |

### 2.3 S1（20 项）· [S1-cache.md](S1-cache.md)

| 编号 | 类型 | 断言摘要 | 失败处理 |
|---|---|---|---|
| T-S1-01 | 单元 | 4 dataclass 往返一致 | 修序列化 |
| T-S1-02 | 单元 | key 确定性 + 四维版本绑定 | 加 `sort_keys` |
| T-S1-03 | 集成 | **H4** 第二次 `llm_calls=0` | 查 cache_key |
| T-S1-04 | 单元 | 提案落盘数一致 | 查 put_proposal |
| T-S1-05 | 单元 | `canonical_id` 规范化 | 别名表 |
| T-S1-06 | 单元 | 词表外类 → proposal + 冲突日志 | 查受控词表 |
| T-S1-07 | 单元 | **跨论文 0.99 不复用** | 加 `paper_id` filter |
| T-S1-08 | 单元 | 阈值 0.98 / 0.92 三档 | 修阈值配置 |
| T-S1-09 | 单元 | 证据缺失保持 proposed | 查证据优先级 |
| T-S1-10 | 单元 | 门 FAIL 不进 validated | 查门 |
| T-S1-11 | 单元 | 类未 active 不晋升 | 查 registry |
| T-S1-12 | 单元 | kind=class 需 approver | 补人工批准 |
| T-S1-13 | 单元 | 语义层晋升需 NON_LLM + 批准 | 查硬规则 |
| T-S1-14 | 单元 | append-only 日志只增行 | 改 `"a"` 模式 |
| T-S1-15 | 单元 | `bump_usage` 只增 | 查回写 |
| T-S1-16 | 集成 | **H5** 语义层命中 0 | **立即停止** |
| T-S1-17 | 性能 | `semantic_fp` < 200 ms | 不解析图 |
| T-S1-18 | 单元 | deprecated 不删文件 | 标 `valid_to` |
| T-S1-19 | 单元 | embedding 恒 1024 维 | 查 config |
| T-S1-20 | API | 6 端点 + `/promote` 403 | 查路由 |

### 2.4 S2（18 项）· [S2-pipeline-front.md](S2-pipeline-front.md)

| 编号 | 断言摘要 | 失败处理 |
|---|---|---|
| T-S2-01 | 26 id 无环、`4broad` 在 `2` 前 | 显式 stage_order |
| T-S2-02 | **H6** 两次 `spec_hash` 相同 | 清除编译器里的 LLM |
| T-S2-03 | 注入异常 LLM 编译仍成功 | 只读 POGraph |
| T-S2-04 | 6 态封装 + `validate_verdict()==[]` | import 项目契约 |
| T-S2-05 | 1a hint 不进 spec | 只认 registered |
| T-S2-06 | gap_gate 逐块引用 | 按块 split 检查 |
| T-S2-07 | 判别动词缺失被拒 | 补词表 |
| T-S2-08 | 跨论文模块过滤 | id 带 arxiv |
| T-S2-09 | 中文词元不拆单字 | 复用 `_as_list` 思路 |
| T-S2-10 | **runner 不写图** | 静态 sha 检查 |
| T-S2-11 | `replay(events)==RUNSTATE` | 重建 RUNSTATE |
| T-S2-12 | 1b 单一写入者 | 加 no-op |
| T-S2-13 | MCTS <4 → BLOCKED | 补轮数门 |
| T-S2-14 | 环内 idea 降级 + warning | 修 DFS |
| T-S2-15 | `NOT_APPLICABLE` 有文件 | 补 verdict 文件 |
| T-S2-16 | 6 端点 + 非法 stage 400 | 查路由 |
| T-S2-17 | 时间线 11 卡片 / 6 态色 / 空态 | 修渲染 |
| T-S2-18 | 累计 58 项全过 | 停下一阶段 |

### 2.5 S3（20 项）· [S3-pipeline-back.md](S3-pipeline-back.md)

| 编号 | 断言摘要 | 失败处理 |
|---|---|---|
| T-S3-01 | L1–L13 表完整、各有预算 | 补登记 |
| T-S3-02 | **BA 全局 ≤2 轮** | 共享 `ba_rounds_used` |
| T-S3-03 | 回退必须改状态 | 消费失败证据 |
| T-S3-04 | 预算超限 → BLOCKED | 查记账 |
| T-S3-05 | budget-underuse WARN + justification | 补护栏 |
| T-S3-06 | toy FAIL ≠ BA | in-phase KILL |
| T-S3-07 | 后台派发、无 busy-wait | 修 6c 时序 |
| T-S3-08 | **runner 不写图** | 静态 sha |
| T-S3-09 | 双阈值 6.0 / 8.0 分开 | 两个具名常量 |
| T-S3-10 | `NOT_APPLICABLE` 无文件被检出 | 补文件 |
| T-S3-11 | PENDING 非白名单 → BLOCKED | 补 `na_verdicts` |
| T-S3-12 | events 重放一致 | 重建 RUNSTATE |
| T-S3-13 | 并行组 7∥8 / 11∥12 无竞争 | 分目录 |
| T-S3-14 | 26 阶段全流程（1 篇） | 查缺的 adapter |
| T-S3-15 | 崩溃恢复从 `next_action` | 查 resume |
| T-S3-16 | TDAL floors | 修脚本 |
| T-S3-17 | `budget_floor.satisfied=false` 拒 PASS | 跨字段后检 |
| T-S3-18 | 7 端点 + `limit>500` 400 | 查路由 |
| T-S3-19 | 26 卡片 + 门表 + 事件分页 | 修渲染 |
| T-S3-20 | 累计 78 项全过 | 停下一阶段 |

### 2.6 S4（18 项）· [S4-materialize.md](S4-materialize.md)

| 编号 | 断言摘要 | 失败处理 |
|---|---|---|
| T-S4-01 | 四类失效触发正确 | 查 invalidate |
| T-S4-02 | `dependency_index` 反向键齐全 | 重建索引 |
| T-S4-03 | **最小重算 <5%** | 查反查逻辑 |
| T-S4-04 | 不删缓存文件 | 标 `valid_to` |
| T-S4-05 | **DRIFT 拒写** | 修 delta |
| T-S4-06 | 并发回写无损坏 | 加文件锁 |
| T-S4-07 | 双路径 sha 一致 | 统一 `storage_cf` |
| T-S4-08 | deprecated 不删节点 | 标 `valid_to` |
| T-S4-09 | append-only 日志单调 | `"a"` 模式 |
| T-S4-10 | `use_count` 只增 | 查 bump_usage |
| T-S4-11 | `LESSONS.avoid` 硬排除 | 在 align 前过滤 |
| T-S4-12 | `attribution` 保持 `llm_proposal` | 加断言 |
| T-S4-13 | 回写后 `spec_hash` 可复算 | 强制重编译 |
| T-S4-14 | 只写 `app_generation.json` | 静态 sha |
| T-S4-15 | 报告 14 字段 + 两 sha 相等 | 修 report |
| T-S4-16 | 7 端点 / 409 DRIFT 不包装成 200 | 查错误处理 |
| T-S4-17 | diff 视图删除数为 0、DRIFT 禁按钮 | 修前端 |
| T-S4-18 | 累计 96 项全过 | 停下一阶段 |

### 2.7 S5（16 项）· [S5-frontend.md](S5-frontend.md)

| 编号 | 断言摘要 | 失败处理 |
|---|---|---|
| T-S5-01 | **H9** 注册错误 `{}` | 补模块注册 |
| T-S5-02 | `/paperapp` 200 + 6 tab | 补页面路由 |
| T-S5-03 | `graph_source` 不受影响 | 独立图 API |
| T-S5-04 | 首屏请求 ≤3 | `/overview` 聚合 |
| T-S5-05 | `limit` 默认 200 / 上限 500 | 加分页 |
| T-S5-06 | GET `Cache-Control: no-store` | 加响应头 |
| T-S5-07 | 4 个旧 URL 302 | 加重定向 |
| T-S5-08 | 单 API 失败不白屏 | `allSettled` |
| T-S5-09 | 空态文案 + 下一步 | 补空态 |
| T-S5-10 | 超时/404/非 JSON 三错误态 | 补 `reason_code` |
| T-S5-11 | DRIFT 409 禁按钮 | 去掉「强制写入」 |
| T-S5-12 | `esc()` 转义 `<script>` | 统一转义 |
| T-S5-13 | sha 不符 → 红条 + 禁 POST | 加冻结态 |
| T-S5-14 | 色彩非唯一信息 / `aria-selected` | 补文字与 ARIA |
| T-S5-15 | 零 npm / CDN | 静态检查 |
| T-S5-16 | **H10/H11** 冒烟 + 112 项全过 | 停下一阶段 |

### 2.8 S6（14 项）· [S6-hardening.md](S6-hardening.md)

| 编号 | 断言摘要 | 失败处理 |
|---|---|---|
| T-S6-01 | 全量回归无 skip-as-pass | 补真实断言 |
| T-S6-02 | `FIX_CLOSURE` 64 条有测试证据 | 补测试 |
| T-S6-03 | 阈值只在 `config.yaml` | 去硬编码 |
| T-S6-04 | 8 项性能基线（3 次中位数） | §1.3 顺序优化 |
| T-S6-05 | 路径穿越被拒 | `resolve()` 校验 |
| T-S6-06 | 无删除 + 演练前后 sha 相等 | **立即停止** |
| T-S6-07 | F1–F8 演练 + restore 后 `audit-all` | 补恢复步骤 |
| T-S6-08 | 报告命令与 README §6 一致 | 修文档 |
| T-S6-09 | `test_all.sh` 不吞失败 | `set -e` |
| T-S6-10 | 3 篇回归降级原因真实 | 回查门 |
| T-S6-11 | 双跑 `output_sha` 相同 | 查 cache_key |
| T-S6-12 | `report/selftest/audit-all` 端点 | 查路由 |
| T-S6-13 | 24 格三态走查 + 零 console error | 补三态 |
| T-S6-14 | `S6_FINAL_REPORT.md` 11 硬门 + 8 指标填满 | 补签字 |

**累计**：8 + 12 + 20 + 18 + 20 + 18 + 16 + 14 = **126 项**。

---

## 3. 测试夹具总表

| 目录 | 内容 | 被谁用 |
|---|---|---|
| `tests/fixtures/paperapp_s0/` | 3 节点最小语义图、2 条 delta | S0 |
| `tests/fixtures/paperapp_s1/` | 2 个 stub LLM 输出、3 提案（含跨论文近似）、1 冲突、1 未注册类 | S1 |
| `tests/fixtures/paperapp_s2/` | 1 论文最小语义图、`GAP_REPORT.md` 三块、含环 `IDEA_DAG.json` | S2 |
| `tests/fixtures/paperapp_s3/` | stub RESULT / ladder / ablation / figure audit / review state 各 1 | S3 |
| `tests/fixtures/paperapp_s4/` | 3 节点语义图、2 条 delta、1 条不一致 delta、2 个 `LESSONS.json` | S4 |
| `tests/fixtures/paperapp_s5/` | API 响应样例、含 `<script>` 的节点 label | S5 |
| `tests/fixtures/paperapp_s6/` | F1–F8 演练注入样本（**均为副本**，不碰真实图） | S6 |

**夹具纪律**：所有演练/故障注入使用副本；真实 `batch10_semantic_v4.json` 与 `app_reproduction.json` 在测试中只读。

---

## 4. 阶段门禁（测试不通过不得推进）

```
S0: B-01..08 + T-S0-01..12  全绿 → S1
S1: + T-S1-01..20           全绿 → S2
S2: + T-S2-01..18           全绿 → S3
S3: + T-S3-01..20           全绿 → S4
S4: + T-S4-01..18           全绿 → S5
S5: + T-S5-01..16           全绿 → S6
S6: + T-S6-01..14           全绿 → 交付
```

每阶段还须重跑 **H1–H11 中已生效的硬门**（见 README §5），并填该阶段 §7 签字表。

---

## 5. 一键命令（S6 起可用）

```bash
cd /home/zengshuxin/molecular_algrithem_design

# 全量单测
python3 -m unittest discover -s tests -p "test_*.py" -v

# 单阶段
python3 -m unittest tests.test_paperapp_s1 -v

# API 冒烟（需先启动服务）
bash scripts/serve.sh 8091 &
bash scripts/smoke.sh http://127.0.0.1:8091

# 审计三件套
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-isolation
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-gates
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-promotions
PYTHONPATH=src python3 -m capfactory.paperapp.cli verify-rebuild

# 一键全量（S6 交付）
bash scripts/test_all.sh
```

---

## 6. 覆盖率目标

| 层 | 目标 |
|---|---|
| `paperapp/registry.py` / `nodecache.py` / `align.py` / `validate.py` / `promote.py` | 行覆盖 ≥ 85% |
| `materialize.py` 六步 | 每步至少 1 个正向 + 1 个拒绝用例 |
| `gates.py` 6 态 | 6 个 state 全覆盖 + 1 个非法 state |
| `phasegraph.json` 26 阶段 | 每阶段至少 1 个 verdict 断言 |
| `/api/v10/paperapp/*` 全端点 | 每个至少 1 个 200 + 对应错误/空态 |
| 硬门 H1–H11 | 每个至少 1 个独立测试直接断言 |

> 覆盖率只是下限；**硬门相关路径必须 100%**，且不允许用 mock 绕过 `verify_rebuild()` / `audit-isolation()`。

---

## 7. 失败处理与升级路径

| 级别 | 情形 | 动作 |
|---|---|---|
| L0 | 单个单元用例失败 | 修实现 → 重跑该阶段测试 |
| L1 | 集成用例失败 | 检查夹具与真实图路径是否混淆；**不得改夹具迁就实现** |
| L2 | 硬门失败（H1/H2/H5/H6/H7/H8） | **立即停止推进**，回滚本阶段改动，填事故记录 |
| L3 | 语义层 sha 变化 / 出现物理删除 | **最高级**：停止全部工作，从 S0 基线恢复，人工复核 |
| L4 | API 冒烟失败 | 查 `/api/status.api_registration_errors` 与 `WEB_API_MODULES` |
| L5 | 前端白屏 / console error | 查 `allSettled` 与 `esc()`，逐面板降级验证 |

所有 L2 以上事件写 `storage/sciforge/paperapp/INCIDENTS.jsonl`（append-only），并在 `S6_FINAL_REPORT.md` 里列出处理结论。

---

## 8. 与验收标准的映射

| 硬门 | 直接对应的测试 |
|---|---|
| H1 语义层冻结 | T-S0-10 / T-S3-08 / T-S4-14 / T-S6-06 |
| H2 重建等价 | T-S0-11 / T-S4-05 |
| H3 基础契约 | B-08 / T-S0-03 |
| H4 缓存幂等 | T-S1-03 / T-S6-11 |
| H5 LLM 节点隔离 | T-S1-16 / T-S4-12 |
| H6 spec 幂等 | T-S2-02 / T-S2-03 |
| H7 门完整 | T-S2-15 / T-S3-10 / T-S3-11 |
| H8 回写可追溯 | T-S4-09 / T-S4-15 |
| H9 API 注册 | T-S0-08 / T-S5-01 |
| H10 冒烟全绿 | T-S5-16 / T-S6-01 |
| H11 回归全绿 | 各阶段最后一项 + T-S6-01 |

8 项验收指标由 S6 `report.py` 采集，见 [`S6-hardening.md`](S6-hardening.md) §7.2。

---

## 9. v2 测试增量（`T-V2-01..24`）

> 依据：[`../DESIGN_REFLECTION_V2.md`](../DESIGN_REFLECTION_V2.md) · [`V2_DELTA.md`](V2_DELTA.md) §3
> **既有 126 项编号与门禁全部保留**；v2 追加 24 项，累计 **150 项**；硬门 11 → **16**。

| 编号 | 阶段 | 断言摘要 | 硬门 |
|---|---|---|---|
| T-V2-01 | S0 | `HumanDecision` 是节点（有 id + verdict 文件），不是纯文本 | H13 |
| T-V2-02 | S0 | 6 个新本体类全部 `status=active` | — |
| T-V2-03 | S0 | `gate_timeout_policy` 来自 config，代码无硬编码 | H14 |
| T-V2-04 | S0 | `MINING_COVERAGE.json` 三态齐全、gap 连到信号 | H16 |
| T-V2-05 | S0/S1 | gate 超时后端 `BLOCKED`，前端无法自动通过 | H14 |
| T-V2-06 | S1 | dismissed 信号仍存在且有 `dismiss_reason` | H12 |
| T-V2-07 | S1 | `decision_fp` 变化 → `request_key` miss | H15/I2 |
| T-V2-08 | S1 | `vocab.candidates` 每项镜像成 `KnowledgeSignal` | H12 |
| T-V2-09 | S1 | `signal_capture_rate == 1.0`（5 类事件全覆盖） | H12 |
| T-V2-10 | S2 | D1 中文词元不拆单字、环标 `CyclicFeedback` | — |
| T-V2-11 | S2 | 人的方向无 `gap_anchor` 且无 exploratory 理由 → 同样被拒 | P2/I4 |
| T-V2-12 | S2 | `human_boost` 默认 0、有上限、可关闭 | I4 |
| T-V2-13 | S2 | `spec_hash` 随 `HumanDecision` 变化（可重算） | H15/I2 |
| T-V2-14 | S2 | D1–D4 默认关闭时既有 8 miner 输出逐字节不变 | H11/I7 |
| T-V2-15 | S3 | gate 超时 BLOCKED + verdict；`human_skip` 有 APPROVAL_LOG | H14 |
| T-V2-16 | S3 | 人方向失败写 `LESSONS.human_hypothesis_rollbacks` | I3 |
| T-V2-17 | S3 | `CONSTRAINT_REINJECTION` 每边界逐字复述（事件可查） | H15 |
| T-V2-18 | S3 | `exploration_regret` 护栏触发 WARN | I3 |
| T-V2-19 | S4 | `SUPERSEDES` 后 `verify_rebuild` 用新 `decision_fp` 重算 | I2/I5 |
| T-V2-20 | S4 | 失败 frontier 可 `untried` 重启且需理由 | I3 |
| T-V2-21 | S4 | decision 反查命中，`stale_recompute_scope < 5%` | H15 |
| T-V2-22 | S5 | gate 待办排最前、无「自动通过」文案；方向表单必填 | H14 |
| T-V2-23 | S5 | 5 个新端点 200/空态；`/overview` 含 3 个新计数 | H9 |
| T-V2-24 | S6 | 16 硬门 + 12 指标实测值填满 `S6_FINAL_REPORT.md` | 全部 |

**夹具**：`tests/fixtures/paperapp_v2/` —— 3 个词表外概念、2 个 ChoicePoint（含 1 个超时）、1 个 `HumanHypothesis`、1 个 `SUPERSEDES`、1 个失败 frontier。

**门禁扩展**：每阶段在原门禁基础上追加该阶段的 `T-V2-xx`；从首次生效阶段起重跑 H12–H16。S6 新增演练 F9「人中途改主意」/F10「gate 超时」/F11「词表外概念连续 3 次」/F12「人方向失败」。

**一键命令追加**：
```bash
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-signals
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-decisions
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-sovereignty
PYTHONPATH=src python3 -m capfactory.paperapp.cli audit-reinjection
PYTHONPATH=src python3 -m capfactory.paperapp.cli mining-coverage
```

**硬门映射增补**：H12→T-V2-06/08/09；H13→T-V2-01；H14→T-V2-03/05/15/22；H15→T-V2-07/13/17/19/21；H16→T-V2-04。

**覆盖率目标增补**：`signals.py` / `hitl.py` / `reinjection.py` 行覆盖 ≥ 85%；5 类信号事件 100%；`gate` 路径 100%（不允许 mock 绕过 `BLOCKED`）。
