# 论文生成各阶段的分类需求：从「阶段要什么」反推分类维度

> 核心问题：是否需要针对论文做多种分类？
> 结论：**需要，而且不能只有一种**——因为不同阶段消费的知识维度不同。
> 分类应该是**正交的多标签**，不是一个互斥的单一类别。

## 1. 十个阶段回顾（知识 / skill / 门控）

| 阶段 | 需要什么知识 | 应调 skill | 门控判据 | 单一分类够吗？ |
|---|---|---|---|---|
| ① 问题锚定 | 领域常识、问题分类学、可行性（数据/算力/时间） | `intake-triage`, `domain-signature` | Q-ID 冻结、可回答判据 | ❌ 需要「领域×可行性」 |
| ② 领域定位 | 文献地图、**方法族谱**、评价规范 | `universal-retrieval`, `novelty-check` | gap 带 cite_key + 原文位置 | ❌ 需要「方法流派×证据规范」 |
| ③ 想法生成 | 跨领域类比、方法组合、可行性 | `idea-discovery`, `adversarial-falsification` | mechanism + 证伪条件 | ❌ 需要「方法流派」+「跨领域桥」 |
| ④ 主张形式化 | 逻辑、实验设计、领域证据规范 | `method-registry`, `invariant-check` | polarity + refutation + 矩阵锁 | ❌ 需要「证据规范×研究范式」 |
| ⑤ 实现验证 | 工程实现、基线复现、工具链 | `experiment-execution`, `dynamic-sandbox` | 基线同口径复现、toy 判决 | ❌ 需要「实现类型×工具链」 |
| ⑥ 证据生产 | 实验执行、统计、算力 | `experiment-ladder`, `ablation-planner` | seeds、消融完整性、阴性记录 | ❌ 需要「实验类型×领域规范」 |
| ⑦ 证据审计 | 逻辑、统计、领域失败模式库 | `leakage-audit`, `logic-verification`, `result-to-claim` | claim 定档、三类泄露 | ❌ 需要「失败模式×证据类型」 |
| ⑧ 叙事设计 | 论证结构、venue 惯例、读者预期 | `paper-writing`(结构段), `unified-plotting` | 章节-claim 绑定、图-claim 绑定 | ❌ 需要「venue×论证模式」 |
| ⑨ 起草对抗 | 学术写作、语体、引用规范 | `paper-writing`, `citation-audit`, `kill-argument` | 措辞不越级、引用上下文正确 | ❌ 需要「venue×语体」 |
| ⑩ 终检交付 | 引用核验、可发表性、工程打包 | `citation-audit`, `publishability-score`, `quality-gate` | 三层引用、复现包 verification | ❌ 需要「venue标准×交付协议」 |

**结论**：没有任何单一分类能同时服务这 10 个阶段。必须多维度正交标签。

## 2. 六个正交分类维度

| # | 维度 | 取值（当前 52 篇可落） | 服务阶段 | 产出类/字段 |
|---|---|---|---|---|
| **D1** | **方法流派**（method_family） | edit_sequence / gflownet / diffusion_flow / llm_agent / llm_finetuned / retro_search / rule_symbolic / benchmark_eval / property_surrogate … | ②③⑤⑥ | `Paper.method_family`（已做）+ 流派社区 |
| **D2** | **证据范式**（evidence_type） | experimental / simulational / derivational / interpretive / causal_inference | ④⑥⑦ | `Paper.evidence_type` + `EvaluationNorm` |
| **D3** | **研究范式**（paradigm） | formal / empirical / design / interpretive | ①④⑦ | `Paper.paradigm` |
| **D4** | **问题类型**（problem_category） | molecule_optimization / molecule_generation / reaction_prediction / property_prediction / benchmark … | ①②⑧ | `Paper.problem_category` |
| **D5** | **venue / 写作惯例**（venue_profile） | NeurIPS / ICLR / Nature MI / JMLR / other（当前全缺） | ⑧⑨⑩ | `VenueProfile`（待补元数据） |
| **D6** | **交付/可复现协议**（artifact_protocol） | code+data / benchmark-only / theory-only / survey | ⑤⑩ | `Paper.reproducibility_tier`（待建） |

