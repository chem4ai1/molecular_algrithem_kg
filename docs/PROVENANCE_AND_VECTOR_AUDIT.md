# 向量库与溯源机制审查（2026-11-14）

> 目的：确认「基于语义层图谱做溯源修正」是否流畅，并落地
> 「算法/基准 → 论文 + 缺论文 CSV 清单」。

## 1. 结论

| 项 | 审查前 | 审查后 |
|---|---|---|
| 语义层向量索引 | ❌ 只有历史索引（34 算法 / 120 论文 / 111 块），与 291 节点语义层不同步 | ✅ `storage_cf/semantic/vector/` 291×1024 BGE 索引，检索结果带 `paper_ids` |
| 节点溯源字段 | ❌ 6 类节点里仅 21 个 Algorithm 有 `paper_id`，`source/evidence` 全 0 | ✅ `provenance_index.json`（150 节点 ↔ 36 论文），关系修复后算法覆盖 100% |
| 缺论文 CSV | ❌ 无 | ✅ 两份 CSV + JSON 报告 + 导出 API |
| 溯源修正 | ❌ 只能手工改图 | ✅ `repair()` 自动补关系、`trace()` 单节点追踪、向量检索带来源 |

**功能可行**，且已落地：算法 22 条缺论文全部自动修复（21 条靠 `paper_id` 属性、1 条靠抽取报告证据）；
基准 37 条全是 `benchmark:kb:*` 预置知识库基准（设计如此，不是缺陷）。

## 2. 向量库审查

### 2.1 历史索引（保留不动）

| 路径 | 规模 | 说明 |
|---|---|---|
| `storage_cf/vector/algorithms/vectors.npy` | 34×1024 | 旧 34 算法，2026-11-13 16:01 更新 |
| `storage_cf/vector/papers/vectors.npy` | 120×1024 | 论文摘要，2026-11-10 索引 |
| `storage_cf/pipeline/vector/chunks/vectors.npy` | 111×1024 | Stage1 分块 |
| `storage_cf/vector3/4/5/` | 6 文档 × 3 视角 | 早期试验 |

**问题**：这些索引各自独立、无统一 id 映射、不覆盖语义层的 56 算法 / 90 基准 /
50 模块 / 49 函数，也**不带论文溯源**。`algorithm_problem.search_algorithms`
用的就是旧 34 算法索引，语义层新增节点检索不到。

### 2.2 新语义层索引

`capfactory/semantic/vector_sync.py`：

```
build(graph)  → storage_cf/semantic/vector/nodes.npy (291, 1024)
              → nodes_meta.json：每条含 id / type / label / paper_ids
search(q, types, k) → 余弦检索，结果自带 paper_ids（可直接跳转溯源）
```

文本构造按类选核心属性（Paper 用研究问题+领域+关键词，Algorithm 用机理+能解决
的问题+族，CodeFunction 用作用+注释+函数类型…），`unknown` 值自动跳过。

`guides.retrieve_instances()` 的语义兜底已改为优先用这个索引，
旧 `search_algorithms` 降为二级回退 —— 抽取时的 A-Box 实例检索现在也能覆盖
语义层全部节点。

**Paper 节点特殊处理**：Paper 自身就是来源，`paper_ids=[self]`，
不溯源到它 `RELATED_TO` 的其它论文（初版曾误把引用目标当来源，已修）。

## 3. 溯源机制审查

### 3.1 证据层级（`provenance.trace()`）

| 优先级 | 证据 | 例子 |
|---|---|---|
| 1 | 图内关系 | `Paper-PROPOSES_METHOD->Algorithm`、`Paper-EVALUATED_ON->Benchmark` |
| 2 | 节点 `paper_id` 属性 | 谱系补建时写入的 `paper:2301.11259` |
| 3 | 抽取报告 | `semantic_extraction/2411.06608.json` 的 E2/E3/E6 命中 + `evidence` |
| 4 | 表格单元格 | `model_results[].paper_id` + `provenance: table_extract:1` |
| 5 | 向量建议 | 按 `papers.csv` 标题相似度给 `suggested_arxiv_id`（**只作建议，不算已溯源**） |

### 3.2 覆盖率（实测）

| 类 | 总数 | 关系可追 | 仅属性 | 预置库 | 无线索 | 覆盖率 |
|---|---:|---:|---:|---:|---:|---:|
| Algorithm（修复前） | 56 | 34 | 21 | 0 | 1 | 60.7% |
| **Algorithm（修复后）** | 56 | **56** | 0 | 0 | 0 | **100%** |
| Benchmark | 90 | 53 | 0 | 37 | 0 | 58.9% |

