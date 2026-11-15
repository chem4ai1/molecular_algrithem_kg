# web/ — FastAPI 路由与页面

**唯一 app：`server.py`**，路由注册用显式清单 `WEB_API_MODULES`（7 个模块）。
注册失败不再静默 `except: pass`，而是写入 `app.state.api_registration_errors`
并体现在 `/api/status`。

## 注册清单与职责

| 模块 | 路由前缀 | 职责 |
|---|---|---|
| `home_api.py` | `/`, `/api/status` 支撑 | 主界面摘要、家族/论文统计 |
| `data_api.py` | `/api/v6/data/*` | 三库分类树、节点卡片、指标分组 |
| `pg_api.py` | `/api/v6/pg/*`, `/api/v6/benchmark/*` | PG 状态、基准概览与榜单 |
| `extract_v7.py` | `/api/v7/*` | 抽取状态、阶段详情、原文溯源、编辑重抽 |
| `algorithm_api.py` | `/api/v8/algorithm/*` | 18 族 schema、算法卡片、语义检索、抽取计划 |
| `benchmark_api.py` | `/api/v8/benchmark/*` | 7 族 schema、指标/结果列表、扩充报告 |
| `relation_api.py` | `/api/v8/relations/*`, `/relations` | 三视图关系浏览器 |
| `graph_api.py` | `/api/v6/graph/*` | 旧图谱 API（页面已砍，测试仍依赖，保留） |
| `extraction_api.py` | 内部 | `GRAPH_PATH` / `STATIC_DIR` / 链 enrich，供其它模块引用 |

## 页面路由（在 server.py）

`/`→home.html，`/data`→data.html，`/relations`→relations.html，
`/pipeline`→pipeline.html，`/pipeline/extract`→pipeline_extract.html。
`/data/graph` 302 → `/relations`；`/po /domain /algograph /extraction` 301 → `/`。

## 归档

- `static/graph.html`（旧力导向图谱页）→ `backup/capfactory/web/static/`
- `_legacy/`（v5 的 po/domain/algograph API）保留在包内但不注册。

## 约定

- 新 API 一律 `name_api.py` + `register(app)` 返回新增路由数，并加入
  `server.WEB_API_MODULES`；不要在各模块里直接 `app.add_api_route`。
- 前端只请求 `/api/v6|v7|v8/...`，不直接读文件。