**正交性**：一篇论文可以同时是
```
method_family = edit_sequence（D1）
evidence_type = experimental（D2）
paradigm      = design（D3）
problem_cat   = molecule_optimization（D4）
venue         = Nature MI（D5）
artifact      = code+data（D6）
```
每个阶段只读取它需要的维度，不被其他维度干扰。

## 3. 分类 → skills / 协议 / 门控 的路由规则

### D1 · 方法流派路由

| method_family | 阶段②检索 | 阶段③可用类比 | 阶段⑤工具链 | 阶段⑥实验协议 | 专属门控 |
|---|---|---|---|---|---|
| `edit_sequence` | SynCraft/MECo 流派社区 | 编辑→逆合成反馈组合 | 分子编辑工具 | 编辑步数/成功率 | 编辑合法性 |
| `gflownet` | SynFlowNet/RGFN 社区 | GFlowNet+奖励塑形 | GFlowNet 训练栈 | reward/多样性 | 采样覆盖度 |
| `diffusion_flow` | 扩散/流社区 | 连续→离散迁移 | 流模型库 | solver 稳定性 | 可逆性检查 |
| `llm_agent` | LLM agent 社区 | agent+工具链组合 | tool registry | agent trace | 工具调用成功率 |
| `retro_search` | 逆合成搜索社区 | 搜索+生成融合 | ASKCOS/RDKit | 搜索预算 | 路线可合成性 |
| `rule_symbolic` | 符号系统社区 | 规则→神经融合 | 推理引擎 | 形式化验证 | soundness/completeness |

### D2 · 证据范式路由（决定门控严格度）

| evidence_type | 最低保真度 | 必需实验 | 措辞许可 | 对应 skill |
|---|---|---|---|---|
| `experimental` | numerical | baseline + 多 seed + 消融 | 可说 proven（满足条件后） | `result-to-claim`, `leakage-audit` |
| `simulational` | numerical | oracle 预算 + 多次采样 | supported | `experiment-ladder` |
| `derivational` | symbolic | 定理/证明审计 | proven（数学意义） | `theory-derivation`, `logic-verification` |
| `interpretive` | qualitative | 案例 + 反例讨论 | suggests | `adversarial-falsification` |

### D3 · 研究范式路由（决定阶段④的主张结构）

| paradigm | 主张形式 | 证伪方式 | 门 |
|---|---|---|---|
| `formal` | 定理/引理 | 反例 | proof audit |
| `empirical` | 数值假设 | 显著性检验 | seeds + baseline |
| `design` | 系统有效性 | 消融 + 用户/任务评估 | artifact + ablation |
| `interpretive` | 观点/框架 | 反例讨论 | strongest counterargument |

### D5 · venue 路由（决定⑧⑨⑩的写法与门）

| venue 类型 | 章节模式 | 引用格式 | 图表预算 | 可发表性门槛 |
|---|---|---|---|---|
| ML 顶会（NeurIPS/ICLR/ICML） | Intro/Method/Exp/Ablation/Related | author-year | 严格 | baseline+ablation |
| Nature 系 | Abstract/Main/Methods(back) | numeric | 少而精 | 叙事简洁+impact |
| 领域会（VIS/Bioinformatics） | 系统/评测/案例 | 视具体 | demo 重要 | artifact |
| survey/review | 分类学/对比/趋势 | author-year | 表格密集 | 覆盖度 |

> **当前 52 篇 venue 全缺失**——这是 D5 路由的阻塞点，必须外部元数据补全。

## 4. 这些分类怎么落到代码

### 4.1 语义层（从论文抽取，客观事实）

```python
Paper.method_family       # D1（已标注 52 篇）
Paper.evidence_type       # D2（已有 95.8%）
Paper.paradigm            # D3（已有 95.8%）
Paper.problem_category    # D4（已有 96.9%）
Paper.venue               # D5（缺失，需外部补全）
Paper.artifact_protocol   # D6（待建）
```

### 4.2 B 类图谱（离线聚合，物化视图）

```
MethodFamily community (D1)  ← 已做（4 个流派社区）
EvaluationNorm (D2)          ← 已有（按 evidence_type）
ParadigmNorm (D3)            ← 待建（按 paradigm 聚合主张结构）
VenueProfile (D5)            ← 有节点但数据缺失
ArtifactProtocol (D6)        ← 待建
```

