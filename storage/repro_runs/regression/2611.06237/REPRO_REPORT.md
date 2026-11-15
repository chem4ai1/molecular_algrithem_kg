# 代码复现报告 · 2611.06237

- 研究问题：评估SO3LR-T模型在分子相互作用能、金属有机框架(MOFs)力学性质及反应化学过渡态搜索中的精度与适用性
- 领域：材料/晶体/分子动力学 / 算法族：机器学习势/神经力场
- 模式：lite　overall: **BLOCKED**
- 方法 7 / 代码 2 / 数据 21 / 指标 24
- SAU 判定：61 条，score 0.9836，coverage 1.0，drift 0.0164
- 最终评估：**PASS**　Exec Rate 1.0 / Perf Gap 0.0 / Align_mixed 98.8
- 未验证范围：原论文模型训练精度（本轮未训练；full 可行性见 TRAIN_FEASIBILITY.json）；原论文实验全量表；跨数据集泛化
- 执行：REPRO_SCRIPT.py 成功 / debug_tries 0 / 0.043s / ladder PASS

| 阶段 | verdict | 原因 |
|---|---|---|
| R0 | PASS |  |
| R1 | PASS |  |
| R2 | PASS |  |
| R3 | PASS |  |
| R4 | BLOCKED | metric spearman 方向为启发式，需人工确认; metric Pearson_r 方向为启发式，需人工确认; helical twist 方向未知; |
| R5 | PASS |  |
| R6 | PASS |  |

dry 模式不执行训练；R6 无实跑值时为 BLOCKED 属预期。