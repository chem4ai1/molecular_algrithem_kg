---
name: extraction-readiness-audit
description: "Audit whether extracted facts are SUFFICIENT TO REASON WITH at each pipeline phase (P0–P11). Answers a question that coverage metrics cannot: 'given this paper's extracted fields, can I actually formalize P0, draw the P1 architecture, specify P2 data construction, produce a P6 result table?' Produces a per-paper READY/PARTIAL/BLOCKED verdict plus the exact二次抽取 to run. Gate: a BLOCKED paper must not enter that phase's evidence pool."
type: support-skill
role: extraction-readiness-auditor
version: 1.0.0
---

# Extraction Readiness Audit

> **为什么需要它**：抽取覆盖率（比如「paradigm 95%」）只说明「抽到了什么」，
> 不说明「够不够推理」。P0 没有 `formal_def` 和 `method_limits` 就写不出问题形式化；
> P1 没有 `arch_modules` 就画不出架构图；P6 没有 `result_tables` 就给不出主实验表。
> 这个 skill 把「够不够」变成可判定的 READY / PARTIAL / BLOCKED。

## Quick Reference

- **输入**：语义层图（Paper + Algorithm + Benchmark 属性）
- **需求来源**：`data/extract_target/readiness.yaml`（声明式，改需求不改代码）
- **输出**：`storage/sciforge/readiness_report.json` + 控制台报告
- **门控**：BLOCKED 的论文不得进入该阶段的证据池；PARTIAL 降级使用（标注置信度）
- **联动**：BLOCKED 自动产出 `pending_refine` 清单，逐篇触发对应 refine 配置

## Job

1. **按阶段读需求**（`readiness.yaml` 的 `critical` / `any_of` / `optional`）
2. **逐篇判定**
   - `critical` 全有 且 `any_of` 至少一组满足 → **READY**
   - 缺一部分 → **PARTIAL**（可用但要标注）
   - `critical` 缺 → **BLOCKED**（不可进入该阶段）
3. **汇总缺项**：按需求项统计缺多少篇，找出系统性缺口
4. **产出补抽清单**：BLOCKED/PARTIAL 的论文按 `补抽:` 字段归到对应 refine

## 需求矩阵（v1）

| 阶段 | critical | any_of | 缺了会怎样 |
|---|---|---|---|
| P0 问题形式化 | `method_limits` | `formal_def` 或 `old_forms` | 写不出「旧法怎么做的、哪里不行」 |
| P1 技术路线 | `arch_modules` + `key_challenge` | `why_not_other` 或 `arch_modules` | 画不出架构图、说不出为何不用它法 |
| P2 数据构造 | `data_sources` | `dedup_rule` 或 `split_spec` | 说不清数据从哪来、怎么防泄漏 |
| P6 主实验 | `result_tables` | — | 给不出方法×指标矩阵 |
| P7 消融 | `arch_modules` | `hyperparams` 或 `ablation_hyperparams` | 不知道消融什么 |

## 与二次抽取的关系

审计本身**不抽取**，只判定 + 分派：

```
审计 → BLOCKED/PARTIAL
     → pending_refine（R7_formulation / R8_architecture / R9_dataset / R10_result_table）
     → 逐篇跑 refine（回原文对应段落补抽）
     → 重新审计，直到 READY 或确认原文确实没有
```

**关键**：有些字段原文确实没有（如 LLM agent 类论文没有 `formal_def`）。
这时审计应输出 `NA`（原文无此项），而不是无限重试。

## 判定示例

```
MECo (2510.14455)
  P0: READY   （formal_def='Mo=F(Mi,T)', method_limits=3 条）
  P1: READY   （arch_modules=[Reasoning LLM, Code LLM], key_challenge=意图对齐）
  P2: READY   （data_sources=[ZINC,ChEMBL], dedup_rule='Tanimoto>=0.6'）
  P6: READY   （result_tables=Table1/3）

AgentDrug (2410.13147)
  P0: PARTIAL （无 formal_def，但 method_limits 有 → 可写问题陈述但无公式）
  P1: READY   （workflow 模块有）
  P2: NA      （zero-shot 不造数据）
  P6: READY
```

## 使用

```bash
python3 scripts/audit_readiness.py
# 输出：各阶段 READY/PARTIAL/BLOCKED 计数 + 缺项统计 + pending_refine
```

## 防止误用

- **不要把 PARTIAL 当 READY**：PARTIAL 进论文时必须标注「该阶段证据不完整」
- **不要无限补抽**：同一字段补抽两次仍空 → 判 NA，写进「原文确实没有」清单
- **不要让审计代替覆盖度统计**：覆盖度回答「抽到什么」，审计回答「够不够用」
