# capfactory 模块地图与改造指南

> 本文件是**后续改造的入口**。先读这里，再动手改代码。
> 设计依据：[docs/ARCHITECTURE_V2.md](../docs/ARCHITECTURE_V2.md)、
> [docs/SCHEMA_AUDIT.md](../docs/SCHEMA_AUDIT.md)、
> [docs/LAYERS_AND_CODE.md](../docs/LAYERS_AND_CODE.md)、
> [docs/V2_PILOT_EGNN.md](../docs/V2_PILOT_EGNN.md)

---

## 1. 现在是什么

97 个 Python 文件 / 约 23,000 行。历史上多次迭代叠加，同一职责有 3–4 套实现。
**V2 架构正在收敛中，目前是「新入口 + 旧实现转发」共存状态**，不是已经重写完。

```
新代码一律从 capfactory.ontology 导入
        │
        ├── V2 定义（25 类 / 46 关系 / 字段三态）
        └── V1 兼容导出（38 类 / 41 词表，用于读旧图）
```

---

## 2. 目标分层（7 层，单一职责）

| 层 | 目录 | 职责 | 现状 |
|---|---|---|---|
| **本体** | `ontology/` | ★ 唯一 schema 源 | ✅ 已建，新代码直接用 |
| 图 | `po/store.py` `kg/` `algograph/store.py` | 图存储 / 校验 / 派生 | ⚠️ 3 套，待合并为 `graph/` |
| 模型 | `llm/` | ★ 唯一模型接入层 | ✅ `backends.py` 已建；`client.py`/`agents.py` 是主流水线 |
| 解析 | `ingest/` | PDF → Markdown → Section | ✅ 单栏 PyMuPDF / 双栏 MinerU(:8886) |
| 抽取 | `kbpipe/` | 抽取 / 归一 / 链接 / 修复 | ⚠️ 12 文件，待合并为 `extract/` |
| 索引 | `vector/` `vision/` | bge 向量库 / VL 图片库 | ⚠️ `store.py`+`multistore.py` 待统一为 `index/` |
| 接口 | `web/` | v2/v3/v4/v5 API + 工作台 | ✅ 45 项冒烟覆盖 |

---

## 3. 保留模块清单（不要动）

| 模块 | 为什么保留 |
|---|---|
| `pipeline.py` | **CapFactory 主流水线**（6 Agent），`cli.py`/`web/` 依赖；注意不要被同名包遮蔽 |
| `llm/client.py` `llm/agents.py` | 主流水线的 LLM 与 6 Agent，离线模式可用 |
| `schema/` `kg/graph.py` `kg/store.py` | 主能力图与复刻流水线的数据结构 |
| `replicate/` `research/` `integration/` | 复刻验证、缺口分析、SciForge 桥接，均有测试覆盖 |
| `algograph/schema.py` `algograph/store.py` | ★ CAD 代码图（13 类源码节点 + 7 类因果本体），**代码层要复用它** |
| `ingest/mineru.py` | 双栏分流，依赖 docker `mineru-api:8886`（GPU 1） |
| `po/concepts.py` `po/vocab.py` `po/store.py` | 现有 786 节点图的读取与校验，删了旧图全废 |
| `web/*.py` | 4 个工作台 + 45 项冒烟 |

---

## 4. 已经收敛的重复（本轮完成）

| 之前 | 现在 | 旧名保留 |
|---|---|---|
| 4 套 JSON 宽容解析 | `utils.parse_llm_json` | `vision.repair_json`、`vector.labeler._json_of`、`kbpipe.eval._json_of`、`kbpipe.extractor._json_block` 都是转发别名 |
| 4 套 LLM 后端各自配 model/url/timeout | `llm/backends.py: BACKENDS / spec() / chat()` | 原 4 个客户端不动 |
| 4 个 schema 定义文件各导入一遍 | `capfactory.ontology` 单一入口 | `po.*` 文件保持兼容 |
| `utils.chunk_text`(滑窗) 与 `kbpipe.chunker.chunk_text`(段落) 同名 | `utils.sliding_window` | `chunk_text` 保留为 deprecated 别名 |

**判断重复的标准**：同名函数/类出现 ≥2 次，或同一配置（model/url/token 预算）散落 ≥2 处。

---

### 4.1 已物理归档（本轮完成）

`capfactory/legacy/` 收两个旧实现，原位置留兼容 shim：

| 文件 | 原位置 | 替代 |
|---|---|---|
| `legacy/eval_extraction.py` | `kbpipe/eval.py` | `ontology/prompts.py` |
| `legacy/po_mapper.py` | `po/mapper.py` | `ontology/instantiate.py` |

`legacy_report()` 给出清单与 `PENDING`（尚未移动的模块）。
移动时改写相对导入，359 个测试与 45 项冒烟全部保持通过。

## 5. 待降级 / 待废弃（不要直接删）

