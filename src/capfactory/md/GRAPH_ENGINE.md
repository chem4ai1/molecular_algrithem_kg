# 图谱引擎：自研 POGraph + networkx 适配

## 1. 现状：**不是**图数据库，也不是 networkx

图谱由自研 `capfactory/po/store.py::POGraph` 承载：

```
POGraph
 ├── nodes: Dict[str, Concept]        # 6001 个，id → dataclass
 ├── assertions: List[Assertion]      # 7460 条，source/target/relation/properties
 ├── _keys: set[(s,t,r)]              # 去重
 └── _adj_out/_adj_in                 # 惰性邻接索引（O(1) 查询）
```

- 存储形态：单个 JSON（`batch10_semantic_v4.json` 12MB），`json.load` 即用
- 不依赖 Neo4j / RDF 库 / 图数据库进程
- 查询走 `outgoing/incoming/by_type` + 惰性邻接索引，不是图查询语言

所以「放到 networkx 上」= 增加一层适配，而非替换存储。

## 2. 适配层：`po/nx_adapter.py`

| 函数 | 作用 |
|---|---|
| `to_networkx(g, layer=None)` | POGraph → `nx.MultiDiGraph` |
| `from_networkx(mg)` | 还原为 POGraph（往返无损于类型/关系/属性） |
| `stats(g)` | 节点/边/类型/关系分布、弱连通分量、密度、度分布、是否 DAG |
| `neighbours(g, node, hops)` | 有向多跳邻居（含跳数） |
| `shortest_path(g, src, dst)` | 有向最短路 + 沿途关系 |
| `export(g, path, fmt)` | 导出 `graphml` / `gexf` / `json` |

### 2.1 为什么是 `MultiDiGraph` 而不是 `DiGraph`

同一对节点之间可能有多条**不同关系**：

```
paper:2411.06608 --EVALUATED_ON--> benchmark:zinc
paper:2411.06608 --RELATED_TO---> algorithm:chemicalvae
paper:2411.06608 --PROPOSES_METHOD--> algorithm:molminer
```

`DiGraph` 会覆盖同端点边，`MultiDiGraph` 保留每条关系的 `key`（= `Assertion.id`）。

### 2.2 属性扁平化

GraphML/GEXF 只支持标量，因此：

- 节点属性：`type / label / layer / ...attrs`，`list/dict` 转 JSON 字符串
- 边属性：`relation / edge_id / attribution / lay(层) / task(任务) / p_*(业务属性)`
- `evidence_ids` 同样转 JSON 字符串，读回时按需 `json.loads`

## 3. 实测（语义层 6001/7460）

| 指标 | 值 |
|---|---|
| 图类型 | `networkx.MultiDiGraph` |
| 节点 / 边 | 6001 / 7460 |
| 弱连通分量 | **260**（每篇论文及其方法/基准簇） |
| 密度 | 0.00020719 |
| 度均值 / 中位 / 最大 | 2.49 / 2 / 33 |
| 是否 DAG | **True**（语义层无环） |
| 出度 Top3 | `SO3LR Tauri…`(33) / `A foundation model…`(27) / `AMP-Designer`(26) |
| 往返一致性 | 节点/边数与类型、关系全部一致 |
| GraphML 导出 | 9.47 MB（可被 `nx.read_graphml` 读回） |

## 4. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v9/graph/nx/stats?graph=semantic` | 图统计 |
| GET | `/api/v9/graph/nx/neighbors/{node_id}?hops=1` | 多跳邻居（hops ≤ 4） |
| GET | `/api/v9/graph/nx/shortest?src=&dst=` | 最短路 |
| GET | `/api/v9/graph/nx/export?fmt=graphml\|gexf\|json` | 下载图文件 |

`graph` 可选 `semantic`（默认）/ `application` / `task`。

导出文件落在 `storage/sciforge/exports/<graph>.<fmt>`，可直接用 Gephi / Cytoscape 打开。

## 5. 边界

- 转换是**内存快照**，每次调用 O(N+E)，6001/7460 约 0.3s；不做增量同步。
- 不改存储格式：语义层/应用层图仍是 JSON，networkx 只在计算与导出时使用。
- 与前端的关系浏览器无耦合：浏览器走 `relation_index.json`，不经过 networkx。
- 属性中原本是 `list/dict` 的字段（`model_results`、`keywords`）在 GraphML 里是 JSON 字符串，
  读回需要 `json.loads`；`json` 格式导出保留原生结构。
