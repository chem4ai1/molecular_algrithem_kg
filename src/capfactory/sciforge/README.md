# sciforge/ — 抽取、装配、三库、复现

**推荐入口：`core.py`**（16 个导出），例如
`from capfactory.sciforge.core import assemble, run_e2e, plan_repro`。
`__init__.py` 是历史重量级聚合导出，被 660 个测试依赖，**保留但不再新增导出**。

## 核心链路

```
Stage2 产物 → assembly/assemble_stage3 (A1–A5)
   ├─ collect.py      收敛 6 份输入 + 完整性门 + inputs_sha 幂等
   ├─ normalize.py    纯函数归一（form/metric/方法名/单位/科技树 8 关系）
   ├─ link.py         三级根定位 + 原论文反查 + AST 对齐
   ├─ materialize.py  写图/run-scoped CSV，边前 TBox 校验
   ├─ cards.py        ★ 算法族二级字段卡片
   ├─ leaderboard_refresh.py ★ PG 榜单 + 动态 SOTA
   ├─ hydrate.py      派生节点补齐三库最小属性
   └─ verify.py       悬空边 + 三档门 PASS/PARTIAL/BLOCKED
→ extraction_e2e.py   端到端报告（8 件产物）
→ relation_layer.py   关系索引（论文/算法/数据三视图按链分组）
→ repro/              代码复现框架
```

## 目录分组

| 组 | 文件 | 说明 |
|---|---|---|
| ★ 入口 | `core.py`, `extraction_e2e.py`, `assembly/`, `repro/` | 后续改造主战场 |
| 流水线 | `pipeline.py`, `stage_extract.py`, `deepdive.py`, `blocks.py`, `sources.py`, `citations.py`, `table_extract.py` | Stage0–3 抽取 |
| 三库 | `paper_core.py`, `algorithm_problem.py`, `algorithm_schema.py`, `algorithm_fill.py`, `benchmark_fill.py`, `benchmark_schema.py`, `leaderboard.py`, `facets_v7.py`, `pgstore.py` | 属性/分类/榜单 |
| 关系 | `relation_layer.py`, `source_resolution.py` | 属性/关系分离 |
| 兼容与研究层 | `flow.py`, `reproflow.py`, `tasks.py`, `golden.py`, `contracts.py`, `polo.py`, `toy_egnn.py`, `manuscript.py`, `slice.py`, `populate.py`, `analyze.py`, `enrich.py`, `intake.py`, `tentacle.py`, `reprogen.py`, `repro_readiness.py`, `multistep_codegen.py`, `batch10.py`, `fill.py`, `registry.py`, `paper_types.py`, `llm_router.py` | **不在当前核心链路**，但被 660/81 测试引用，保留 |
| 已归档 | `classify_missing.py` | `backup/capfactory/sciforge/`（一次性 qwen 补分类脚本） |

## 约定

- **Stage3 只做确定性装配，不调 LLM 产生新事实**；新事实回 Stage2。
- **只移动不删除**：过时代码进 `backup/`，见 `backup/README.md`。
- **存图统一由 `assemble_stage3` 写 `out_dir/graph.json`**；子模块不得各自 `graph.save(主图)`。
- 节点 4 个溯源键：`source_locator / assembly_provenance / run_id / inputs_sha`；
  数据来源 `provenance` 不进数据库节点（属性/关系分离）。

## 回归

`tests/test_stage3_assembly.py`、`tests/test_p1_repro.py`、`tests/test_paper_relations.py`
覆盖装配、榜单、卡片、端到端、复现框架。
