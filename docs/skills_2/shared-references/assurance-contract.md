# assurance-contract · 审计严格度轴与 6 态 verdict

> 源文件：`skills/shared-references/assurance-contract.md`（248 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `7`/`8`/`10`/`15`/`15.5` |
| **输入节点（对齐）** | `GateVerdict`(paperapp) |
| **输出节点（对齐）** | `GateVerdict.state`(6 态) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 为 `GateVerdict` 加 `assurance=draft|submission` 属性，不新增类 |

## 1. 解决的问题
### 1.1 核心问题
定义 `assurance`（draft / submission）轴，决定审计 verdict 是建议还是 load-bearing gate。
### 1.2 为什么需要
历史上 `effort=beast` 与审计严格度混淆，导致草稿质量论文跳过全部三个 submission 门。
- `All mandatory audits must emit a verdict (one of the 6 below). Silent skip is forbidden.`
### 1.3 不做的后果
高 effort 低 assurance 的论文被误判可投稿。

## 2. 输入
### 2.1 输入知识节点
`assurance.级别`；`audit.verdict(6态)`；`audit.audited_input_hashes`；`audit.trace_path`；`verdict.STALE`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板；依赖 `integration-contract.md` §2、`effort-contract.md`、`review-tracing.md`、`reviewer-independence.md`。
### 2.3 输入产物
各审计 JSON + `verify_paper_audits.sh`。

## 3. 输出
### 3.1 输出知识节点
`assurance` 映射（lite/balanced→draft，max/beast→submission）；审计 JSON 必填字段；6 态语义。
### 3.2 输出产物
`.sciforge/verdicts/*.json`：`audit_skill / verdict / reason_code / audited_input_hashes / trace_path / thread_id / reviewer_model / generated_at`；Final Report 的 submission-ready yes/no。
### 3.3 传递片段
子技能「Always emit, never block」——只发 verdict，由父技能依 assurance 决定是否阻断。

## 4. 判定与门
| 状态 | 处理 |
|---|---|
| FAIL / BLOCKED / ERROR / STALE | 阻断；verifier exit 1 阻 Final Report |
| FIGURES_VECTOR | 见 png 即 FAIL |
| FIGURES_REPRODUCIBLE | 缺 `gen_*.py` → WARN |
| FIGURES_DATA_CONSISTENCY | 缺数据源 → FAIL / WARN |

## 5. 上下游
paper-writing / result-to-claim / citation-audit / logic-verification → 本契约 → 定稿门。

## 6. 映射
提交前设 `assurance=submission`；本项目 `sciforge/contracts.py::VERDICT_STATES` 已实现 6 态。
