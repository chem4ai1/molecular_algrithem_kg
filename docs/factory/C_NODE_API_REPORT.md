# C 节点接口化改造：调研、优化与实测案例

> 基于 Decision Log / Agent Ledger 范式：每个决策绑定 intent + provenance + verdict，append-only 可回放。

## 1. 调研结论

| 来源 | 做法 | 对本项目的启发 |
|---|---|---|
| Agent Patterns Catalog: Decision Log | 持久化推理轨迹与动作，支持回放/时间旅行 | 决策要 append-only 且带上下文 |
| LedgerMind / Tenet AI: Decision Ledger | 每个决策记录 intent/context/reasoning/outcome，绑定来源 | C 节点必须带 source/via/verdict |
| ThreatClaw: Agent Ledger | 决策与 provenance、policy rationale 密码学绑定 | provenance 不能是装饰，要进节点属性与边 |

**结论**：原 `WritingContext` 的「run_id id + layer/task/miner + 建边」三件事方向正确，
但缺两样：**类型化决策接口** 和 **自动 provenance 绑定**。

## 2. 改造前后对比

| | V1（脚本硬写） | V2（WritingContext 接口） |
|---|---|---|
| C 节点创建 | `g.node("claim:...", "Claim", ...)` | `ctx.formalize_claim(...)` |
| B 类查询 | 脚本里手写 `query_*()` 调用 | **内置在方法里**，自动写 source/via |
| provenance | 手工塞几个属性 | 每个决策自动 `_log(intent, source, via, verdict)` |
| 门控 | 没有 | `verdict=BLOCKED` 真实触发 |
| 回放 | 只有阶段日志 | `decisions[]` append-only ledger |

## 3. 新增的 6 个类型化接口

| 方法 | 产出 | 内置 B 类查询 | 门控 |
|---|---|---|---|
| `formulate_gap()` | GapTriple | query_frontier_baseline | — |
| `propose_idea()` | IdeaCandidate | — | 无机制/无证伪条件 → REJECTED |
| `formalize_claim()` | Claim | query_evaluation_norm | 无 refutation_condition → BLOCKED |
| `grade_claim()` | grade + AUDITED_BY 边 | query_failure_checks | — |
| `design_narrative()` | SectionPlan + FigurePlan | query_venue_profile | venue 缺失 → WARN |
| `deliver()` | ReproductionPackage | — | verification≠pass → BLOCKED |

## 4. 实测 Decision Log（52 篇图谱上运行）

| 决策 | verdict | provenance source |
|---|---|---|
| GapTriple | CREATED | lineage:factory:other |
| IdeaCandidate | LOCKED | gaptriple:factory_v2:x4f941a68 |
| Claim | LOCKED | norm:factory:experimental |
| Claim | BLOCKED:no_refutation_condition | — |
| ClaimGrading | SUPPORTED | failurelib:factory |
| Narrative | WARN:no_venue | venue:factory:unknown |
| Delivery | BLOCKED:verification | claim:factory_v2:x6fd098ae |

### 关键验证点

1. **无推翻条件的 Claim 被真实 BLOCKED**：`Claim / BLOCKED:no_refutation_condition`
2. **verification=pending 的交付被真实 BLOCKED**：`Delivery / BLOCKED:verification`
3. **venue 缺失是 WARN 不是伪造**：`Narrative / WARN:no_venue`
4. **B 类图被真正消费**：GapTriple 的 frontier 来自 `lineage:factory:other`，
   Claim 的 fidelity 来自 `norm:factory:experimental`，grade 来自 `failurelib:factory`

## 5. 修复的 bug

- `_slug()` 对纯中文返回空串 → id 变成 `claim:factory_v2:`；加 SHA256 短 hash 兜底
- 图规模：374 节点 / 433 断言（比 V1 多 4 条决策 provenance 边）

## 6. 复现

```bash
PYTHONPATH=src python3 stages/2_knowledge/build_factory_graph_v2.py
cat storage/sciforge/factory_decision_trace_v2.json
```
