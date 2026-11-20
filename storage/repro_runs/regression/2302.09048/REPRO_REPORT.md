# 代码复现报告 · 2302.09048

- 研究问题：提出MiDi模型，通过混合图与3D去噪扩散，端到端联合生成分子图及其对应的3D原子排列，解决现有方法依赖预定义规则预测化学键导致不可微的问题。
- 领域：unknown / 算法族：unknown
- 模式：lite　overall: **BLOCKED**
- 方法 1 / 代码 0 / 数据 1 / 指标 2
- SAU 判定：10 条，score 0.6667，coverage 0.9，drift 0.3333
- 最终评估：**PARTIAL**　Exec Rate 1.0 / Perf Gap 0.0 / Align_mixed 70.5
  - 降级原因：SAU_score 0.6667 < 0.90
  - 降级原因：drift_rate 0.3333 > 0.05
  - 降级原因：Align_mixed 70.5 < 80
- 未验证范围：原论文模型训练精度（本轮未训练；full 可行性见 TRAIN_FEASIBILITY.json）；原论文实验全量表；跨数据集泛化
- 执行：REPRO_SCRIPT.py 成功 / debug_tries 0 / 0.048s / ladder PASS

| 阶段 | verdict | 原因 |
|---|---|---|
| R0 | BLOCKED | 缺 domain |
| R1 | PASS |  |
| R2 | BLOCKED | 算法→代码关系缺失 |
| R3 | PASS |  |
| R4 | PASS |  |
| R5 | PASS |  |
| R6 | PARTIAL | drift_rate 0.3333 > 0.2 |

dry 模式不执行训练；R6 无实跑值时为 BLOCKED 属预期。