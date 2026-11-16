# S5 · 前端统一设计、API 整合、调试面板与三态规范

## 0. 阶段卡

| 项 | 值 |
|---|---|
| 目标 | 把 S0–S4 的临时页面收拢成**一套设计系统 + 一个单页 6 个 tab**，补齐 API 聚合、统一调试面板、错误/空/加载三态与可访问性 |
| 依赖 | S0–S4 全部后端与页面增量 |
| 上游文档 | `../SCIFORGE_INTEGRATION_BLUEPRINT.md` §8；本计划 README §1 现状基线 |
| 周期建议 | 5–6 个工作日 |
| 一句话验收 | `/api/status.api_registration_errors == {}`；`bash scripts/smoke.sh` 全绿；6 个 tab 零 console error |
| 硬门 | H9 / H10（+ H1/H2/H5/H7/H8 不退化） |

> **技术栈约束**：现有前端是 FastAPI + 原生 HTML/JS（`repro.html` 范式），**不引入 npm / Vite / React / 图表库**。所有新代码复用 `app.css` 的 CSS 变量与原生 `fetch`。

---

## 1. 后端设计（为前端服务的最小改动）

### 1.1 文件清单

| 动作 | 路径 | 职责 |
|---|---|---|
| 新建 | `src/capfactory/web/static/paperapp.css` | 设计系统：CSS 变量、组件类、6 态色、三态样式、响应式 |
| 新建 | `src/capfactory/web/static/paperapp.js` | 公共 JS：`State` / `api()` / `esc()` / `tbl()` / `renderStageCard()` / `badge()` / `devtools()` |
| 新建 | `src/capfactory/web/static/paperapp.html` | **替换** S0 的占位状态页为单页 6 tab |
| 新建 | `src/capfactory/web/paperapp_overview.py` | 聚合端点（一次拿全 6 个 tab 的摘要） |
| 新建 | `tests/test_paperapp_s5.py` | §6 的 16 项 |
| 修改 | `src/capfactory/web/paperapp_api.py` | 汇总 S0–S4 的全部路由 + 新增 `/overview`、`/graph/nodes`、`/graph/node/{id}`、`/debug/*` |
| 修改 | `src/capfactory/web/server.py` | 页面路由 `/paperapp` 显式注册（当前只有 `/`、`/data`、`/relations`、`/pipeline*`、`/repro`）；`WEB_API_MODULES` 保持 `paperapp_api` |
| 修改 | `src/capfactory/web/static/home.html` | 顶部导航加 1 个「论文生成」入口（**仅此一处**，不扩散） |
| 修改 | `scripts/smoke.sh` | 补 `/api/v10/paperapp/overview`、`/graph/nodes`、`/debug/health` 三项 |
| 归档 | `paperapp_cache.html` / `paperapp_timeline.html` / `paperapp_run.html` / `paperapp_diff.html` | 标 `deprecated` 保留 URL 可访问（重定向到单页对应 tab），**不物理删除** |

### 1.2 统一 API 表（`/api/v10/paperapp/*`）

| 分组 | 路径 | 方法 | 来源阶段 |
|---|---|---|---|
| 总览 | `/overview` | GET | S5 新增聚合 |
| 总览 | `/status` | GET | S0 |
| 注册 | `/registry`、`/registry/audit` | GET | S0 |
| 校验 | `/verify-rebuild`、`/gates/audit` | GET | S0/S2 |
| 缓存 | `/cache/requests`、`/cache/proposals`、`/cache/conflicts`、`/cache/nodes` | GET | S1 |
| 提案 | `/proposals/{id}`、`/promote` | GET/POST | S1 |
| 编排 | `/stages`、`/stages/{id}`、`/spec`、`/runs` | GET | S2 |
| 运行 | `/runs/{id}`、`/runs/{id}/stages`、`/loopbacks`、`/budget`、`/events`、`/verdict` | GET | S3 |
| 回写 | `/materialize/report`、`/materialize/diff`、`/stale`、`/promotions`、`/replay`、`/invalidate` | GET/POST | S4 |
| 图节点 | `/graph/nodes?layer=&status=&q=&limit=`、`/graph/node/{id}` | GET | S5 新增 |
| 调试 | `/debug/health`、`/debug/events?tail=`、`/debug/replay` | GET | S5 新增 |
| 动作 | `/run` | POST | S2/S3 |

