# 52 篇新论文全量抽取配置（algorithm factory batch）

> 本目录在标准 E1–E6 / R1–R6 之外，新增针对新论文库（`data/paper_seed/papers`）的
> 抽取对象与图谱/决策链配置。所有抽取对象由 `data/extract_target/batch/` 声明。

```
extract_target/
├── stages/          E1–E6 一次抽取（标准）
├── refine/          R1–R6 二次抽取（标准）
├── batch/           ★ 本次新增
│   ├── papers.yaml          52 篇抽取对象清单（含类别/arxiv_id）
│   ├── B1_lineage.yaml      B类：方法族谱聚合
│   ├── B2_norm.yaml         B类：领域评价规范聚合
│   ├── B3_failure_lib.yaml  B类：失败模式库聚合
│   ├── C1_claim.yaml        C类：主张形式化（独立阶段）
│   └── C2_gap_triple.yaml   C类：空白三元组
```

抽取后端：`baidu/ernie-5.5-flash-preview:free`（OpenRouter，key 在 `API_KEY/openrouter`）。
