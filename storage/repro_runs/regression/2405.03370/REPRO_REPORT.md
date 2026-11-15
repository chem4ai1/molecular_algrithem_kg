# 代码复现报告 · 2405.03370

- 研究问题：利用AntiFold模型对蛋白质语言模型推荐的抗体变体进行反向折叠评分，以筛选出结合亲和力降低的变体
- 领域：蛋白/抗体/RNA / 算法族：结构基逆折叠/序列设计
- 模式：lite　overall: **PARTIAL**
- 方法 4 / 代码 2 / 数据 3 / 指标 2
- SAU 判定：35 条，score 0.9429，coverage 1.0，drift 0.0571
- 最终评估：**PARTIAL**　Exec Rate 1.0 / Perf Gap 0.0 / Align_mixed 98.8
  - 降级原因：drift_rate 0.0571 > 0.05
- 未验证范围：原论文模型训练精度（本轮未训练；full 可行性见 TRAIN_FEASIBILITY.json）；原论文实验全量表；跨数据集泛化
- 执行：REPRO_SCRIPT.py 成功 / debug_tries 0 / 0.052s / ladder PASS

| 阶段 | verdict | 原因 |
|---|---|---|
| R0 | PASS |  |
| R1 | PASS |  |
| R2 | PASS |  |
| R3 | PASS |  |
| R4 | PARTIAL | metric accuracy 方向为启发式，需人工确认 |
| R5 | PASS |  |
| R6 | PASS |  |

dry 模式不执行训练；R6 无实跑值时为 BLOCKED 属预期。