**聚合端点 `/overview`**（一次请求替代 6 个并发，解决 S2–S4 页面各自发 4–7 个 `fetch` 的问题）：

```json
{"ok":true,"semantic_sha":"...","app_sha":"...","dynamic_tbox_version":"dyn-1.x.x",
 "n_semantic_nodes":6001,"n_app_nodes":8853,"n_registered_classes":12,
 "runs":{"total":3,"last":{"run_id":"...","status":"PASS","overall":"PASS"}},
 "cache":{"hit_rate":0.93,"n_proposals":41,"n_registered":14,"n_conflicts":3},
 "gates":{"n_missing":0,"n_not_applicable_without_file":0},
 "materialize":{"last_report":"...","equivalence":true,"semantic_sha_stable":true},
 "stale":{"scope":0.02,"items":2},
 "api_registration_errors":{}}
```

### 1.3 静态资源与响应头

- `/static` 已挂载（`server.py` L50-51），新 `paperapp.css/js` 直接放 `static/`；
- 所有列表 API 默认 `limit=200`、上限 `500`，超出返回 400（防浏览器被 6001 节点灌爆）；
- `/graph/node/{id}` 返回单节点 + 入/出断言各最多 50 条 + `evidence_ids` 对应的 `Evidence` 摘要 + `attribution`；
- GET 响应加 `Cache-Control: no-store`（调试数据必须实时）；POST 不加；
- 错误统一 `{ok:false, reason_code, detail}`，**不返回裸 traceback**；devtools 面板另走 `/debug/events`。

---

## 2. 前端设计

### 2.1 页面结构（单页 6 tab）

```
/paperapp
├─ header：标题 + arxiv 选择器 + run 选择器 + [刷新] [运行] [调试面板] + 全局状态徽章
├─ 顶部汇总条：semantic_sha / app_sha / dynamic_tbox_version / 缓存命中率 / 隔离审计 / 语义层冻结徽章
└─ tab 容器
   ├─ T1 总览   ← S0 状态页四面板（基线/等价性/注册中心/审计）+ /overview 聚合
   ├─ T2 编排   ← S2 时间线（26 阶段定义）+ PaperSpec 折叠区 + 门审计
   ├─ T3 运行   ← S3 run 详情（26 卡片/门表/回退/预算/事件流/产物树）
   ├─ T4 缓存   ← S1 五面板（L1/L2/L3/冲突/详情抽屉）
   ├─ T5 回写   ← S4 diff 视图 + stale 面板 + 晋升日志 + 回放上下文
   └─ T6 图节点 ← 新增：`app_generation.json` 节点检索/筛选/详情/证据链
```

URL 支持 `?tab=cache&run=<id>&proposal=<id>` 深链，便于把调试链接贴进报告。

### 2.2 设计系统（`paperapp.css`）

| 类别 | 规范 |
|---|---|
| 颜色 | 复用 `repro.html` 变量：`--bg #080e18 / --pnl #0c1526 / --bd #1d2940 / --tx #cfe0ff / --mut #7d8bb0 / --ok #3ddc97 / --bad #ff6b6b / --warn #ffb454 / --acc #8fb4ff / --cur #173c42` |
| 6 态色 | `PASS`=ok、`WARN`=warn、`FAIL`=acc、`NOT_APPLICABLE`=mut（但必须带文件图标）、`BLOCKED/ERROR`=bad、`null`=mut 虚线 |
| 排版 | `13px/1.6` 等宽/系统字体；面板 `.panel`、表格 `table`、徽章 `.st`、卡片 `.step`，与 `repro.html` 一致 |
| 组件类 | `.kv`（键值行）、`.mono`（哈希）、`.drawer`（右侧详情）、`.chip`（过滤器）、`.progress`（预算/进度）、`.pulse`（BLOCKED）、`.deprecated`（灰行 + 删除线仅对文本） |
| 响应式 | ≥1200px 六列卡片；768–1200 三列；<768 单列 + tab 横向滚动 |
| 可访问性 | tab 用 `role=tablist/tab/tabpanel` + `aria-selected`；按钮 `aria-label`；色彩不作为唯一信息（徽章带文字）；焦点可见 |

