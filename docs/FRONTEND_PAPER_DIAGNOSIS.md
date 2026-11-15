# 论文库前端问题：根因分析与修复（2026-11-13）

> 用户反馈：领域/研究问题/算法族显示 unknown；节点开头没有像算法库那样
> 的卡片，而是「该节点没有适配的可视化，见下方 JSON」；很多属性 unknown。

## 1. 结论先行

**不是缓存问题，也不是导入失败**，是三个独立的代码缺陷叠加：

| # | 现象 | 根因 | 类别 |
|---|---|---|---|
| 1 | 分类树里 26 个 unknown | 26 个 **proxy Paper 占位节点**被当成正式论文进了分类树；迁移时 `resolved_kind` 被裁掉，只剩 `domain="unknown"` | 数据 + 展示 |
| 2 | 属性显示 unknown、出现 `filled_by: llm_paper_core` | **`data_api._graph()` 从未切到新图源**。上轮替换的目标串写成 `POGraph("v6")`，实际是 `POGraph("data")`，`str.replace` 静默失败，页面一直读 legacy 图 | 代码缺陷 |
| 3 | 「该节点没有适配的可视化」 | `_viz()` 的 Paper 分支依赖 `Paper-REPORTS->Observation` 找观测值；**语义层已删 Observation 与 REPORTS**，所以恒返回 `{"kind":"none"}` | 架构变更后未同步 |
| 4 | 点开论文看不到方法/基准/代码链 | `applayer/miner.py` 只复制语义层**节点**，没复制语义层**断言**，应用层图里 `paper:*` 的 outgoing 只剩应用层关系 | 代码缺陷 |

## 2. 逐项证据

### 2.1 图数据本身是对的

```
语义层 Paper(paper:2411.06608) 12 个属性：
  domain         = 分子生成与从头设计      （不是 unknown）
  domain_code    = D1
  flow_family    = 片段/结构化生成
  why_hard       = 现有自回归模型通常依赖固定展开顺序…（中文长句）
  keywords       = 36/36 篇都有
```

但 API 返回的 attrs 是
`{filled_by: llm_paper_core, schema_version: v3_paper_core, domain_codes: [...]}` ——
这些字段只存在于 **legacy 图**。直接证明 `_graph()` 读错了文件。

### 2.2 unknown 的 26 个是什么

语义层 36 个 Paper 里：

```
10 个宿主论文：domain 有中文值
26 个 proxy  ：domain = "unknown"
```

这 26 个是「相关论文线索」解析时建的方法名占位（`paper:src:*`），
用途是让论文-论文链可跳转，**不是可分类的论文实体**。

### 2.3 `_viz` 的死分支

```python
if t == "Paper":
    ids = _by_paper(g, aid, ("REPORTS",))   # 语义层已无 REPORTS
    grp = _obs_groups(g, ids)               # 语义层已无 Observation
    return metrics if grp else {"kind": "none"}
```

`data.html:221` 遇到 `kind==='none'` 就输出那句提示。算法库之所以正常，
是因为它的 `Algorithm` 分支还在（且 `AlgorithmModule` 被别名回 `AlgorithmStep`）。

## 3. 修复

| 修复 | 位置 |
|---|---|
| `_graph()` 真正改为 `graph_source.load("application")` | `web/data_api.py` |
| Paper 卡片：`kind="paper_core"`，展示三核心 + 瓶颈 + 关键词 + 4 类关系链 | `data_api._viz` + `static/data.html` `vizHTML` |
| unknown 分组改名为「待补全（关系线索）」并排到最后 | `data_api.tree` |
| `meta.research_problem` 兼容 `research_question`；族兼容 `flow_family` | `data_api.tree` |
| `mine_all` 复制语义层 401 条断言到应用层图 | `applayer/miner.py` |
| 提示文案改「该节点暂无可视化，属性与关系见下方 JSON」 | `static/data.html` |

修复后的实测：

```
domain groups：7 个真实领域 + 「待补全（关系线索）」26（排最后），无 unknown
node_card(paper:2411.06608).viz.kind = paper_core
  core: research_question / domain / problem_category / flow_family / why_hard / keywords
  chains: 方法1 · 基准6 · 代码1 · 相关6
应用层图 744 节点 / 993 断言（含 401 条语义层断言）
```

## 4. 回答用户的三个疑问

- **「是关系没清楚吗？」** 一部分是：`mine_all` 没复制语义层断言，导致论文卡片读不到方法/基准/代码关系。已修。
- **「是缓存吗？」** 不是缓存（重启也一样）。是 `_graph()` 的图源替换静默失败，属于代码缺陷。
- **「是没成功导入吗？」** 不是：语义层与应用层图文件里的属性都是中文真值。只是页面读了错误的图。

## 5. 仍需注意

- 26 个 proxy 仍在图里（关系浏览器需要它们做跳转），只是**不再混进论文分类树**；
  若要彻底不显示，可在 `tree()` 里直接过滤 `resolved_kind=="proxy"`，但那样会丢掉
  「待补全」的可见性，本轮选择保留为独立分组。
- `node_card` 的 attrs 仍保留 `"unknown"` 原值供下方 JSON 查看；
  Paper 核心卡片会跳过这些值，不显示成 "unknown"。
