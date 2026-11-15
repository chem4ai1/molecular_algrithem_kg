# static/ — 前端页面（5 个）

| 文件 | 路径 | 内容 |
|---|---|---|
| `home.html` | `/` | 主界面入口卡片 |
| `data.html` | `/data` | 论文/算法/数据三库：左侧分类树 + 右侧属性卡片；基准模型×指标矩阵（SOTA 高亮）、算法问题/机理、按问题找方法搜索框 |
| `relations.html` | `/relations` | **关系浏览器**：左实例列表 + 右按链类型分组关系；论文-论文链可点击跳转 |
| `pipeline.html` | `/pipeline` | 长 DAG 视图 |
| `pipeline_extract.html` | `/pipeline/extract` | 抽取阶段状态色、01–04 竖排、独立滚动、输入/输出/链、原文溯源、编辑重抽 |
| `app.css` | `/static/app.css` | 全站共用样式 |

## 约定

- 不再新增力导向图谱页面；关系展示统一在 `relations.html` 的链分组列表。
- 页面共用 `_page()` 读取（server.py），静态资源挂载在 `/static`。
- 链接里不要出现 `/data/graph`（已重定向）；用 `/relations`。
- 已归档：`graph.html`（旧图谱页）在 `backup/capfactory/web/static/`。
