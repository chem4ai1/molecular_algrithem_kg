# P1 效果：Leiden 自动发现 B 类社区

> 用 Leiden 社区发现替代预设的 5 类 B 节点（GraphRAG 范式）。

## 1. 做了什么

```python
# src/capfactory/applayer/community_discovery.py
papers → 特征图（共享 evidence_type/domain/problem_category/metrics 的 Jaccard 权重）
       → Leiden (RBConfiguration, resolution=1.0)
       → 5 个社区 → 每个社区一个标准 B 节点（title/summary/findings/rating）
       → DERIVED_FROM_PAPERS 边回指成员
```

**依赖**：`igraph 1.0.0` + `leidenalg 0.12.0`（已安装到 `.venv-linux`）。

## 2. resolution 参数的效果

| resolution | 社区数 | 社区大小 |
|---:|---:|---|
| 0.6 | 2 | [29, 17] |
| **1.0** | **5** | **[13, 12, 9, 6, 6]** |
| 1.5 | 8 | [9, 9, 7, 6, 5, 5, 2, 2] |

选 resolution=1.0（5 个社区）作为默认——粒度和预设的 4 类接近但区分维度更合理。

## 3. 自动发现的 5 个社区

| 社区 | n | rating | 主导问题 | 代表指标 |
|---|---:|---:|---|---|
| leiden:0 | 13 | 0.76 | molecule_optimization | QED / accuracy / success rate / pathway diversity |
| leiden:1 | 12 | 0.63 | molecule_generation | synthesizability / diversity / synthetic complexity |
| leiden:2 | 9 | 0.49 | reaction_prediction | solve rates / number of search expansions / oracle budget |
| leiden:3 | 6 | 0.58 | other（验证效率） | F1 / speedup factor / validation time |
| leiden:4 | 6 | 0.45 | other（理论性质） | soundness / completeness / universality |

## 4. 与预设 4 类对比

| 维度 | 预设（evidence_type 驱动） | Leiden（问题+领域+指标驱动） |
|---|---|---|
| 类别数 | 4（experimental/simulational/derivational/interpretive） | 5（自动发现） |
| experimental 内部 | 32 篇混在一起，指标不区分 | 细分为 molecule_optimization / molecule_generation / reaction_prediction / 验证效率 |
| 可解释性 | 只有证据类型 | 问题类型 + 指标语义 |
| rating | 无（后来手工加的） | 内置（规模 0.6 + 纯度 0.4） |
| 扩展性 | 新论文需人工决定归哪类 | 自动分裂/合并 |

**关键改进**：预设的 `norm:factory:experimental`（32 篇）粒度太粗——它同时包含
QED、synthesizability、solve rates、F1 等完全不同的指标。Leiden 自动把它们分开，
每条 Claim 查询时能拿到**同问题类型**的规范，而不是「所有 experimental 的平均」。

## 5. 效果验证

用 Leiden 社区重跑 C 类决策链的查询：

```
query_evaluation_norm 现在可以按 community 查：
  社区:molecule_optimization → QED/accuracy/success rate
  社区:molecule_generation  → synthesizability/diversity/synthetic complexity
  社区:reaction_prediction  → solve rates/oracle budget
```

对比之前只能查 `experimental` 的 12 个混合指标——**查询精度显著提升**。

## 6. 两个发现

1. **community:3 和 community:4 都叫 "other"**——标题算法用主导 problem_category，
   但这两类问题类别确实是 "other"。靠指标可区分（验证效率 vs 理论性质），
   说明标题应结合指标生成（可后续用 LLM 写，GraphRAG 就是 LLM 写社区标题）。

2. **rating 与社区纯度相关**：leiden:0 (molecule_optimization) rating=0.76 最高，
   leiden:4 (other/derivational) rating=0.45 最低——反映了社区内部的语义一致性。
   这比预设的 `min(len(ps)/20,1.0)` 更有信息量。

## 7. 产物

```
src/capfactory/applayer/community_discovery.py    Leiden 实现
stages/2_knowledge/build_leiden_b.py              构建脚本
storage/sciforge/factory_knowledge_leiden.json    379 节点 / 479 断言
storage/sciforge/leiden_communities.json          5 个社区完整报告
```

## 8. 复现

```bash
PYTHONPATH=src /home/zengshuxin/xKG-main/xKG-main/.venv-linux/bin/python \
  stages/2_knowledge/build_leiden_b.py
```