### 2.3 公共 JS（`paperapp.js`）

```javascript
const State = {arxiv:'', runId:'', tab:'overview', filters:{}, cache:{}, errors:{}};
async function api(path, opt) { /* fetch + 超时 10s + 统一错误结构 + 记录 State.errors */ }
function esc(s), tbl(head, rows), badge(state), kv(rows)
function renderStageCard(stage), renderVerdictTable(rows), renderProgressBar(v, max)
function devtools() { /* 右下角抽屉：最近 20 条 /debug/events、State.errors、/debug/health、复制所有 sha */ }
function route()  { /* 读 ?tab=&run=&proposal= → 切 tab + 拉数据 */ }
function refresh(){ /* Promise.allSettled 拉取当前 tab 所需端点，逐面板渲染 */ }
```

**单一 `refresh()` + `Promise.allSettled`**：任一面板失败只让该面板进入错误态，不白屏、不阻塞其它面板。

### 2.4 T6 图节点面板（新增，补上动态本体的可视化）

| 控件 | 行为 |
|---|---|
| 筛选 | `layer=semantic/application`、`status=registered/deprecated`、`q=` 关键词、`attribution=llm_proposal` 开关 |
| 列表 | 节点表：id / type / class / status / attribution / use_count / evidence 数 / valid_to |
| 详情抽屉 | 节点 attrs 全量 + 入边/出边各 50 条 + `derived_from` 链路 + `evidence_ids` 对应 Evidence（区分 `quote` 与 `title`）+ 六哈希 + `supersedes` |
| 高亮 | `attribution="llm_proposal"` 行左侧金色边框；`deprecated` 灰行；`stale` 橙色角标 |
| 空态 | 「该筛选下无节点（可尝试清除 `attribution` 过滤）」 |

> 这一页是「动态本体」唯一的可视入口：能直接看到哪些节点是 LLM 提案、哪些已注册、哪些被废弃，且不改 `graph_source.py`。

### 2.5 三态规范（所有 6 个 tab 统一）

| 态 | 表现 | 触发 |
|---|---|---|
| 加载 | 面板内 `校验中…` + 骨架条；按钮 `disabled` + 文案变化 | `fetch` 进行中 |
| 空 | `无数据` + 一句说明 + 可操作的下一步按钮（如「运行一次」） | 200 且 `items:[]` |
| 错误 | 显示 `reason_code` + 原始响应前 200 字 + 「重试」按钮；**不吞异常** | 非 2xx / 超时 / JSON 解析失败 |
| 部分失败 | 顶部黄色条「N 个面板加载失败」+ 各面板独立错误态 | `allSettled` 中有 rejected |
| 冻结 | 语义层 sha 与基线不一致时全页红色横幅 + 禁用所有 POST | `/overview.semantic_sha_stable=false` |

### 2.6 统一调试面板（右下角抽屉）

| 项 | 内容 |
|---|---|
| 健康 | `/debug/health`：图文件存在性、注册表可解析、锁文件状态、`api_registration_errors` |
| 事件 | `/debug/events?tail=50`：最近事件，`ts / stage / event / payload 摘要` |
| 重放 | `/debug/replay`：`replay_ok` + 与 `RUNSTATE` 的差异条数 + 「重建 RUNSTATE」按钮 |
| 错误 | 当前页面 `State.errors` 列表（含失败的 URL 与 reason_code） |
| 复制 | 一键复制 `semantic_sha / app_sha / request_key / spec_hash / run_id` |
| 跳转 | 由当前 tab 直达对应 CLI 命令（显示命令文本，可复制） |

