# 阶段 5 · 前端

FastAPI 后端 + 服务端渲染页面（无独立构建步骤）。

| 路由 | 页面 / 能力 |
|---|---|
| `/` | 首页 |
| `/data` | 三库（论文/算法/数据）树 + 节点卡片 |
| `/relations` | 关系浏览器 + 节点溯源卡片 + 单元格级溯源 |
| `/api/v6/data/*` | 三库树、节点卡片 |
| `/api/v8/relations/*` | 关系视图与实例 |
| `/api/v8/provenance/*` | 溯源追踪/审计/缺失 CSV/向量检索 |
| `/api/v8/task/*` | 任务规格/状态/构建 |
| `/api/v8/extraction/batch-status` | 全量抽取进度 |

| 职责 | 文件 |
|---|---|
| 应用装配、路由注册 | `src/capfactory/web/server.py` |
| 三库 API | `data_api.py` |
| 关系浏览器 API | `relation_api.py` |
| 溯源 API | `provenance_api.py` |
| 图源与分层加载 | `graph_source.py` |
| 页面与资源 | `static/{home,data,relations}.html`、`static/provenance_card.js` |

```bash
python stages/5_frontend/serve.py 8091
# http://127.0.0.1:8091
```
