# confidence-uplift · TDAL 联合置信的有界提升机制

> 源文件：`skills/shared-references/confidence-uplift.md`（314 行） · 类型：shared-reference（协议）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段1 定主张 + 阶段5 自检 |
| **SciForge 26 节点** | `10`/`14` |
| **输入节点（对齐）** | `Claim`/`TDAL` |
| **输出节点（对齐）** | `Claim.weakest_dimension`/`TDAL.joint` |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 复用已建议新增的 `Claim` 与 `TDAL`，不额外新增 |

## 1. 解决的问题
### 1.1 核心问题
用三种机制主动提升 TDAL 联合落地置信度，从「评估」升级到「改进」。
### 1.2 为什么需要
v2.7 止于 "claim is WEAK"；v2.8 给出如何变 MODERATE/STRONG。`The uplift is a bounded, auditable loop — not infinite polish.`
### 1.3 不做的后果
弱主张被无限打磨或直接放弃，缺少有界提升路径。

## 2. 输入
### 2.1 输入知识节点
`TDAL.verdict ∈ WEAK/UNSUPPORTED/MODERATE/STRONG`；`weakest_dimension ∈ T/A/D/L`；`mechanism.1/2/3`；`round`；`scope_score`；`hedge_score`；`T_progressive`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；被 result-to-claim / theory-derivation / auto-review-loop 消费。
### 2.3 输入产物
`domain-adaptation-contract.md`、`result-to-claim/SKILL.md`、`theory-derivation/SKILL.md`、`universal-retrieval/SKILL.md`、`adversarial-falsification/SKILL.md`。

## 3. 输出
### 3.1 输出知识节点
mechanism_1（假设强度，紧 T）；mechanism_2（替代路径，hedge A/D）；mechanism_3（渐进验证，逐 tier 提 T）；uplift loop 3 轮固定序 1→2→3。
### 3.2 输出产物
`refine-logs/confidence-uplift-plan.json`：`trigger_verdict / initial_tdal / weakest_dimension / rounds[] / final_verdict / total_uplift / human_waived / escalated_to_human`。
### 3.3 传递片段
无。

## 4. 判定与门
| 门 | 判据 |
|---|---|
| 触发 | verdict≤WEAK 必 invoke；STRONG 跳过 |
| 每机制 | ≤3（3 轮跨机制硬顶） |
| 采纳 | `scope_score<0.5` 不采纳 |
| 替代路径 | improvement<0.2 无 |
| tier-0 | 失败即 BLOCK |
| 终局 | 3 轮后 UNSUPPORTED → BLOCK；L 不可提升 → Phase4 重跑；仅 human 可 waive |

## 5. 上下游
result-to-claim (Phase10) / auto-pipeline → 本契约 → theory-derivation(6a) / universal-retrieval(4) / auto-review-loop(14)。

## 6. 映射
主张 TDAL≤WEAK 时按 1→2→3 收紧假设 / 换数据集 / 分层证明；scope caveat 必须进论文。