### 4.3 路由函数（在线，按阶段读不同维度）

```python
def route_skill(phase: int, paper_profile: dict) -> list[str]:
    if phase == 2:
        return SKILLS_BY_METHOD_FAMILY[paper_profile["method_family"]]
    if phase == 4:
        return SKILLS_BY_EVIDENCE[paper_profile["evidence_type"]] + \
               SKILLS_BY_PARADIGM[paper_profile["paradigm"]]
    if phase in (8, 9, 10):
        return SKILLS_BY_VENUE.get(paper_profile["venue"], DEFAULT_VENUE_SKILLS)
    ...
```

## 5. 每个分类维度的「获取方式」

| 维度 | 获取方式 | 是否需要 LLM | 稳定性 |
|---|---|---|---|
| D1 方法流派 | 关键词规则 + LLM 修正 + 社区聚合 | 混合 | 中（流派会演化） |
| D2 证据范式 | E1 词表抽取 + 交叉校验（有 model_results 不能判 derivational） | 是 | 高 |
| D3 研究范式 | E1 词表抽取 | 是 | 高 |
| D4 问题类型 | E1 词表抽取 | 是 | 高 |
| D5 venue | **外部元数据**（DBLP/S2）或从 PDF 页眉解析 | 否 | 高 |
| D6 artifact | 代码仓库存在性 + 是否 benchmark + 是否 theory | 否 | 高 |

**关键**：D5/D6 不需要 LLM——它们能从元数据/文件系统确定性得出，不该浪费 token。

## 6. 对当前流程的调整建议

1. **阶段② 改用 D1 流派社区**替代 evidence_type 做检索（已实现雏形，待接到 `query_*`）
2. **阶段④ 同时读 D2+D3**——证据范式决定保真度，研究范式决定主张结构（当前只读了 D2）
3. **阶段⑤ 按 D1 选工具链**——不同流派调不同 skill（当前没有路由）
4. **阶段⑧⑨⑩ 需要补 D5 venue 元数据**——否则写作门控只能按默认，无法按 venue 定制
5. **新增 D6 artifact_protocol**——阶段⑤/⑩ 据此决定要不要做复现包

## 7. 一句话总结

**10 个阶段需要 6 个正交分类维度**：方法流派、证据范式、研究范式、问题类型、venue 惯例、交付协议。
前四个已部分抽取，后两个是阻塞点。分类不是目的——目的是让每个阶段**按类路由到正确的 skill + 协议 + 门控**。

## 8. 路由实现与实测

`src/capfactory/applayer/phase_router.py` 实现了 `route(phase, profile)`：

```python
from capfactory.applayer.phase_router import route
r = route(4, {"method_family": "edit_sequence", "evidence_type": "experimental",
              "paradigm": "design", "venue": "NeurIPS"})
# → {skills: [result-to-claim, leakage-audit, ablation-planner],
#    claim_contract: {min_fidelity: numerical, required: [baseline, multi_seed, ablation],
#                     claim_form: system_effectiveness, falsify_by: ablation},
#    gate: claim_locked}
```

**实测两篇不同流派论文的路由差异**：

| 论文 | D1 流派 | 阶段② skills | 阶段②门 | 阶段④ claim_form |
|---|---|---|---|---|
| 2512.20333 SynCraft | edit_sequence | method-registry, leakage-audit | edit_validity | （D2/D3 缺失→空） |
| 1911.00598 SHACL | rule_symbolic | theory-derivation, logic-verification | soundness_completeness | theorem |

**发现的缺口**：SynCraft 的 `evidence_type`/`paradigm` 在全量抽取时为 None（11% 论文未判），
导致阶段④路由为空。这不是路由 bug，是上游抽取缺口——需重抽或用同流派社区的值填充。

## 9. 结论

- **多种分类是必需的**：6 个正交维度分别服务不同阶段
- **分类的价值在路由**：不路由到 skill/门控的分类只是标签
- **当前就绪度**：D1/D2/D3/D4 已抽取（D1 刚做，D2/D3 有 5% 缺口），D5 venue 全缺，D6 待建
