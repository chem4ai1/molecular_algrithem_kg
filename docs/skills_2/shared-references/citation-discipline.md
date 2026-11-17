# citation-discipline · 三层反幻觉引用纪律

> 源文件：`skills/shared-references/citation-discipline.md`（58 行） · 类型：shared-reference（法条）

## 阶段与节点对齐（paper_phase 六阶段）

| 项 | 对齐结果 |
|---|---|
| **阶段标注** | 阶段3 起草 + 阶段5 自检 |
| **SciForge 26 节点** | `15` |
| **输入节点（对齐）** | `CitedPaper`(task-w) |
| **输出节点（对齐）** | `CitedPaper.context_quote`(字段回填) |
| **对齐状态** | 完全对齐 |
| **节点增补建议** | 无：三层验证状态已由 `CitedPaper.existence/metadata_ok/context_ok` 承载 |

## 1. 解决的问题
### 1.1 核心问题
用三层反幻觉验证确保每条引用真实，`BibTeX` 从已验证源生成而非手写。
### 1.2 为什么需要
`Every citation must pass 3 layers of anti-hallucination verification. No paper is ever fabricated from memory.` / `BibTeX entries are generated from verified sources, never hand-written`。
### 1.3 不做的后果
幻觉文献进 bib，投稿抽查命中。

## 2. 输入
### 2.1 输入知识节点
`citation.key / verification_status`；`layer.arXiv / CrossRef / SemanticScholar`；`bib.条目`。
### 2.2 输入 prompt 模板 / 契约
无 prompt 模板，作为法条被 `citation-audit` 消费。
### 2.3 输入产物
API：`export.arxiv.org/api/query`、`api.crossref.org/works/{doi}`、`api.semanticscholar.org/graph/v1/paper/search`。

## 3. 输出
### 3.1 输出知识节点
`citation` 状态（verified / unverified / error）；bib 统一 key 无重复；5 条 checklist；forbidden 模式。
### 3.2 输出产物
`literature/references.bib`：`author/title/journal/year/doi/verification_status=verified`；`VERIFICATION_LOG.md`。
### 3.3 传递片段
禁 `\cite{TODO}` / `\cite{forthcoming}` / `\cite{arxiv:TODO}`；禁孤儿引用、禁手写 BibTeX。

## 4. 判定与门
| 层 | 判据 |
|---|---|
| arXiv | batches of 40，核 title/authors/abstract/category |
| CrossRef | DOI 解析 + title + author |
| S2 | title/authors/year |
| 总 | 未验证条目不纳入 bib |

## 5. 上下游
citation-audit / paper-writing → 本契约 → `references.bib` 生成与引用检查。

## 6. 映射
分子生成/基准论文须经 arXiv→CrossRef→S2 验证后写入 bib。
