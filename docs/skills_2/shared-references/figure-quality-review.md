# figure-quality-review · 视觉质量自审（机械审计的补充）

> 源文件：`skills/shared-references/figure-quality-review.md`（116 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段2 + 阶段3 |
| **SciForge 26 节点** | `11` |
| **输入节点（对齐）** | `FigureAsset`；`FigureAudit` |
| **输出节点（对齐）** | `FigureAudit.visual_review` |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 复用已建议的 `FigureAudit`，加 visual_review 字段 |

## 1. 解决的问题
### 1.1 核心问题
机械审计只看结构，本契约补上视觉质量评审且不引入外部视觉 API 作为硬门。
### 1.2 为什么需要
A1–A10 不能判 balance / elegance / communication；T 类宿主不得伪造视觉评审。
### 1.3 不做的后果
图结构合规但视觉不可读，或伪造「已视觉评审」。

## 2. 输入
### 2.1 输入知识节点
`figure.capability=V/T`；`figure.output.svg`；`figure.audit_verdict`；`figure.revision_log.md`；visual checklist 1–9。
### 2.2 输入 prompt 模板 / 契约
`Text-only agents degrade gracefully to the mechanical audit.`；`At most ONE call per figure version; its output is advisory, never a gate verdict, never blocks a run; unreachable ⇒ deferred-external.`
### 2.3 输入产物
`figure_audit.py` A1–A10 机械审计结果。

## 3. 输出
### 3.1 输出知识节点
`revision_log.md[capability, visual-review, checklist, accepted-risk]`；`output.svg`；`advisor.suggestions`。
### 3.2 输出产物
`figures/<name>/revision_log.md`、`output.svg`。
### 3.3 传递片段
V 类每次非 FAIL 渲染后打开 SVG 逐项诚实回答；no/concern → 改 SOURCE → re-render → re-inspect。

## 4. 判定与门
V：Tier1 MANDATORY + Tier2 optional；T：`visual-review: skipped-text-only`；Deliver only when checklist fully satisfied AND mechanical audit not FAIL；3 passes 无进展 → re-layout 或 accepted-risk。

## 5. 上下游
`figure_audit.py` / unified-plotting → 本契约 → 宿主视觉自审、Tier2 advisor、图稿交付。

## 6. 映射
分子架构/构效图先过 A1–A10，再查 message / hierarchy / wiring / typography / palette。
