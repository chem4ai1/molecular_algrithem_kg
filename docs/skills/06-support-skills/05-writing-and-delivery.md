# 指导 · 写作、编译与引用终审（3 个 support skill + 2 个模板）

> **覆盖**：`paper-writing`(396) · `paper-compile`(294) · `citation-audit`(388)；`paper-writing/templates/default/main.tex`(90) 与 `math_commands.tex`(47)
> **DAG 位置**：Phase 12 → 13 → 15；这是「科学产物变成可投稿 PDF」的最后一段。

---

## 1. `paper-writing` — 单一 elsarticle 模板 + 五模式（Phase 12，MUST）

| 项 | 内容 |
|---|---|
| 输入 | `derivation_output.md` + `CLAIMS_FROM_RESULTS.md` + `figures/` + `FRONTIER_GAP.md` / `FRONTIER_MAP.json` + `LOGIC_VERIFICATION.md` / `LEAKAGE_AUDIT.md` / `FIGURE_INDEX.md` + `LEAKAGE_SCRUB.json` |
| 输出 | `paper/main.tex` + `paper/sections/*.tex` + `paper/PAPER_PLAN.md` |
| 关键 | **统一 `elsarticle` 模板（无 venue 分叉）**；v2.1 **五模式选择器**：`theory / experiment / computational / survey / hybrid`，由 `verification_type` 驱动（见 `paper-modes.md`） |
| 模板 | `templates/default/main.tex`(90 行骨架) + `math_commands.tex`(47 行数学宏) |

### 1.1 必须遵守的输入纪律

| 来源 | 用在哪 |
|---|---|
| `FRONTIER_GAP.md` / `FRONTIER_MAP.json` | **Introduction 前三段**：frontier baseline / delta claim / why-not-before |
| `differentiation.md` + `collision_matrix` | Intro 的 "Unlike X, we ..." 差异化句 |
| `CLAIMS_FROM_RESULTS.md` | 逐 claim 强度与 Claims-Evidence Matrix；**正文不得超出它** |
| `RESULT.json` → `input_data.json` | 所有数字与表格；禁止凭记忆填数 |
| `FIGURE_INDEX.md` + `latex_include.tex` | Figure Budget（Methods 架构图 MANDATORY、body ≥7、类型 ≥3）、正文嵌 PDF only |
| `domain-signature.json` | `writing_profile` 的 style / citation_format / section_structure |

### 1.2 写作期的三道硬约束

1. **Pipeline-leakage scrub**：`scripts/leakage_scan.py` 的 A–J 类（含 Class J AIGC 痕迹词、Class L 内部术语替换表），写 `LEAKAGE_SCRUB.json`；Phase 13 边界据此拒绝推进。
2. **voice**：`writing-principles.md` §0.5 anti-AIGC、§0.6 SCI stance-first；`paper-voice-contract.md` 的 caption 纪律（渲染后才写、定义误差棒、不含 "Figure"、只讲科学不讲管线）、negative vocabulary delete-on-sight。
3. **Phase 6 verifier**：`assurance: submission` 时检查 `REVIEW_STATE.json`、`CITATION_AUDIT.json`、`PROOF_AUDIT.json` 等存在；`verify_paper_audits.sh` 非零退出阻断 Final Report。

> **双写**：`output-versioning.md` 要求每个交付物同时写时间戳副本与固定名副本；MANIFEST append-only 追加一行。

---

## 2. `paper-compile` — 零 warning 零 error（Phase 13，MUST）

| 项 | 内容 |
|---|---|
| 输入 | `paper/main.tex` + `paper/sections/*.tex` + `literature/references.bib` + figures |
| 输出 | `paper/main.pdf` + `compile.log` + `COMPILE_REPORT.json` |
| 关键 | **submission 级零 warning 零 error**；**anti-deadloop ladder：每条 warning 3 次尝试 → BLOCKED**；`PAPER_COMPILE.schema.json` 4 required（`verdict, zero_warnings, zero_errors, generated_at`） |
| OSS 差异 | **没有按 venue 的页数表**：单一目标 8–15 页主文（flexible），无 `TARGET_VENUE` 开关 |

