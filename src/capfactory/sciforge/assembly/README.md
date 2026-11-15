# assembly/ — Stage3 装配层（A1–A5）

**唯一入口：`assemble_stage3()`**（由 `capfactory/sciforge/core.py` 导出）。
不调 LLM、不产生新事实、幂等（`inputs_sha`）、失败不吞。

| 阶段 | 文件 | 关键函数 |
|---|---|---|
| A1 Collect | `collect.py` | `collect()` → `Stage3Input`（完整性门 + sha） |
| A2 Normalize | `normalize.py` | `normalize()` 纯函数 → `NormalizedInput` |
| A3 Link | `link.py` | `link()` / `find_roots()` / `resolve_source_ref()` / `ast_align()` |
| A4 Materialize | `materialize.py` | `materialize()`（边前 `ontology.tbox.check_domain_range`） |
| A5 Verify | `verify.py` | `verify()` → 悬空边 / 三档门 |
| 契约 | `contract.py` | `Stage3Input / NormalizedInput / LinkPlan / Stage3Manifest` |
| 子模块 | `cards.py` | `build_algorithm_cards()` 族专属二级字段 |
| 子模块 | `leaderboard_refresh.py` | `refresh_leaderboard()` PG + 动态 SOTA |
| 子模块 | `hydrate.py` | `hydrate_derived_nodes()` 派生节点补齐 |

**落盘（out_dir，8 件）**：`STAGE3_MANIFEST.json` / `REPORT.md` /
`VIOLATIONS.json` / `LINK_PLAN.json` / `algorithm_cards.json` /
`leaderboard.json` / `graph.json` / `sources/*.csv`。

**存图统一在此处**：子模块不得各自 `graph.save(主图)`。
