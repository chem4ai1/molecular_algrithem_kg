# 阶段 4 · 论文复现

R0–R6 门控流水线：intake → resolve-method → ground-code → bind-data →
fix-metrics → execute → verify-and-replay。**零 LLM、只读图**。

| 职责 | 文件 |
|---|---|
| ReproSpec / SAU 契约 | `src/capfactory/reprospec/contract.py` |
| 确定性编译（5 类 SAU） | `compiler.py` |
| 运行时节点 materialize | `application.py` |
| 三层对齐评分 | `scoring.py` |
| 层次化 rubric 树 | `rubric_tree.py` |
| 树 → 运行时图（RubricNode/HAS_SAU） | `rubric_runtime.py` |
| 阶段图与执行 | `src/capfactory/sciforge/repro/{phasegraph.json,planner.py,runner.py,gates.py}` |

```bash
python stages/4_reproduction/compile_run.py paper:2411.06608 lite
```

产物：`storage/repro_runs/<aid>/` 下 `REPRO_SPEC.json`、`SAU_LIST.json`、
`RUBRIC_TREE.json`、`RUBRIC_TREE_SCORES.json`、`SAU_VERDICTS.json`、
`app_repro_runtime.json`、`FINAL_EVALUATION.json`、`REPRO_REPORT.md`。
