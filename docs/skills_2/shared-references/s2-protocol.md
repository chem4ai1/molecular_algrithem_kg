# s2-protocol · S2 保真度阶梯、完整性与消融硬协议

> 源文件：`skills/shared-references/s2-protocol.md`（288 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `6c`/`10` |
| **输入节点（对齐）** | `ExperimentArm`；`LeaderboardEntry` |
| **输出节点（对齐）** | `S2Ladder`/`AblationLedger` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议的 `S2Ladder`/`AblationLedger`；三 gate 不各自建类 |

## 1. 解决的问题
### 1.1 核心问题
把「重复到收敛」从建议变成强制协议：ladder、integrity、ablation 三 gate 与固定阈值。
### 1.2 为什么需要
阈值是 config 常量而非 LLM 判断；`unverified full-set => NO claims above qualitative.`
### 1.3 不做的后果
toy 偶然优势或缺失消融被写成主结果。

## 2. 输入
### 2.1 输入知识节点
`S2_LADDER.json`：metric / subset / critic / fullset；`S2_INTEGRITY.json`：baseline reproduction / seeds；`ABLATION_LEDGER.json`：plans/results；`RESULT.json`；`config.yaml`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；由 `experiment-ladder`、`experiment-execution`、`ablation-planner`、`result-to-claim` 消费。
### 2.3 输入产物
`kernel/sciforge/s2/`（ladder / integrity / ablation）、`scripts/s2_*_gate.py`、`experiments/full/**`。

## 3. 输出
### 3.1 输出知识节点
`S2Ladder.critic.state`；`S2Integrity.verdict`；`AblationLedger.current_best`；`toy_gate / full_gate`；`fidelity`。
### 3.2 输出产物
`.sciforge/audits/{S2_LADDER,S2_INTEGRITY,ABLATION_LEDGER}.json`；`.sciforge/verdicts/`。
### 3.3 传递片段
无。

## 4. 判定与门
`MIN_BASELINE_REPRO=0.8`；`MAX_ENGINEER_ROUNDS=2`；`GAIN_TOLERANCE_PCT=0.15`；`MIN_SEEDS=2`；ablation 5–6；缺 ledger → FAIL；无实验 → SKIP；tie 不算赢。

## 5. 上下游
experiment-ladder / experiment-execution / ablation-planner → 本协议 → result-to-claim / paper-writing / auto-review-loop。

## 6. 映射
`reprospec/ladder.py` 的 GOOD/ENGINEER/BAD 与本协议同构；缺 `model_results.seeds` 时保真度封顶 qualitative。
