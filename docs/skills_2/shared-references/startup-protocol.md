# startup-protocol · 每个 skill 启动必读与全局契约加载顺序

> 源文件：`skills/shared-references/startup-protocol.md`（236 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | `DomainProfile` |
| **输出节点（对齐）** | 启动日志（属性级） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：startup-log 是运行日志，不是知识节点 |

## 1. 解决的问题
### 1.1 核心问题
规定每个 skill 启动时的加载顺序与必读文件，防止长程漂移与跳过领域适配。
### 1.2 为什么需要
`Every skill reads refine-logs/domain-signature.json at startup`；`no file exists → use defaults and print warning`；只有本 skill 的 SKILL.md 被读，其他靠路径引用。
### 1.3 不做的后果
下游不读签名、不改权重，领域适配失效。

## 2. 输入
### 2.1 输入知识节点
`skill.name / SKILL.md`；`domain-signature.json`；`discipline-context.md`；`output-language.md`；`startup-log.md`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；`Load only the current skill's SKILL.md — do not inline other skills`；`Inject loaded signature summary into analysis prompt`。
### 2.3 输入产物
`domain-adaptation-guide.md`、`domain-signature-consumer.md`、`integration-contract.md`。

## 3. 输出
### 3.1 输出知识节点
`startup-log` 条目；`execution-log` 每 skill 记录；signature summary injection。
### 3.2 输出产物
`refine-logs/startup-log.md`、`refine-logs/execution-log.md`。
### 3.3 传递片段
无。

## 4. 判定与门
缺签名 → 默认 + WARN；每 skill 必写 execution-log；不得内联其他 skill 全文。

## 5. 上下游
orchestrator → 本契约 → 每个 skill 的启动流程与 startup-log。

## 6. 映射
每次 phase 启动先读 `DomainProfile` 与当前 decision_fp，再写 execution-log。
