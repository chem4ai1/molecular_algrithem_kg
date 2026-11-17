# experiment-ladder · subset → full 阶梯与三态 Critic

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/experiment-ladder/SKILL.md`（76 行）
> 类型：support · Phase 6c · 代码佐证：`kernel/sciforge/s2/ladder.py`（`decide` / `relative_gain`）、`scripts/s2_ladder_gate.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段外·执行基础设施 |
| **SciForge 26 节点** | `6c` |
| **输入节点（对齐）** | `ExperimentArm`；`LeaderboardEntry` |
| **输出节点（对齐）** | `LeaderboardEntry`(task)；`Evidence` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 task-r 节点 `S2Ladder`(subset/critic.state/fullset/relative_gain_pct)：现有节点无三态 Critic 与 engineer 轮次 |

## 1. 解决的问题

### 1.1 核心问题
用 subset → full-set ladder 与三态 Critic（`GOOD / ENGINEER / BAD`）阻止子集偶然优势直接变成 claim。

### 1.2 具体场景 / 为什么需要
- `Reproduce the incumbent on the subset` —— 先复现 baseline。
- `GOOD ⇒ run the FULL set for both arms with identical protocol.` —— ties 不算赢。
- engineered 轮数上限 2，防止无限「修一修」。

### 1.3 不做的后果
- 子集上偶然赢 0.3 个点就写成主结果；full set 上结论反转。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Experiment` | `experiments/subset/baseline.value` | subset 实验 | 必须 |
| `Experiment` | `experiments/subset/candidate.value` | subset 实验 | 必须 |
| `Metric` | `name / direction` | `EVALUATION_PROTOCOL.json` | 必须 |
| `Experiment` | `fullset.baseline.value / candidate.value` | full 实验 | 必须 |
| `Critic` | `state` | `ladder.py` | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Job | `Reproduce the incumbent on the subset` | baseline 先行 |
| GOOD 分支 | `GOOD ⇒ run the FULL set for both arms with identical protocol.` | 同协议 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `experiments/subset/baseline/**` | baseline 复现 |
| `experiments/subset/candidate/**` | 候选 |
| `experiments/full/**` | 全量 |
| `kernel/sciforge/s2/ladder.py` | decide / relative_gain |
| `scripts/s2_ladder_gate.py` | 门 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `S2Ladder` | `schema_version / problem_id` |
| `Metric` | `name / direction` |
| `Subset` | `n / baseline / candidate` |
| `Critic` | `state / engineer_rounds` |
| `FullSet` | `verified / baseline / candidate` |
| `S2Ladder` | `relative_gain_pct` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/S2_LADDER.json` | `metric / subset / critic / fullset / relative_gain_pct` | gate 账本 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无 | — | — |

## 4. 判定与门

| 门 | 脚本 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| `s2_ladder` | `scripts/s2_ladder_gate.py` | 有实验缺 ledger ⇒ FAIL | exit 2 | 边界拒绝 |
| 无实验 | gate | SKIP | exit 0 | — |
| Critic 状态 | `ladder.py` | `BAD / GOOD / ENGINEER` | — | BAD 丢弃 |
| engineer 上限 | skill 内 | `MAX_ENGINEER_ROUNDS` | `2` | 超限拒绝 |
| 增益容差 | `ladder.py` | `GAIN_TOLERANCE_PCT` | `0.15` | ties 不算赢 |
| GOOD 条件 | skill 内 | `fullset.verified=true` 且严格改进 | — | 不满足不晋升 |
| 失败回退 | orchestrator | L7 BA_FAIL | target=2 | 回 Phase 2 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/experiment-execution` 6b / 6c | `/experiment-ladder` | `/result-to-claim`、`/paper-writing` |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `S2Ladder / Critic` | `reprospec/ladder.py` 已实现 `GOOD/ENGINEER/BAD` | 否，已实现 |
| `GAIN_TOLERANCE_PCT=0.15` | gate 配置 | 否 |
| `fullset.verified` | `ExperimentRun.outputs_sha` | 否 |
