# 代码复现报告 · 2411.06608

- 研究问题：提出MolMiner，一种基于片段、几何感知且顺序无关的自回归模型，支持对12个理化性质的高维条件控制分子设计。
- 领域：分子生成与从头设计 / 算法族：片段/结构化生成
- 模式：lite　overall: **PARTIAL**
- 方法 6 / 代码 2 / 数据 6 / 指标 11
- SAU 判定：71 条，score 0.942，coverage 0.9718，drift 0.058
- 最终评估：**PARTIAL**　Exec Rate 1.0 / Perf Gap 0.0 / Align_mixed 98.2
  - 降级原因：drift_rate 0.058 > 0.05
- 未验证范围：原论文模型训练精度（本轮未训练；full 可行性见 TRAIN_FEASIBILITY.json）；原论文实验全量表；跨数据集泛化
- 执行：REPRO_SCRIPT.py 成功 / debug_tries 0 / 0.044s / ladder PASS

| 阶段 | verdict | 原因 |
|---|---|---|
| R0 | PASS |  |
| R1 | PARTIAL | JTNN 缺机理; MoLeR 缺机理 |
| R2 | PASS |  |
| R3 | PASS |  |
| R4 | PASS |  |
| R5 | PASS |  |
| R6 | PASS |  |

dry 模式不执行训练；R6 无实跑值时为 BLOCKED 属预期。