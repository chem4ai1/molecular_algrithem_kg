# B 类离线聚合 与 画像路由：详细机制

## 第 05 步：B 类离线物化（offline materialization）

### 5.1 为什么要"离线一次建"

B 类不是从单篇论文抽出来的，是**跨 52 篇比较后才有意义**的规律：
- "这个领域认什么指标" —— 单篇论文只能告诉你它自己用了什么
- "哪个方法族谱最大" —— 必须统计所有方法
- "失败模式有哪些" —— 必须汇总所有论文的 limitations

如果每次生成论文都重新统计一遍，会有三个问题：
1. **慢**——每次扫 52 篇图
2. **不稳定**——语料变了结果就变，无法对比
3. **不可追溯**——不知道某条规范是哪几篇支撑的

所以做法是：**跑一次，把结果写成节点存在图里**（这就是"物化视图"materialized view），
后续所有生成直接查这些节点。

### 5.2 构图：从 A 类属性造一张"论文相似图"

`community_discovery.build_similarity_graph()`：

```python
# 每篇论文抽特征集合
feats[p] = {
  "family=edit_sequence", "family=edit_sequence", "family=edit_sequence",  # ×3 权重
  "problem_category=molecule_optimization",
  "evidence_type=experimental",
  "metric=QED", "metric=success rate", ...
}

# 两两算 Jaccard 相似度
w(i,j) = |feats[i] ∩ feats[j]| / |feats[i] ∪ feats[j]|

# 只保留 w >= 0.1 的边
```

**关键设计**：`method_family` 重复 3 次 → 在 Jaccard 里权重大大提高。
这样社区主要按"方法流派"聚，而不是按"问题类别"聚。

### 5.3 Leiden 社区发现

```python
la.find_partition(
    ig_g, la.RBConfigurationVertexPartition,
    weights=ig_g.es["weight"],
    resolution_parameter=1.0,
    seed=42)       # 固定种子，保证可复现
```

`resolution` 的效果（实测）：

| resolution | 社区数 | 大小 |
|---:|---:|---|
| 0.6 | 2 | [29, 17] |
| **1.0** | **5** | [13, 12, 9, 6, 6] |
| 1.5 | 8 | [9, 9, 7, 6, 5, 5, 2, 2] |

用户要求"分得更细"→ 用 method_family 加权 + resolution=1.0，得到 4–5 个有意义的流派社区。

### 5.4 社区摘要：GraphRAG 结构

每个社区跑 `summarize_community()`，产出标准属性：

```python
{
  "title": "社区:molecule_optimization",
  "summary": "从 13 篇论文自动发现的社区，主导问题 molecule_optimization",
  "findings": [
    {"summary": "证据类型: experimental(12), derivational(1)", "explanation": "在 13 篇社区成员中统计"},
    {"summary": "指标: QED(3), accuracy(1), success rate(1)", "explanation": "..."}
  ],
  "rating": 0.76,                 # 规模×0.6 + 纯度×0.4
  "rating_explanation": "n=13, 主导证据纯度=0.92",
  "n_papers": 13,
  "members": [paper_id, ...]
}
```

**rating 是 GraphRAG 社区报告的标准字段**——它让下游知道"这条规范有多可信"。
实测：molecule_optimization 社区 rating=0.76，other/derivational 社区 rating=0.45。

### 5.5 物化：写节点 + 回指边

```
EvaluationNorm norm:factory:experimental
  │
  ├─ DERIVED_FROM_PAPERS → paper:2002.07007
  ├─ DERIVED_FROM_PAPERS → paper:2407.12186
  └─ ...（共 32 条边）

MethodLineage lineage:factory:molecule_generation
  │
  ├─ LINEAGE_OF → algorithm:synflownet
  ├─ LINEAGE_OF → algorithm:rgfn
  └─ ...（共 9 条边）

FailureModeLibrary failurelib:factory
  └─ FAILURE_SEEN_IN → paper:2002.07007（共 7 条边）
```

**回指边的作用**：任何 B 类结论都能追问"你从哪几篇论文得出"。
比如 `rating=0.76` 的规范，点开能看到 13 篇来源论文。

### 5.6 实测图里的样子

我刚查了 `factory_knowledge_leiden.json`：

```
MethodLineage: 6 个
  lineage:factory:molecule_generation
    出边 9: LINEAGE_OF → fmg / synflownet / rgfn ...

EvaluationNorm: 9 个
  norm:factory:derivational
    title=derivational 证据规范 | rating=0.3 | n_papers=6
    findings[0]={认可指标：soundness, docking, safety, efficacy}
    出边 6: DERIVED_FROM_PAPERS → 1911.00598 / 2402.15864 / ...

FailureModeLibrary: 1 个
  出边 7: FAILURE_SEEN_IN → ...
```

---

