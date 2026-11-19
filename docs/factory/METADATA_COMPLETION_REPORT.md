# 元数据补全与「要不要补 LLM」分析

## 1. 补了什么

| 项 | 方法 | 结果 |
|---|---|---|
| D2 evidence_type（5 篇缺） | 强规则（survey→interpretive）+ 同流派众数 | 5/5 补齐，0 剩余 |
| D3 paradigm（5 篇缺） | 同上 | 5/5 补齐，0 剩余 |
| D5 venue | PDF 页眉规则 + LLM 分级补 | 23→26/52（+3 篇 LLM） |
| D6 artifact_protocol | 代码仓库/基准/理论关键词规则 | 52/52，100% |

### D2/D3 分级补全策略

```
① 强规则：survey/review → interpretive；theorem+无实验节 → derivational/formal
② 同流派众数：其余按 method_family 的众数填
③ 标记来源：evidence_type_source = strong_rule | family_mode | llm_corrected
```

关键验证：`2508.14111`（Agentic Science Survey）用强规则正确识别为 interpretive，
而众数（llm_agent 流派→experimental）会错——**强规则必须先于众数**。

## 2. 最终 6 维覆盖率

```
method_family      52/52 = 100%
evidence_type      52/52 = 100%
paradigm           52/52 = 100%
problem_category   51/52 = 98%
venue              26/52 = 50%   ← 唯一缺口
artifact_protocol  52/52 = 100%
```

**阶段④路由成功率：52/52**（补前 SynCraft 路由为空，补后 skills=3、claim_form=system_effectiveness）

## 3. 对照实验：规则 vs LLM

| 论文 | 规则 venue/ev | LLM venue/ev | 判断 |
|---|---|---|---|
| SynCraft (2512.20333) | nature_family / experimental | Nature MI / experimental (conf 0.4) | **规则更准**（PDF页眉明确） |
| 1911.00598 SHACL | None / derivational | Journal of Web Semantics / derivational (conf 0.75) | **LLM 更准**（补了 venue） |
| 2002.07007 | None / simulational | ACS Central Science / simulational (conf 0.85) | **LLM 更准** |
| 2101.07136 Trav-SHACL | None / experimental | unknown / derivational (conf 0.4) | LLM 的 ev 更准（形式化验证） |

**结论**：
- venue：LLM 能补规则漏掉的（规则只看 md 前 60 行，LLM 读摘要能识别期刊）→ **值得补**
- evidence_type：LLM 与规则有分歧时 LLM 有时更准，但置信度差异大 → **只在高置信（≥0.7）时改**

## 4. 要不要继续补 LLM？——成本收益分析

### venue 缺口拆解（26 篇 None）

```
11 篇 = arxiv_preprint（明确是预印本，不是真缺口）
15 篇 = 未知（值得补）
```

### 本轮 LLM 补全结果

```
venue_filled: 3    ← 只补了 3/15，其余 LLM 返回空或 conf<0.5
llm_fail: 0        ← 没有报错，是返回质量低
kept_rule: 21      ← 规则已确定的直接跳过（正确策略）
```

**为什么只补 3 个**：Ernie 免费模型对「只输出 JSON + 元数据抽取」这类任务，
在连续调用后返回空串/低置信（之前全量抽取也遇到 429 限流）。
分级策略正确地**没有**用低质量结果覆盖规则结果——这是好事。

### 建议

| 场景 | 是否补 LLM | 理由 |
|---|---|---|
| **venue（15 篇真缺口）** | ❌ 不补 LLM，用外部元数据 | 实测 vLLM 也全部低置信（0-0.1）——从摘要推 venue 本身不可靠；应查 DBLP/S2 API 按 arxiv_id 精确匹配 |
| evidence_type（已 100%） | ❌ 不需要 | 当前已全覆盖，再补只在 conf≥0.7 时有边际收益 |
| D6 artifact | ❌ 不需要 | 100% 确定性判定，LLM 不会更准 |
| 众数填充的 4 篇 evidence_type | ⚠️ 可选 | 若要求高可信，用 vLLM 校验；否则标记 source=family_mode 即可 |

**实测追加**：用 vLLM 对 6 篇 unknown venue 补，全部返回 unknown（confidence 0–0.1）。
**结论修正**：venue 不该用 LLM——摘要里通常不写 venue，模型只能猜。
正确路径是 DBLP/Semantic Scholar 按 arxiv_id 精确查询（确定性，零幻觉）。
当前阶段④路由已 100% 成功，venue 只影响阶段⑧⑨，可延后到写作阶段前接外部 API。

## 5. 流程调整建议落地情况

| 建议 | 状态 |
|---|---|
| 阶段② 改用 D1 流派社区 | ✅ 已实现（method_communities） |
| 阶段④ 同时读 D2+D3 | ✅ 路由已实现（phase_router） |
| 阶段⑤ 按 D1 选工具链 | ✅ 路由已实现（BY_METHOD_FAMILY.tools） |
| 阶段⑧⑨⑩ 补 venue | ⚠️ 50%，不阻塞，可延后 |
| 新增 D6 artifact_protocol | ✅ 100% |

## 6. 产物

```
src/capfactory/applayer/metadata_enrich.py       D5/D6 确定性补全
stages/2_knowledge/fill_gaps.py                   D2/D3 分级补全
stages/2_knowledge/llm_backfill_metadata.py      LLM 分级补 venue
storage/sciforge/factory_knowledge_final.json    最终图（6维 100/100/100/98/50/100）
```

## 7. 一句话

**6 维分类里 5 维已 100%，唯一缺口 venue 有 50% 但其中 11 篇是预印本（非真缺口）。
实测 LLM（Ernie 和 vLLM）都补不动 venue——答案是查 DBLP/S2，不是换模型。
不阻塞当前流程，写作阶段前接外部 API 即可。**