---

## 3. 构建步骤（Step 1–12）

| Step | 动作 | 即时验证 |
|---:|---|---|
| 1 | 抽 `paperapp.css/js` 公共组件，先让 S0 状态页改用公共文件 | 页面外观与 `repro.html` 一致 |
| 2 | `paperapp.html` 改成 6 tab 骨架 + 深链路由 | `?tab=cache` 能切到对应面板 |
| 3 | 迁 S0 四面板 → T1；迁 S1 五面板 → T4 | 原有功能逐项对照不丢 |
| 4 | 迁 S2 时间线 / S3 run 详情 → T2/T3 | 26 卡片、门表、事件流可用 |
| 5 | 迁 S4 diff/stale → T5 | DRIFT 时按钮禁用逻辑保留 |
| 6 | 实现 `/overview` 聚合端点 + 顶部汇总条 | 1 次请求替代 ≥6 次 |
| 7 | 实现 `/graph/nodes`、`/graph/node/{id}` + T6 | `attribution` 过滤与详情抽屉可用 |
| 8 | `paperapp_overview.py` 注册到 `_V10`；`server.py` 加 `/paperapp` 页面路由 | `/api/status` 无注册错误；`/paperapp` 200 |
| 9 | 实现 `/debug/*` + 统一调试面板 | 能复制全部 sha、看到 `replay_ok` |
| 10 | 三态规范逐面板走查（含断网、404、超时、空目录、DRIFT 409） | T-S5-08..11 |
| 11 | `home.html` 加入口；4 个旧页面重定向到单页对应 tab | 直接访问旧 URL 不 404 |
| 12 | `smoke.sh` 追加 3 项；全量回归 + H9/H10 | 见 §7 |

---

## 4. 修正清单

| # | 坑 / 触发信号 | 修法 | 回归 |
|---:|---|---|---|
| C1 | 忘把 `paperapp_api` 或新模块加进 `WEB_API_MODULES` → 404 且静默 | `/api/status` 断言 `api_registration_errors == {}`；`smoke.sh` 加检查 | T-S5-01 |
| C2 | `/paperapp` 页面路由没在 `server.py` 注册 → 404 | 显式 `@app.get("/paperapp")` | T-S5-02 |
| C3 | 误把动态节点塞进 `graph_source.py`（它读 `batch10_app_v1.json`）→ 既有页面数据串 | 独立 `/graph/nodes` 直读 `app_generation.json`；不改 graph_source | T-S5-03 |
| C4 | 6 个 tab 各自发 4–7 个 fetch → 首屏 30+ 请求 | `/overview` 聚合 + 懒加载（切到 tab 才拉详情） | T-S5-04 |
| C5 | 一个 API 失败导致整页白屏 | `Promise.allSettled` + 逐面板错误态 | T-S5-08 |
| C6 | `innerHTML` 拼接未转义 → XSS / 显示错乱 | 统一 `esc()`，禁止裸插值 | T-S5-12 |
| C7 | 列表 API 一次返回 6001 节点 → 浏览器卡死 | `limit` 默认 200 / 上限 500 + 分页 | T-S5-05 |
| C8 | GET 被浏览器缓存 → 调试数据过期 | `Cache-Control: no-store` | T-S5-06 |
| C9 | 旧页面被物理删除 → 报告里的链接失效 | 302 重定向到单页 tab + 标 `deprecated` | T-S5-07 |
| C10 | 语义层 sha 不一致时仍可 POST 回写 | 全页红色横幅 + 禁用所有 POST | T-S5-13 |
| C11 | `NOT_APPLICABLE` 只用灰色表示，色盲用户无法分辨 | 徽章带文字 + 文件图标 | T-S5-14 |
| C12 | 引入 npm/React 破坏零构建部署 | 代码评审检查项；`static/` 只放 `.html/.css/.js` | T-S5-15 |

---

## 5. 中间结果展示与调试计划表

