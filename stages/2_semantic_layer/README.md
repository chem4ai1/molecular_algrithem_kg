# 阶段 2 · 语义层回填与索引

把抽取报告写回语义层图（6 类 / 9 关系），再重建派生层。

| 职责 | 文件 |
|---|---|
| E1–E6 回填、代码联系、谱系边 | `src/capfactory/semantic/apply.py` |
| 溯源修复/索引/缺失 CSV/向量/快照 | `src/capfactory/semantic/refresh.py` |
| 溯源追踪与审计 | `provenance.py` |
| 语义层 TBox | `tbox_v4.py` |
| 语义层向量 | `vector_sync.py` |

```bash
python stages/2_semantic_layer/apply_refresh.py
```

产物：`storage/sciforge/batch10_semantic_v4.json`、`relation_index.json`、
`provenance/provenance_index.json`、`batch10_app_v1.json`（页面快照）。