## 第 06 步：按画像路由（route_phase）

### 6.1 什么是"画像"（profile）

每篇论文有 7 个正交标签：

```python
profile = {
  "method_family": "edit_sequence",     # D1
  "evidence_type": "experimental",      # D2
  "paradigm": "design",                 # D3
  "problem_category": "molecule_optimization",  # D4
  "venue": "NeurIPS",                   # D5
  "artifact_protocol": "code+data",     # D6
  "data_modality": "smiles",            # D7
}
```

### 6.2 路由做什么

**同一个阶段，不同论文应该调不同 skill、过不同门**。
`phase_router_v2.route_phase(phase, profile)` 就是这张映射表。

### 6.3 P1 的路由实例（用户问的例子）

```python
# 编辑序列流派
ROUTE_TEMPLATE["edit_sequence"] = {
  "modules": ["edit_generator", "edit_executor"],
  "why_not": "为什么不直接端到端生成 SMILES",
  "arch_elems": ["初始分子", "编辑动作", "执行器", "输出分子"],
  "key_challenge": "编辑动作的可执行性与可解释性",
}
```

调用：
```python
route_phase("P1", {"method_family": "edit_sequence", ...})
→ {
  "phase": "P1",
  "skills": ["method-registry"],
  "route_template": {modules: [...], why_not: ..., arch_elems: [...]},
  "gate": "has_why_not_other"
}
```

**这些不是我编的**——是从 MECo 论文反推的：
- `edit_generator` = MECo 的 reasoning LLM（生成编辑意图）
- `edit_executor` = MECo 的 code LLM（转成可执行代码）
- `why_not` = MECo 3.1 批评"直接生成 SMILES 不透明"

### 6.4 符号流派的例子

```python
ROUTE_TEMPLATE["rule_symbolic"] = {
  "modules": ["constraint_compiler", "inference_engine", "validator"],
  "why_not": "为什么不用端到端学习",
  "arch_elems": ["本体", "约束", "推理规则", "验证结果"],
  "key_challenge": "形式语义的完整性与推理效率",
}
gate = "has_why_not_other"        # 当前实现：P1 统一用此门
# 注：soundness_completeness 是设计稿中的规划值，代码尚未按流派分化 P1 门控
```

从 SHACL/Trav-SHACL/DaRLing 论文反推。

### 6.5 其他阶段的路由维度

| 阶段 | 读哪个画像维度 | 输出什么 |
|---|---|---|
| P0 | D1 流派 | `form`: 有公式流派→`math_definition+limits`；llm_agent→`problem_statement+workflow` |
| P1 | D1 | modules / why_not / arch_elems / key_challenge 模板 |
| P2 | **D7 模态** | smiles→`[rdkit, rdchiral]` + `Tanimoto<0.6`；3d→`[openbabel]` + RMSD |
| P6 | D2 证据 | experimental→`[success_rate, validity, similarity, constraint]` |
| P7 | P1 的 modules | ablation_targets = 创新组件 |
| P8 | D1 | 图类型（gflownet 不做 case 图） |
| P9 | D5×D1 | 章节模板（12 节 / 9 节 / 6 节 / Nature 5 节） |
| P11 | D6 交付 | code+data→`[code, data, env, script]` |

### 6.6 门控的真实阻断

路由输出的 `gate` 不是注释，是会被审计的判据：

- `has_why_not_other` —— P1 没有"为什么不用别的方法"→ BLOCKED
- `soundness_completeness` —— 规划中的符号系统专用门（尚未在 P1 实现，当前统一用 has_why_not_other）
- `no_test_leakage` —— P2 测试集与训练集 Tanimoto ≥ 阈值 → BLOCKED
- `every_figure_has_claim` —— P8 图不绑 claim → BLOCKED

我在 `WritingContext` 接口里实测触发过：
```
无 refutation_condition 的 Claim → BLOCKED
verification=pending 的交付包 → BLOCKED
```

---

## 两步的关系

```
05 B 类聚合：把 52 篇的规律沉淀成节点（一次建，长期用）
                    ↓ 被查询
06 画像路由：用论文画像 + B 类知识，决定"这阶段调什么 skill、过什么门"
                    ↓
           C 类决策节点（带 source/via，可追溯查到 B 类节点）
```

**没有 05，06 就是凭空判断**——`why_not_other`/`frontier_baseline`/`grade` 都会变成 LLM 自由发挥。
有了 05，每个决策都能回答"从哪条规范/哪个社区查来的"。

## 复现

```bash
PYTHONPATH=src python3 stages/2_knowledge/build_leiden_b.py
PYTHONPATH=src python3 -c "
from capfactory.applayer.phase_router_v2 import route_phase
print(route_phase('P1',{'method_family':'edit_sequence'}))
print(route_phase('P1',{'method_family':'rule_symbolic'}))
"
```