| # | 中间产物 | 生成时机 | 展示位置 | 调试命令 | 日志/事件 | 正常判据 | 异常信号 | 修复动作 |
|---:|---|---|---|---|---|---|---|---|
| 1 | `/overview` 聚合响应 | 首屏 / 刷新 | 顶部汇总条 | `curl -s localhost:8091/api/v10/paperapp/overview` | — | 10 个字段齐全 | 缺 `api_registration_errors` | C1 |
| 2 | `/api/status` 注册错误 | 服务启动 | 调试面板「健康」 | `curl -s localhost:8091/api/status \| python3 -m json.tool` | `app.state.api_registration_errors` | `{}` | 有键 | C1 |
| 3 | 6 个 tab 数据 | 切 tab 时 | 各 tab | 浏览器 DevTools Network | `State.errors` | 每 tab ≤2 个请求 | >6 个 | C4 |
| 4 | `/graph/nodes` 列表 | T6 | T6 列表 | `curl ".../graph/nodes?attribution=llm_proposal&limit=5"` | — | `count≤200` | 返回 6001 | C7 |
| 5 | `/graph/node/{id}` 详情 | T6 抽屉 | T6 抽屉 | 同上改路径 | — | 入/出边各 ≤50 | 超量 | 截断 |
| 6 | `semantic_sha` 冻结徽章 | 全程 | header 常驻 | `sha256sum storage/sciforge/batch10_semantic_v4.json` | — | 与基线一致 | 不一致 | 全页红条 + 禁 POST |
| 7 | `/debug/events` | 调试面板 | 调试面板 | `curl ".../debug/events?tail=20"` | 事件本身 | 与 `events.ndjson` 末尾一致 | 对不上 | 查 replay |
| 8 | `/debug/replay` | 调试面板 | 调试面板 | `cli verify-run --run <id>` | `replay_ok` | true | false | 重建 RUNSTATE |
| 9 | 三态（加载/空/错） | 各请求 | 各面板 | 断网 / 改 API 路径 / 清空目录模拟 | `State.errors` | 面板独立降级 | 白屏 | C5 |
| 10 | DRIFT 409 | 回写 | T5 | `cli materialize --dry-run` | `rebuild_checked` | 按钮禁用 + diff 展开 | 可强制写入 | 前端禁「强制」 |
| 11 | 旧 URL 重定向 | Step 11 | 浏览器 | `curl -I localhost:8091/paperapp_cache.html` | — | 302 到 `?tab=cache` | 404 | C9 |
| 12 | `smoke.sh` 结果 | Step 12 | 终端 | `bash scripts/smoke.sh` | — | 全绿 | 有 FAIL | 按端点查 |
| 13 | `home.html` 入口 | Step 11 | 主界面导航 | 浏览器点击 | — | 跳 `/paperapp?tab=overview` | 跳错 | 修链接 |
| 14 | 复制面板命令 | 调试面板 | 调试面板 | 点「复制 CLI」 | — | 命令可直接粘贴执行 | 命令含旧路径 | 更新命令表 |

---

## 6. 测试计划（挂钩）

| 编号 | 类型 | 用例 | 断言 |
|---|---|---|---|
| T-S5-01 | API | `/api/status` | `api_registration_errors == {}` |
| T-S5-02 | API | `/paperapp` 页面路由 | 200 且含 6 个 `role=tab` |
| T-S5-03 | 集成 | `graph_source.load()` 不受影响 | 节点数与基线一致（C3） |
| T-S5-04 | 前端 | 首屏请求数 | ≤3（overview + 2 个懒加载） |
| T-S5-05 | API | `limit` 上限 | 默认 ≤200；`limit=999` → 400 |
| T-S5-06 | API | 响应头 | GET 含 `Cache-Control: no-store` |
| T-S5-07 | API | 旧页面重定向 | 4 个旧 URL → 302 到对应 tab |
| T-S5-08 | 前端 | 单 API 失败 | 该面板错误态，其余 5 个 tab 数据正常 |
| T-S5-09 | 前端 | 空目录 | 200 + `items:[]` → 空态文案 + 下一步按钮 |
| T-S5-10 | 前端 | 超时 / 404 / 非 JSON | 三种错误态均显示 `reason_code` + 重试 |
| T-S5-11 | 前端 | DRIFT 409 | 回写按钮禁用、diff 展开、无「强制写入」入口 |
| T-S5-12 | 前端 | XSS 转义 | 含 `<script>` 的节点 label 被 `esc()` 转义 |
| T-S5-13 | 前端 | 冻结徽章 | 人工改 `semantic_sha_stable=false` → 红条 + 所有 POST 禁用 |
| T-S5-14 | 可访问性 | 色彩非唯一信息 | 6 态徽章均带文字；tab 有 `aria-selected` |
| T-S5-15 | 静态检查 | 零构建 | `static/` 无 `package.json` / 无 CDN 依赖 |
| T-S5-16 | 回归 | 全量 + 冒烟 | 96 项累计 + `smoke.sh` 全绿 |

