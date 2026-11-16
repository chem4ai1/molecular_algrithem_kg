# 抽取目标配置（声明式）

抽取对象、字段、prompt 模板全部写在这里，Python 只负责读取与执行。
新增一类节点 / 一个属性 / 一条关系，**只改这里的 YAML**，不动代码。

```
extract_target/
├── stages/    一次抽取：E1–E6，按阶段读原文整节
├── refine/    二次抽取：基于已有抽取结果，回到原文对应段落补抽
└── _schema.md 配置字段说明
```

加载优先级：`data/extract_target/` > 内置常量（`contracts.py` / `prompts.py`）。
目录为空或文件缺失时自动退化到内置，保证迁移期行为不变。