Benchmark 的 37 个孤儿全是 `benchmark:kb:moses / guacamol / qm9 / esol …`
这类**人工预置的知名基准**，本来就不属于某一篇论文；在 CSV 里单独标
「预置知识库基准（设计如此）」+ priority=low，不当作缺陷。

### 3.3 自动修复

`repair()` 把「有 `paper_id` 属性但无关系」的节点补上
`PROPOSES_METHOD` / `EVALUATED_ON`（先过 TBox domain/range 校验），
边上写 `provenance=provenance_repair`。本轮补了 **22 条**，幂等（第二次运行 n=0）。

## 4. 缺失论文 CSV 功能

`export_missing_csv()` 输出：

| 文件 | 行数 | 内容 |
|---|---:|---|
| `storage_cf/sciforge/provenance/missing_paper_algorithms.csv` | 1 | 唯一真无来源的算法 |
| `storage_cf/sciforge/provenance/missing_paper_benchmarks.csv` | 37 | 预置知识库基准 + 建议论文 |
| `provenance_report.json` | — | 覆盖率、孤儿分类、逐条原因 |
| `provenance_index.json` | — | 150 节点 ↔ 36 论文 正反向索引 |

CSV 列（12 列，UTF-8 BOM，Excel 可直接开）：

```
node_id, label, type, reason, paper_id_attr, report_hits,
model_result_sources, suggested_arxiv_id, suggested_title,
suggested_similarity, action, priority
```

`action` 三档：`自动补关系` / `人工确认建议论文` / `待补抽取`；
`priority` 三档：high / medium / low。
`suggested_*` 只用于人工复核，**不会自动改图**。

## 5. API

| 路径 | 作用 |
|---|---|
| `GET /api/v8/provenance/node/{id}` | 单节点完整溯源链（关系/属性/报告/表格/证据） |
| `GET /api/v8/provenance/audit` | 全图审计摘要 |
| `GET /api/v8/provenance/missing?kind=algorithm\|benchmark\|all` | 缺失列表 JSON |
| `POST /api/v8/provenance/export` | 重新导出 CSV + 索引 |
| `GET /api/v8/provenance/vector-search?q=...&types=Algorithm` | 向量检索（带 paper_ids） |
| `GET /api/v8/provenance/vector-stats` | 索引状态 |

## 6. 后续溯源修正是否流畅（评估）

| 场景 | 路径 | 评价 |
|---|---|---|
| 发现某算法/基准没来源 | `/audit` → `/missing` → CSV | ✅ 一键列出，带建议论文 |
| 只缺关系、已有 paper_id | `repair()` 自动补 | ✅ 已修 21 条 |
| 想看某节点从哪来 | `/node/{id}` 或 `trace()` | ✅ 四类证据聚合 |
| 想按语义找相关节点并溯源 | `/vector-search` → `paper_ids` | ✅ 检索结果自带来源 |
| 抽取时做实例检索 | `guides.retrieve_instances` → 语义层索引 | ✅ 已接 |
| 新增论文后更新溯源 | `semantic.refresh.refresh_all()` 或 `POST /api/v8/provenance/refresh` | ✅ 一条命令串 6 步 |
| 单元格级溯源 | `model_results[].provenance=table_extract:1` | ✅ 有，但还没在页面展示 |

**流畅性闭环**：`capfactory/semantic/refresh.py::refresh_all()` 把
「溯源修复 → provenance 索引 → 缺失 CSV → 关系索引 → 向量索引 → 应用层图」
串成一条命令（也暴露为 `POST /api/v8/provenance/refresh`），
实测 `ok=True`、291 节点 / 423 断言、向量 291×1024、应用层同步重建。
`repair()` 幂等（第二次运行 n=0），报告证据也纳入自动修复。

## 7. 边界

- `suggest_paper()` 用标题 token 重合，6385 行 `papers.csv` 里很多行 `arxiv_id` 为空，
  建议值可能只有标题没有 id；这是**建议**不是事实，不会写回图。
- 向量索引是构建时快照；语义层图改动后需 `vector_sync.build()` 重建
  （`nodes_meta.json.source` 记录了来源图，可据此判断是否过期）。
- 历史 `storage_cf/vector*/` 未删（旧模块/测试依赖），新索引独立目录，互不影响。
