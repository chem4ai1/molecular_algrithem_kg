# output-manifest · 产物清单即运行态 SSoT

> 源文件：`skills/shared-references/output-manifest.md`（202 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | 全部阶段产物 |
| **输出节点（对齐）** | `RunArtifact`(manifest 条目) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用 `RunArtifact` 承载 manifest 条目（加 phase/verdict 属性） |

## 1. 解决的问题
### 1.1 核心问题
以结构化 manifest 登记每个 phase 的实际产物，并在跨 agent / leader 边界做 same-input parity 对账。
### 1.2 为什么需要
`produce exactly the files it declared`；`A phase that writes only CHANGES_SUMMARY.md has NOT executed`；缺 manifest → BLOCKED。
### 1.3 不做的后果
用总结文档冒充执行；替换产物后无人发现。

## 2. 输入
### 2.1 输入知识节点
`manifest.run_id / phase / skill / produced / input_hashes / verdict / state`；`manifest.integrity_check`；`manifest.claim_gate`；`parity_report`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；被 `auto-pipeline`、`artifact-registry`、`result-to-claim` 消费。
### 2.3 输入产物
SKILL.md Output Shape 声明；各 phase 产物。

## 3. 输出
### 3.1 输出知识节点
`MANIFEST.json` 双路径：`.sciforge/manifest/MANIFEST.json` 与 `<workspace>/MANIFEST.json`；`phases` / `crosscheck` 两 section。
### 3.2 输出产物
`.sciforge/manifest/MANIFEST.json`：schema_version/run_id/schema/completed_at/phases/crosscheck；verdict=PASS/WARN/FAIL/BLOCKED/NOT_APPLICABLE/ERROR。
### 3.3 传递片段
无。

## 4. 判定与门
每 phase 写 manifest；cross-agent parity ≥80%；manifest 存在但产物缺失 → BLOCKED；无 manifest → INCOMPLETE；claim gate 完成率。

## 5. 上下游
auto-pipeline / 每个 skill → 本契约 → artifact-registry / result-to-claim / 最终报告。

## 6. 映射
每个阶段落 `.sciforge/manifest/MANIFEST.json` + `phases` / `crosscheck`，产物路径与 sha 必登记。
