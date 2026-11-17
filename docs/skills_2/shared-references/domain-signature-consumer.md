# domain-signature-consumer · 下游统一消费领域签名

> 源文件：`skills/shared-references/domain-signature-consumer.md`（236 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定 |
| **SciForge 26 节点** | 全部（消费侧） |
| **输入节点（对齐）** | `DomainProfile`(learned) |
| **输出节点（对齐）** | 各 skill 的权重/风格/门槛（属性级） |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 不新增类；靠 `origin=learned|rule` 约束 hint 不得被下游直读 |

## 1. 解决的问题
### 1.1 核心问题
规定下游 skill 如何统一消费领域签名并自动适配权重、风格与门槛。
### 1.2 为什么需要
唯一真源是 `/domain-learner` 的 signature；禁止硬编码领域逻辑；hint 仅供 learner 作 prior。
### 1.3 不做的后果
下游各读各的签名副本，行为漂移。

## 2. 输入
### 2.1 输入知识节点
`DomainSignature.evidence_type / failure_mode_profile.common_failures / evidence_norm_profile.sample_size_norm / domain_profile.primary_domain`。
### 2.2 输入 prompt 模板 / 契约
`Every skill reads refine-logs/domain-signature.json at startup and adapts its behavior accordingly.`
### 2.3 输入产物
`refine-logs/domain-signature.json`（唯一真源）。

## 3. 输出
### 3.1 输出知识节点
`IdeaDiscovery.perspective_weights`；`ResultToClaim.grounding_confidence`；`ExperimentExecution.experiment_matrix`；`NoveltyCheck.novelty_weight`。
### 3.2 输出产物
无新增文件；产出为各 skill 自适应权重 / 风格 / 门槛。
### 3.3 传递片段
启动时 Step 1–5；无签名用 default behavior；downstream MUST NOT read hint。

## 4. 判定与门
无机械门；权重 high×0.9 / medium×0.7 / low×0.4；`unknown_norm` 默认 ≥3 seeds、≥2 scales、baseline + ablation groups。

## 5. 上下游
`/domain-learner` → 本契约 → idea-discovery / adversarial-falsification / paper-writing / result-to-claim / experiment-execution / publishability-score / novelty-check。

## 6. 映射
按 simulational/experimental 调候选权重，按证据规范校准 benchmark、ablation 与 claim 门槛。