### 2.1 编译前会先查

- `scripts/check_figure_embedding.py`：① 正文 `figure` 环境数 ≥ `--min-figures`；② 磁盘上每张 figure PDF 都被 `\includegraphics` / `\input` 引用；③ `--require-renderer` 时每张图目录必须带 `figure_audit.json` + `latex_include.tex`（**防止绕过 `render_figure.py` 手写 PDF**）。FAIL → exit 2，`paper-compile` 据此**拒编译**。
- `scripts/figure_style_gate.py`：figures-follow-text（首个 `\ref/\Cref` 在 figure 环境之前且同节或更早）、vector-only（禁 `.png/.jpg/.jpeg`）、type diversity ≥3。
- `LEAKAGE_SCRUB.json` / `LEAKAGE_SCRUB_VERIFIED.json`：正文痕迹已清理。

### 2.2 失败处理

| 情况 | 动作 |
|---|---|
| 单条 warning | 每条最多 3 次修复尝试（换方法/扩范围/换工具），仍失败 → `BLOCKED + reason_code` 交人 |
| 页数溢出 | L12：回 Phase 12 删减重编译；无可删 → 降一个长度档重排 |
| `check_figure_embedding` FAIL | 回到 Phase 11/12 修图或补引用，**不要**在编译阶段硬塞 |

> 旧版「warning 可降级豁免」已废除，`zero-warnings` 是 non-negotiable。

---

## 3. `citation-audit` — 终审 3 层反幻觉（Phase 15，MUST）

| 项 | 内容 |
|---|---|
| 输入 | `paper/main.tex` + `literature/references.bib` |
| 输出 | `CITATION_AUDIT.md` + `CITATION_AUDIT.json` |
| 核心 | **每个 `\cite{key}` 必须解析到一个已验证的 .bib 条目**；3 层独立验证 = existence（arXiv）→ metadata（CrossRef）→ context（Semantic Scholar） |
| schema | `CITATION_AUDIT.schema.json` **11 个 required**（本套 schema 里最严），含 `audit_skill=citation-audit`、6 态 verdict、`reason_code`、`audited_input_hashes`、`trace_path`、`thread_id`、`generated_at` |
| 门 | 全部引用过 3 层；FAIL → **删掉伪造引用 + 回 Phase 4 重新检索** |

### 3.1 它比 3 层协议更严的两道补充

| 脚本 | 补什么 |
|---|---|
| `scripts/doi_gate.py` | strict-DOI：每个 `@entry` 必须有 DOI 且 CrossRef 能解析；**解析出的 BibTeX 标题与 bib 标题 token-overlap ≥0.8**（防「DOI 有效但指向另一篇」这种经典引用幻觉）；唯一例外 `no_doi_classical={yes}`；支持 `--offline` |
| `scripts/citation_support.py` | **句子级支持**：含数字/比较级的句子必须同句有 `\cite{}`（否则 `unsupported_quantitative_claim`）；每个 bib key 至少被引用一次（否则 `orphan_reference`）；`SCIFORGE_LLM_SUPPORT=1` 时才做模型抽查 `claim_not_entailed → WEAK_CITE` |

> 三层验证只证明「文献存在且元数据吻合」，**不证明正文里的引用句真的是该文献说的** —— 这就是第 4 层 `citation_support` 存在的原因。四层叠加才是完整引用链。

### 3.2 与其他阶段的关系

- 上游 `universal-retrieval`（Phase 4）负责**找得到、是真的**；本 skill 负责**终稿里用得对**；
- `reviewer-independence` persona 的 File-Read Order 也会读 `CITATION_AUDIT.md`；
- `PAPER_CLAIM_AUDIT` 是另一个 audit-family verdict（5 required），管「正文 claim 与证据矩阵一致性」，别与 `CITATION_AUDIT` 混。

---

