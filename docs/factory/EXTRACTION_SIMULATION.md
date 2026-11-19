# 抽取全过程模拟（MECo 重放）

> 用 MECo (`2510.14455`) 一篇论文，不实际调 LLM，而是**回放已有报告和中间产物**，
> 把从 PDF 到最终产物的每一步输入/动作/输出/门控打出来。
> 追踪文件：`storage/simulation/simulation_trace.json`

## 全景（10 步）

| # | 阶段 | 输入 | 动作 | 输出 | 门控 |
|---|---|---|---|---|---|
| 00 | PDF→md | `2510.14455_MECo.pdf` | `parse_pdf()` pymupdf + 章节切分 | `2510.14455.md`（79,264 字符 / 38 章节） | PASS |
| 01 | E1_paper | YAML(30 字段, 7 条规则) + md | `render → LLM → validate → rules` | 30 字段（含 `research_question`/`claims`/`gaps`） | PASS |
| 02 | E2_algorithm | YAML(13 字段) + md | 同上（无规则） | `algorithms[]`（含 `arch_modules` 3 个） | PASS |
| 03 | E3_benchmark | YAML(10 字段) + md | 同上 | `benchmarks[]` | PASS |
| 04 | 落图 | 三份报告 | `apply_one()`：Paper 属性 + 6 类节点 + 9 关系 | 语义层（6 类未变，Paper 36 字段） | PASS |
| 05 | B 类聚合 | 52 篇语义图 | Leiden + 规则聚合（离线一次建） | MethodLineage 6 / Norm 4 / FailureLib 1 | PASS |
| 06 | 阶段路由 | 6 维画像 | `route_phase('P1', profile)` | modules + gate=`has_why_not_other` | PASS |
| 07 | **就绪度审计** | Paper + 关联 Algorithm | readiness.yaml 矩阵 | **5/5 阶段 READY** | PASS |
| 08 | C 类决策链 | ProblemAnchor… | WritingContext 接口 + ledger | 带 source/via/verdict 的决策节点 | PASS |
| 09 | 产物生成 | result_tables + SectionPlan | table→LaTeX / 骨架 / 绘图 | 18 张 .tex + 骨架 + PDF | PASS |

## 关键点逐条说明

### 01–03 · 抽取三步的实际机制

```
YAML 声明 30/13/10 个字段
   ↓ render() 读 YAML 生成 prompt（词表按阶段注入）
   ↓ LLM 输出 JSON（本地 vLLM 或 Ernie）
   ↓ parse_llm_json 容错解析
   ↓ validate() 归一化 ← 第一道容易漏字段的关
   ↓ apply_rules() 用 YAML rules: 补规则字段
     E1 实测 rule_filled = [data_sources, dedup_rule, result_tables, formal_def]
   ↓ 报告落盘
```

**规则与 LLM 的分工**：
- LLM 抽语义：`research_question`/`method_limits`/`old_forms`/`arch_modules`/`key_challenge`
- 规则抽结构：`data_sources`/`dedup_rule`/`formal_def`/`result_tables`/`hyperparams`

### 04 · 落图不改结构

`stable_key()` 不含新属性，语义层仍是 **6 类 / 9 关系**——只是 Paper 从 28 字段扩到 36。

### 05 · B 类是离线聚合，不是每次现算

```
52 篇 → 特征相似图 → Leiden → 社区报告（title/summary/findings/rating）
      → 物化节点 + DERIVED_FROM_PAPERS/LINEAGE_OF 边
```

### 06 · 按画像路由，不是一套模板套所有论文

```
edit_sequence → modules=[edit_generator, edit_executor], gate=has_why_not_other
rule_symbolic → modules=[compiler, inference, validator], gate=soundness
```

### 07 · 就绪度审计（新增 skill）

MECo 实测：
```
P0=READY  P1=READY  P2=READY  P6=READY  P7=READY
```

**关键修正**：审计要聚合关联 Algorithm 的字段（`arch_modules` 不在 Paper 上）。

### 08 · 决策链和门控

`WritingContext` 的 6 个类型化接口内置 B 类查询；无 `refutation_condition` 的 Claim 被真实 BLOCKED。

### 09 · 产物

18 张 LaTeX 表（自动加粗最优、↓ 取 min、同名行不误加粗）+ 章节骨架 + 可跑绘图脚本。

## 复现

```bash
PYTHONPATH=src python3 stages/0_pipeline/simulate_extraction.py
cat storage/simulation/simulation_trace.json
```