| 模块 | 依据 | 建议动作 | 前置条件 |
|---|---|---|---|
| `po/mapper.py` | V1 ↔ domain 双向转换，V2 不需要 | 标 `legacy`，停止新增调用 | 确认 `po_api` 不再用 |
| `kbpipe/eval.py` | free/schema 对照评估脚本，**不是生产链路** | 移到 `tools/` | 补一个 dev-only 入口 |
| `vector/indexer.py` | 与 `vector/store.py` 职责重叠 | 合并进 `index/store.py` | 保留 `index_paper_abstracts` 别名 |
| `po/semantics.py`(740 行) | 定义 + 推理规则混在一起 | 拆 `ontology/export.py` + `graph/derive.py` | 拆完跑 335 测试 |
| `po/keywords.py` + `po/taxonomy.py` | 关键词表与分类器分家 | 合并进 `ontology/keywords.py` | 保留 `classify` 导出 |
| `Assertion` / `Objective` 概念类 | 0 / 1 实例 | 迁移后删 | 38→25 类数据迁移完成 |
| `capfactory/__pycache__` 等 | 字节码缓存 | 可随时清 | 无 |

> **为什么不盲删**：项目大量使用相对 import（`from .x import` / `from ..po import`），
> 用绝对 import 做依赖分析会把几乎所有模块误判为「0 引用」。
> 删除前必须：① `python3 -m unittest discover -s tests` 全绿；
> ② `deploy/smoke_test.py` 45/45；③ 检查 Web 路由与该模块的 `__init__` 导出。

---

## 6. 新增模块怎么用

### 6.1 读 schema（新代码统一入口）

```python
from capfactory.ontology import (
    V2_CLASSES, LAYER_CLASSES, V2_RELATIONS,       # 25 类 / 46 关系
    APPLICATION_LINKS, CODE_LINKS, EXTRACTION_PROTOCOL,
    CONCEPT_SPECS, default_registry,               # V1 兼容（读旧图）
)
```

字段三态：`Field(source="extracted|derived|inherited", level="must_have|should_have|optional")`。
**规则**：LLM 只填 extracted；derived 由规则回填；inherited 从父继承。

### 6.2 跑 V2 端到端试点

```python
from capfactory.ontology.instantiate import (
    extract_v2, build_v2_graph, bind_code, link_v2, report,
)
from capfactory.llm.backends import chat
from capfactory.po import POGraph

raw = extract_v2(text, chat_fn=lambda p: chat(p, backend="vllm", max_tokens=8000))
g, st = build_v2_graph(raw, doc_id="2102.09844")
code = bind_code(g, repo_path)            # AST，不执行代码
link = link_v2(g, POGraph.load("storage_cf/po/report_graph.json"))
print(report(g, extract=st, code=code, link=link))
```

产物：`storage_cf/ontology/egnn_v2.json` / `egnn_raw.json` / `egnn_report.json`。

### 6.3 统一 JSON / 后端

```python
from capfactory.utils import parse_llm_json
from capfactory.llm.backends import chat, BACKENDS
text = chat(prompt, backend="vllm", max_tokens=32768)
data = parse_llm_json(text) or {}
```

---

## 7. 迁移顺序（四阶段，每阶段都要全绿）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **0（已完成）** | 统一入口、4 处转发、V2 定义、单篇试点 | 335 tests、45 冒烟 |
| **1** | `Observation` 可比字段改 `inherited`，重跑 `benchmark.py` 对比 SOTA | 备份 `sota.md`，新旧 `group_key` 差异可解释 |
| **2** | 抽取 prompt 加 Composition/DataForm 必抽；按 Results 小节逐节抽 | 孤立节点率 < 20%、指标覆盖 3 个实验 |
| **3** | CAD 双图 + grounding 实例化（`CausalGraph` / `GroundingAlignment`） | 至少 1 篇论文有 paper/code 两套推理图 |
| **4** | 38→25 类数据迁移 + 双写边/字段；确认无引用后删 legacy | 旧图可只读回放、Web 全绿 |

---

## 8. 关键数据文件

| 路径 | 内容 |
|---|---|
| `storage_cf/po/report_graph.json` | V1 主图（786 节点 / 1531 断言，0 违规） |
| `storage_cf/po/batch_qwen38.json` | qwen38 抽取的 10 篇 V1 图 |
| `storage_cf/ontology/egnn_v2.json` | ★ V2 试点图（60 节点 / 60 断言） |
| `data/docx/*.md` | 783 篇论文的 Markdown（单栏 529 / 双栏 244） |
| `data/repos/src/*` | 90 个已下载代码仓库 |
| `storage_cf/vector3|4|5/docs` | 各版多向量库 |

---

## 9. 验证命令（每次改完必跑）

```bash
python3 -m unittest discover -s tests          # 660 tests
python3 -m compileall -q capfactory
python3 deploy/smoke_test.py --base-url http://127.0.0.1:8090   # 45/45
python3 -c "from capfactory.ontology import layers_summary; print(layers_summary())"
```

外部依赖：Ollama(11434, bge-m3/qwen3.5)、vLLM(8000, Qwen3.8-27B)、
docker `mineru-api`(8886, GPU 1)、OpenRouter（VL 图注，免费）。
任一不可用时按 `llm/backends.py` 的 `AUTO_ORDER` 降级。

抽取链路的代码级说明见 [md/EXTRACTION_OVERVIEW.md](md/EXTRACTION_OVERVIEW.md)。

应用层任务化与前端导入审视见 [md/APPLICATION_TASK_LAYERS.md](md/APPLICATION_TASK_LAYERS.md)。

语义层逐类逐字段与关系详解见 [md/SEMANTIC_LAYER_ARCHITECTURE.md](md/SEMANTIC_LAYER_ARCHITECTURE.md)。
