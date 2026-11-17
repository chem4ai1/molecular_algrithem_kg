# citation-audit · Phase 15 三层引用核验（存在 / 元数据 / 上下文）

> 源文件：`/home/zengshuxin/xKG-main/SciForge-OSS-master/skills/support/citation-audit/SKILL.md`（389 行）
> 类型：support · Phase 15（MUST） · 代码佐证：`scripts/doi_gate.py`（title overlap ≥0.8）、`scripts/citation_support.py`、`scripts/validate_verdicts.py`。

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段5 自检核验 |
| **SciForge 26 节点** | `15` |
| **输入节点（对齐）** | `CitedPaper`(task-w, context_quote)；`SectionDraft`；`Evidence` |
| **输出节点（对齐）** | `CitedPaper.existence/metadata_ok/context_ok`(字段回填)；`FailureCheck`(task-r) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：`CitedPaper` 已定义 existence/metadata_ok/context_ok/context_quote 三个可判定字段；只需在 schema 文档中补判定规则 |

## 1. 解决的问题

### 1.1 核心问题
对每条 `\cite{}` 做 existence → metadata → context 三层核验，输出强制的 `CITATION_AUDIT.json`。

### 1.2 具体场景 / 为什么需要
- 最危险的失败是「真实论文支撑错误论断」（wrong context），它比拼错作者更难发现。
- 无 bib 或无 cite 也必须写 `NOT_APPLICABLE`，不能静默跳过。
- Step 3 reviewer prompt 要求逐条输出 `YES / NO / UNCERTAIN` 与 `KEEP / FIX / REPLACE / REMOVE`。

### 1.3 不做的后果
- 幻觉文献或错上下文引用进正文，投稿时直接被审稿人命中。

## 2. 输入

### 2.1 输入知识节点

| 节点类 | 关键属性 | 来源 | 是否必须 |
|---|---|---|---|
| `Citation` | `cited_keys / bib_keys` | 正文与 bib | 必须 |
| `Use` | `key / file / line / surrounding_sentence` | 正文逐字位置 | 必须 |
| `CitationAudit` | `audited_input_hashes` | 本次运行 | 必须 |
| `ReviewLedger` | — | Phase 14 | 可选 |

### 2.2 输入 prompt 模板 / 契约文本

| 模板段 | 关键原文指令句 | 作用 |
|---|---|---|
| Step 3 reviewer prompt | `EXISTENCE: does this paper exist… Output: YES / NO / UNCERTAIN` | 存在性判定 |
| 裁决 | `Emit VERDICT: KEEP / FIX / REPLACE / REMOVE` | 逐条动作 |
| 契约 | `assurance-contract.md`、`review-tracing.md`、`citation-discipline.md` | 6 态/trace/三层纪律 |

### 2.3 输入产物文件

| 路径 | 用途 |
|---|---|
| `paper/main.tex` | 主文件 |
| `paper/sections/*.tex` | 引用上下文 |
| `literature/references.bib` | 条目 |
| `review-tracing.md` | trace 协议 |

## 3. 输出

### 3.1 输出知识节点

| 节点类 | 关键属性 |
|---|---|
| `CitationAudit` | `audit_skill / verdict / reason_code / summary / audited_input_hashes / generated_at` |
| `AuditDetail` | `total_entries / per_entry[].key / verdict / axis_failures` |
| `AuditDetail` | `uses / uncited_entries` |

### 3.2 输出产物文件

| 路径 | 关键字段 | 用途 |
|---|---|---|
| `.sciforge/audits/CITATION_AUDIT.md` | Priority Fixes / All-Clean Entries | 人读报告 |
| `.sciforge/verdicts/CITATION_AUDIT.json` | verdict / per_entry | 机读账本 |
| `.sciforge/traces/citation-audit/<date>_runNN/` | 审计轨迹 | 可追溯 |

### 3.3 向下一阶段传递的 prompt / 约束片段

| 片段 | 传递到 | 作用 |
|---|---|---|
| `KEEP / FIX / REPLACE / REMOVE` + reason_code | `/publishability-score`、final assembly | 引用处置 |
| `soft-only` → `keep_unchanged / soften_citing_sentence / drop_cite_in_body_only` | `/paper-writing` | 只软化句子，仍保留正确 cite |

## 4. 判定与门

| 门 | 脚本 / 机制 | 判据 | 阈值 | 失败去向 |
|---|---|---|---|---|
| `citation_audit` | skill 内 | 无 cite | → `NOT_APPLICABLE: no_citations` | — |
| bib 可读 | skill 内 | bib 不可读 | → BLOCKED | 阻塞 |
| 全 KEEP | skill 内 | — | → PASS | — |
| 仅 FIX | skill 内 | — | → WARN `metadata_drift` | — |
| REPLACE / REMOVE | skill 内 | — | → FAIL `wrong_context` | 回 `/paper-writing` Phase6 |
| DOI overlap | `scripts/doi_gate.py` | title token-overlap | `≥0.8` | FAIL |

## 5. 上下游接口

| 上游 | 本 skill | 下游 |
|---|---|---|
| `/result-to-claim` → `/paper-writing` | Phase 15 `/citation-audit` | `/publishability-score` → final assembly |

## 6. 与分子项目的映射

| 知识点 | 落点 | 是否需新增类 |
|---|---|---|
| `CitationAudit / Use` | `applayer` 建议新增 `Citation` 类（808 篇论文只有 48 条 `RELATED_TO`） | 是（应用层） |
| context 层逐字支撑 | `RELATED_TO.properties.context_quote` + `evidence_span` | 否（C 类） |
| `doi/year` 补缺 | `Paper.doi/year`（现 2/808） | 否（B 类） |