## 4. 两个 LaTeX 模板

| 文件 | 行数 | 用途 |
|---|---:|---|
| `templates/default/main.tex` | 90 | `elsarticle` 单一骨架：导言区 / 标题作者 / abstract / `\input` 各 section / bibliography；所有模式共用，**不按 venue 分叉** |
| `templates/default/math_commands.tex` | 47 | 常用数学宏（符号、算子、定理环境等），供 `main.tex` 引入 |

**使用纪律**：改模板要同时满足 `venue-profiles.md` 的统一骨架与 `paper-modes.md` 的章节集；**不要为某个会议复制一份模板改页数** —— venue 适配是 deferred/optional 的投稿时动作。

---

## 5. 这段链的 SOP

```
Phase 11 图（PDF+SVG + latex_include.tex + FIGURE_AUDITS.json）
    ↓ ∥
Phase 12 paper-writing
   ├─ 五模式选章节/页数
   ├─ Intro ← FRONTIER_GAP.md
   ├─ 数字 ← RESULT.json / input_data.json
   ├─ claim ← CLAIMS_FROM_RESULTS.md
   └─ leakage_scan.py → LEAKAGE_SCRUB.json
    ↓
Phase 13 paper-compile
   ├─ check_figure_embedding.py（拒编译权）
   ├─ figure_style_gate.py（follow-text / vector-only / diversity）
   └─ 零 warning 零 error → main.pdf
    ↓
Phase 14 评审（auto-review-loop / kill-argument）→ 可能回 12 修改
    ↓
Phase 15 citation-audit
   ├─ 3 层 + doi_gate + citation_support
   └─ FAIL → 删伪造引用 + 回 Phase 4
```

---

## 6. 检查清单

**Phase 12**
- [ ] mode 已选，章节集/页数/`PAPER_PLAN.md` 一致
- [ ] Intro 三元组来自 `FRONTIER_GAP.md`，差异化句有 `collision_matrix` 支撑
- [ ] 所有数字可追溯到 `RESULT.json`；claim 强度 ≤ `CLAIMS_FROM_RESULTS.md`
- [ ] caption 渲染后写、定义误差棒、不含 "Figure"
- [ ] `leakage_scan.py` Class A–J 通过；AIGC 痕迹词已清
- [ ] Figure Budget：Methods 架构图、body ≥7、类型 ≥3；正文只嵌 PDF

**Phase 13**
- [ ] `check_figure_embedding.py --require-renderer` 通过（每张图有 `figure_audit.json`）
- [ ] `figure_style_gate.py` 三查通过
- [ ] `main.pdf` 生成，零 error 零 warning；`COMPILE_REPORT.json` 如实填 `zero_warnings/zero_errors`
- [ ] 页数在 8–15 主文目标内，溢出走 L12

**Phase 15**
- [ ] 每个 `\cite{key}` 解析到 verified .bib 条目
- [ ] `doi_gate` 标题 token-overlap ≥0.8；无 `\cite{TODO}` / `forthcoming` / 手写 BibTeX
- [ ] `citation_support` 无 `unsupported_quantitative_claim` / `orphan_reference`
- [ ] `CITATION_AUDIT.json` 11 个 required 齐全，含 `audited_input_hashes`
- [ ] `submission` 模式下 `verify_paper_audits.sh` 非零即阻断

---

## 7. 与框架的对应

[APPLICATION_ONTOLOGY_FRAMEWORK.md](../APPLICATION_ONTOLOGY_FRAMEWORK.md) 中 `PaperSection / Caption / FigureBudget / CitationArtifact / Verdict` 与 §3 全表 Phase 12–15 行由本组落地；§11 反模式「AI 直出数据图 / 正文嵌栅格 / caption 先于渲染 / 绕过 render_figure.py / 引用标题当逐字引文」都对应这里的门。
GGR 复现层的 `ClaimAnchor` 三哈希与 `doi_gate` 的标题 token-overlap 是同一条「防张冠李戴」原则在不同层的实现。
