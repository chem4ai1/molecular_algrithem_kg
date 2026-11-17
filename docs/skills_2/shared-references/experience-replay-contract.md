# experience-replay-contract · 跨 run 失败/成功经验回放

> 源文件：`skills/shared-references/experience-replay-contract.md`（83 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条（5→1 回环） |
| **SciForge 26 节点** | `16`→`2`/`6b` |
| **输入节点（对齐）** | `Lesson`(paperapp) |
| **输出节点（对齐）** | `Lesson`/`ExplorationFrontier` |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：paperapp 已有 Lesson 与 ExplorationFrontier 动态类 |

## 1. 解决的问题
### 1.1 核心问题
让失败或成功的运行沉淀为下一次运行的结构化先验。
### 1.2 为什么需要
`a single run that dies or fails should make the NEXT run better, not repeat the same mistake.`；失败不作贡献也不静默丢弃。
### 1.3 不做的后果
同一误分类/失败 baseline 在每次 run 中重复出现。

## 2. 输入
### 2.1 输入知识节点
`Lesson.failed_experiments / idea_rollbacks / code_errors / what_worked / avoid`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；单一串行 DAG，无并行 side-system；lessons 是 advisory priors，但 `avoid` 是 hard exclusions。
### 2.3 输入产物
`.sciforge/verdicts/KILL_ARGUMENT.json`（失败/回滚证据）。

## 3. 输出
### 3.1 输出知识节点
Phase16 `LESSONS`；`IdeaDiscovery.prior_downweight`；`ExperimentExecution.hard_exclusions`；`Policy.probe_weights`。
### 3.2 输出产物
`.sciforge/LESSONS.json`：`schema_version / run_id / 四类数组`；`output/LESSONS.json` 跨 run 镜像。
### 3.3 传递片段
无。

## 4. 判定与门
缺失类别 → empty arrays（never omit the key）；每个 FAIL/KILL 必进一个 category 且有 lesson + evidence；override 记 `override_reason`。

## 5. 上下游
`/auto-pipeline` Phase16 → 本契约 → Phase2 `/idea-discovery`、Phase6b `/experiment-execution` 及后续 runs。

## 6. 映射
记录误分类算法、失败 baseline、代码错误；后续抽取/评测自动避开已知坏配置。对应 `replay.py` 与第 5 类 lesson。
