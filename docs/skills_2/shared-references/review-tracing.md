# review-tracing · 双 reviewer 独立留痕

> 源文件：`skills/shared-references/review-tracing.md`（309 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段4 + 阶段5 |
| **SciForge 26 节点** | `14` |
| **输入节点（对齐）** | `ReviewState` |
| **输出节点（对齐）** | `ReviewLedger` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `ReviewLedger`；trace 路径与 hash 为属性 |

## 1. 解决的问题
### 1.1 核心问题
让 5 个 consumer skill 的 reviewer 调用留下不可伪造的独立 trace，防「autoReviewer 从未运行」却声称已审。
### 1.2 为什么需要
`Without a verifiable trace, "the reviewer said OK" is just an agent asserting its own work is good.`
### 1.3 不做的后果
自评冒充跨模型评审，verdict 不可审计。

## 2. 输入
### 2.1 输入知识节点
`TRACE_ID`；`skill / reviewer_model / host_agent / input_hash / output_hash`；`state.json active`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`The host agent MUST NOT write this file.`；`verify-review-trace.sh` 校验双 reviewer 文件。
### 2.3 输入产物
`auto-review-loop / result-to-claim / kill-argument / citation-audit / novelty-check` 5 个 SKILL.md。

## 3. 输出
### 3.1 输出知识节点
`reviewer_trace`；`trace_dir`；`active state.json`；`verdict.trace_path`。
### 3.2 输出产物
`.sciforge/traces/<skill>/<date>_runNN/reviewer{1,2}_{role}.json`；`state.json`；`review-trace` verdict 文件。
### 3.3 传递片段
无。

## 4. 判定与门
双 reviewer 文件存在；input/output hash 匹配；host 不得写 trace；缺任一 → FAIL/缺 review；verifier exit 1 阻断 Final Report。

## 5. 上下游
5 consumer skills → 本契约 → verifier / artifact-registry / integration-contract。

## 6. 映射
`ReviewState.model_ids[]` 必须对应真实 trace 文件，且 trace 的 input_hash 对应被测稿件。
