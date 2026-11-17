# artifact-registry · 跨技能产物的唯一真相源（SSoT）

> 源文件：`skills/shared-references/artifact-registry.md`（195 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 全阶段·法条 |
| **SciForge 26 节点** | 全部 |
| **输入节点（对齐）** | 各 skill 的 Output Shape 声明 |
| **输出节点（对齐）** | 产物注册表（路径/生产者/消费者/schema） |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：靠 `artifact.path/producer/consumer/schema` 属性即可，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
登记 load-bearing 产物的路径、生产者、消费者、schema 与验证器，防止幻影产物与 schema drift。
### 1.2 为什么需要
- 生产者与消费者文件名不一致会让链条静默断裂。
- 字段未文档化会让消费者漏检。
- 所有 SKILL.md 的 Output Shape / Inputs 必须反向引用本注册表。
### 1.3 不做的后果
「The skill will produce a report」这种无路径无字段的承诺被当作完成。

## 2. 输入
### 2.1 输入知识节点
| 节点 | 关键属性 |
|---|---|
| 制品 | `路径 / 生产者 / 消费者 / schema / 验证器` |
| verdict | 6 态词表 |
| hash | `audited_input_hashes` |
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板，作为法条被下游引用；依赖 `output-protocol.md`（目录权威）、`assurance-contract.md`（6 态）、`integration-contract.md`、`output-versioning.md`、`output-manifest.md`。
### 2.3 输入产物
各 SKILL.md 的 Output Shape / Inputs 声明。

## 3. 输出
### 3.1 输出知识节点
`制品.注册行`；`artifact.跨切不变量5条`；两层级路径（`.sciforge/verdicts/` 扁平机器可读）。
### 3.2 输出产物
`.sciforge/verdicts/*.json`（6 态机器判定）、`.sciforge/audits/*.md`（叙述报告）、`methods/METHOD_REGISTRY.md`、` .sciforge/MANIFEST.md`。
### 3.3 传递片段
「The skill will produce a report」无路径/字段名即拒；「Optional artifact」若 load-bearing 不可选。

## 4. 判定与门
| 门 | 判据 | 失败去向 |
|---|---|---|
| Always emit | never silent-skip（detector 负 = NOT_APPLICABLE） | — |
| 哈希 | 审计 JSON 必含 `audited_input_hashes` | 缺则 FAIL |
| Section3 | 不可变，drift = FAIL | FAIL |
| 机器 verdict | 扁平落 `.sciforge/verdicts/` | — |

## 5. 上下游
各 SKILL.md / auto-pipeline → 本注册 → method-registry / result-to-claim / invariant-check / citation-audit / paper-writing。

## 6. 映射
`molecular_algrithem_design` 每个跨阶段产物须先登记路径/生产者/消费者/验证器，未登记不得进 gate。
