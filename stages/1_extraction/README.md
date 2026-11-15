# 阶段 1 · 知识抽取

输入 `data/papers/*.md`，输出 `storage/sciforge/semantic_extraction/<aid>.json`。

链路：切片 → paper_type 分类 → E1–E6 LLM 阶段 → 校验 → 范式层
（NER / 规范化 / 关系逐字落地 / 模块追踪 / 槽位审计）。

实现位置：

| 职责 | 文件 |
|---|---|
| 阶段编排、切片、CSV 校准 | `src/capfactory/semantic/extraction/runner.py` |
| 契约与词表裁剪 | `contracts.py` / `prompts.py` / `vocab.py` |
| 校验与证据归一 | `validator.py` |
| T-Box / A-Box 指导、类型判定 | `guides.py` |
| 范式层 | `paradigm.py` |
| 批量断点续跑 | `src/capfactory/semantic/batch_extract.py` |

```bash
python stages/1_extraction/run_one.py 2411.06608
python stages/1_extraction/run_batch.py --limit 3
python stages/1_extraction/run_batch.py --status
```
