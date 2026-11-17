# intake-triage · Phase 0 companion 投递物普查与阶段路由

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/intake-triage/SKILL.md`（75 行）
> 类型：support · Phase 0 companion · 无机械门（planning artifact only）。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段0 问题锚定（前置） |
| **SciForge 26 节点** | `0` companion |
| **输入节点（对齐）** | `Paper`；`ResearchQuestion` |
| **输出节点（对齐）** | `HumanIntent`(paperapp) |
| **对齐状态** | 无法完全对齐 |
| **节点增补建议** | 新增 `IntakeManifest`(census/user_requests/phase_plan)：投递物普查是运行入口事实，不属于任何写作节点；`HumanIntent` 只覆盖需求，不覆盖产物清单 |

## 1. 解决的问题

### 1.1 核心问题
对用户任意投递物（草稿、代码、数据、结果、日志、图、文献、venue 要求）做普查、信任分类、需求账本与阶段路由建议，**只规划不削门**。

### 1.2 具体场景 / 为什么需要
- 真实用户往往一次给一堆东西，需要先分类再决定哪些进哪个阶段。
- `Never read full drafts into context; sample heads/structure.` —— 防上下文爆炸。
- 继承物仍须在各边界 gate 重新派生（`inherit ≠ trust`）。

### 1.3 不做的后果
- 用户给的草稿被当作已验证事实；或把整篇草稿塞进上下文导致长程漂移。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Intake` | `question / draft_tex / draft_md / code / data / results / logs / figures / bibliography / venue_spec / style_demands / other` | 用户投递 | 必须 |
| `Census` | `path / size / note` | 普查 | 必须 |
| `UserRequest` | `id / demand / phase` | 用户 | 必须 |
| `PhaseGraph` | `nodes` | `kernel/config/phasegraph.json` | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Job | `Census — list what arrived, by class` | 分类普查 |
| 上下文纪律 | `Never read full drafts into context; sample heads/structure.` | 抽样而非全读 |
| 范围 | scope（wet-lab / clinical / proprietary GUI 拒绝；COMSOL 仅 PINN/surrogate） | 能力边界 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| workspace root / `intake/**` | 投递物 |
| `kernel/config/phasegraph.json` | 26 节点 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `IntakeManifest` | `schema_version / census / user_requests / phase_plan / suggested` |
| `Suggested` | `claim_mode / discipline / tier` |
| `PhasePlan` | `{6b, 6c, 12}` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/verdicts/INTAKE_MANIFEST.json` | `census / user_requests / phase_plan / suggested` | advisory plan |
| `intake/INTAKE_REPORT.md` | 人类可读路由 | 人读 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无 | — | — |

## 4. 判定与门

| 门 | 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| 无机械门 | — | planning artifact only | — | — |
| 信任门 | skill 内 | `inherit ≠ trust` | — | 下游 gate 不变 |
| 范围门 | skill 内 | wet-lab / clinical / proprietary GUI | — | 按 scope 拒绝 |
| COMSOL 门 | skill 内 | 仅 PINN / surrogate 目标 | — | "run COMSOL for me" 拒绝 |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| Phase 0 load-problem / 用户投递 | `/intake-triage` | Phase 6b / 6c / 10 / 11 / 12 / 13 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `IntakeManifest / UserRequest` | `paperapp` 的 `HumanIntent` 可与 user_requests 对接 | 否 |
| `inherit ≠ trust` | `verify_rebuild` 与 `DRIFT` 拒写纪律的同构 | 否 |