**前端测试方式**（不引入 JS 测试框架）：
- Python 侧用 `urllib.request` 对 API 做契约测试（沿用 `scripts/smoke.sh` 风格）；
- HTML 静态用 `html.parser` 检查 `role=tab` 数量、无外链 CDN、无裸 `innerHTML` 插值；
- 浏览器交互用 `curl -I` 与人工清单（§7 签字项），截图留档。

**命令**：
```bash
python3 -m unittest tests.test_paperapp_s5 -v
bash scripts/serve.sh 8091
bash scripts/smoke.sh http://127.0.0.1:8091
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. 验收标准（签字表）

### 7.1 硬门

| 门 | 判据 | 实测值 |
|---|---|---|
| H9 API 注册 | `/api/status.api_registration_errors == {}` | `______` |
| H10 冒烟全绿 | `smoke.sh` 原 10 项 + S0–S5 新增项全 PASS | `____/____` |
| H1/H2/H5/H7/H8 不退化 | 重跑各阶段硬门 | `______` |
| H11 回归 | 112 项累计全过 | `____/____` |

### 7.2 指标

| 指标 | 目标 |
|---|---|
| 首屏请求数 | ≤ 3 |
| 首屏可交互时间（本地） | < 1.5 s |
| 6 个 tab console error | 0 |
| `/graph/nodes` 单次响应 | < 300 ms（limit=200） |
| 语义层 sha 冻结徽章 | 常驻且与基线一致 |

### 7.3 退出条件与人工签字

- 交付 6 个 tab 截图、调试面板截图、`smoke.sh` 输出、16 项测试结果；
- **人工签字项**：确认 `graph_source.py` 未修改；确认 4 个旧 URL 仍可访问（302）；确认无 npm/CDN 依赖；确认语义层冻结横幅在 sha 不符时真的禁用 POST；
- 硬门不过 → 不得进入 S6。

---

## 8. 交付物与回滚

**交付**：4 个新文件 + 4 个修改文件 + 4 个旧页面重定向标记 + `tests/test_paperapp_s5.py` + 截图 + `docs/plan/S5_FRONTEND_REPORT.md`。

**回滚**：
1. `server.py` 的 `/paperapp` 路由与 `home.html` 入口移除；`WEB_API_MODULES` 保留 `paperapp_api`（否则后端功能也断）；
2. `paperapp.html` 回退为 S0 的四面板版本（保留在 git 历史）；
3. 4 个旧页面取消重定向，恢复直接访问；
4. `smoke.sh` 回退到 S4 版本；重跑确认。

---

## 9. 上下游接口

| 产出 | 消费方 |
|---|---|
| 统一 6 tab 单页 | 用户日常操作入口；S6 回归走查清单 |
| `/overview` 聚合端点 | S6 指标报告的数据源 |
| `/debug/*` + 调试面板 | S6 故障注入演练、日常排障 |
| T6 图节点面板 | S6 动态本体可视化验收 |
| `paperapp.css/js` 设计系统 | 后续任何新页面复用 |
| 旧 URL 302 映射 | 保证前几阶段写进报告的链接不失效 |
