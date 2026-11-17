# paper-compile · elsarticle 编译与零警告/页数/图嵌入硬检查

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/paper-compile/SKILL.md`（294 行）
> 类型：support · Phase 13（MUST） · 代码佐证：`scripts/check_figure_embedding.py --min-figures <budget> --require-renderer`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草（编译） |
| **SciForge 26 节点** | `13` |
| **输入节点（对齐）** | `SectionDraft`；`FigureAsset`；`CitedPaper` |
| **输出节点（对齐）** | `RunArtifact`(task-r)；`FailureCheck`(task-r) |
| **对齐状态** | 部分对齐 |
| **节点增补建议** | 新增 `CompileReport`(errors/warnings/pages/within_page_limit)：编译结果需独立查询，不能只塞进 `FailureCheck.note` |

## 1. 解决的问题

### 1.1 核心问题
编译 `elsarticle` 为 `main.pdf`，消费 `LEAKAGE_SCRUB` 门并执行零警告、图表、页数、嵌入的硬检查。

### 1.2 具体场景 / 为什么需要
- `This check is a hard wall — there is no WARN downgrade` —— 清洗门没有降级通道。
- 页数上限：`short ≤6 / standard ≤12 / long ≤16`。
- 图必须矢量、带 renderer 证据、达到最小数量。

### 1.3 不做的后果
- clean compile 掩盖流水线泄漏、超页或丢图等 desk-reject 缺陷。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Paper` | `main.tex` | `/paper-writing` | 必须 |
| `Bibliography` | `references.bib` | 检索 | 可选（应存在） |
| `Section` | sections | `/paper-writing` | 可选（应存在） |
| `Figure` | figures | `/unified-plotting` | 可选（应存在） |
| `LeakageScrub` | `status=PASS` | `/paper-writing` | 必须 |
| `Length` | page limit | 配置 | 必须 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| 无模板 | 消费 `output-protocol.md` | 产物协议 |
| 硬墙指令 | `This check is a hard wall — there is no WARN downgrade` | 不允许降级 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `paper/{main.tex, references.bib, sections/*.tex, figures/, LEAKAGE_SCRUB.json, math_commands.tex}` | 主文件与门 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `CompileReport` | `Status / Pages / WithinPageLimit` |
| `LeakageScrubVerified` | `compile_allowed / re_scan_hits` |
| `PaperPlan` | `page_limit_exceeded` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `paper/main.pdf` | — | 论文 |
| `paper/compile.log` | — | 日志 |
| `paper/LEAKAGE_SCRUB_VERIFIED.json` | — | 清洗授权 |
| `paper/COMPILE_REPORT.json` | `Status / Errorsfixed / Warningsremaining` | 机读报告 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| 无 | — | — |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| scrub 门 | skill 内 | 缺 `LEAKAGE_SCRUB.json` | → `BLOCKED: leakage_scrub_gate_not_run` | 阻塞 |
| scrub 状态 | skill 内 | `status != PASS` | → `BLOCKED: pipeline_leakage_not_scrubbed` | 阻塞 |
| 嵌入门 | `check_figure_embedding.py --min-figures <budget> --require-renderer` | exit 2 / 图<2 | `2` | `figures_not_embedded` |
| 页数门 | skill 内 | short≤6 / standard≤12 / long≤16 | — | `page_limit_exceeded` → L12 回 `/paper-writing` |
| 警告门 | skill 内 | 3 次仍有警告 | `3` | `BLOCKED: unresolved_warning_<type>` |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/paper-writing` Step 3.5 | Phase 13 `/paper-compile` | submission / `main.pdf`；超页回 `/paper-writing` 削减 |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `CompileReport` | `paperapp` gate 产物 | 否 |
| `LEAKAGE_SCRUB.status=PASS` | `DK-P4-07` 数值清洗门 | 否 |
| 图嵌入校验 | `DK-P4-10` `Figure.first_ref_position` | 否 |
