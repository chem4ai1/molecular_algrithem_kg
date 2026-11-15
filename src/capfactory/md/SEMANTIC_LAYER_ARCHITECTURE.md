# 语义层架构详解（v4.1 · 6 类 / 9 关系）

> 2026-11-14。本文是**语义层的权威说明**：逐类、逐字段、逐关系给出定义、
> 级别、来源、真实填充率与实例。代码定义在 `capfactory/semantic/tbox_v4.py`
> （`SEMANTIC_CLASSES` / `SEMANTIC_RELATIONS` / `REMOVED_CLASS_MAP`），
> 抽取契约在 `semantic/extraction/contracts.py`（`NON_LLM` 标记规则字段）。
> 图文件：`storage_cf/sciforge/batch10_semantic_v4.json`（6001 节点 / 7460 断言）。

## 0. 定位与边界

语义层只回答一件事：**这篇论文客观提出了什么、在什么数据集上评测出什么数值**。
它不承载任务视图，也不承载推断。

| 属于语义层 | 不属于语义层 |
|---|---|
| 论文、算法、算法模块、代码仓库、代码函数、基准 | 榜单行、指标定义、证据节点、局限节点、研究问题节点 |
| 论文提出算法、论文评测基准、模块由函数实现 | 复现计划、生成大纲、章节素材 |
| 表格里的原始数值行 | 跨论文归一后的 SOTA 结论 |

被移出的 9 个类各有落点：属性化（`Paper.research_question`、`Benchmark.metrics[]`、
`Benchmark.model_results[]`）或上移应用层（`LeaderboardEntry` / `Evidence` /
`Limitation` / `DataSource`），映射表见 `REMOVED_CLASS_MAP`，
应用层见 `md/APPLICATION_TASK_LAYERS.md`。

## 1. 架构总览

```
                 ┌──────────── 论文层 ────────────┐
                 │  Paper (808)                   │
                 └──┬───────────┬──────────┬──────┘
        PROPOSES_METHOD  HAS_CODE      EVALUATED_ON
                    │           │          │
        ┌───────────▼──┐  ┌─────▼───────┐  │   ┌────────────┐
        │ Algorithm    │  │CodeRepository│  └──►│ Benchmark  │
        │ (1674)       │  │ (10)        │      │ (604)      │
        └──┬───────────┘  └─────┬───────┘      └────────────┘
   HAS_MODULE                 HAS_FUNCTION            ▲
           │                       │                  │ EVALUATED_ON
   ┌───────▼────────┐      ┌───────▼───────┐          │ (Algorithm→)
   │AlgorithmModule │      │ CodeFunction  │──────────┘
   │ (2856)         │◄─────│ (49)          │
   └────────────────┘ MODULE_IMPLEMENTED_BY
        ▲
        └── SUBCLASS_OF（Algorithm 之间，1083 条）
```

**9 条关系**（实际条数）：

| 关系 | 域 → 值域 | 条数 | 用途 |
|---|---|---:|---|
| `PROPOSES_METHOD` | Paper → Algorithm | 1666 | 论文提出算法（核心归属） |
| `HAS_CODE` | Paper → CodeRepository | 10 | 论文关联代码仓库 |
| `EVALUATED_ON` | Paper\|Algorithm → Benchmark | 984（875+109） | 在哪个基准上评测 |
| `HAS_MODULE` | Algorithm → AlgorithmModule | 2862 | 算法由哪些模块构成 |
| `MODULE_IMPLEMENTED_BY` | AlgorithmModule → CodeFunction | 758 | 模块由哪个函数实现 |
| `HAS_FUNCTION` | CodeRepository → CodeFunction | 49 | 仓库包含函数 |
| `BELONGS_TO_MODULE` | CodeFunction → AlgorithmModule | **0** | 反向关系（当前未使用） |
| `RELATED_TO` | Paper → Paper\|Algorithm | 48（26+22） | 相关文献/方法线索 |
| `SUBCLASS_OF` | Algorithm → Algorithm | 1083 | 算法继承/改进（带 kind） |

## 2. 命名与 ID 规则

| 对象 | 规则 | 示例 |
|---|---|---|
| Paper | `paper:<arxiv_id>`；proxy 为 `paper:src:<host>:<slug>` | `paper:2411.06608` |
| Algorithm | `algorithm:<slug(名称)>` | `algorithm:molminer` |
| AlgorithmModule | `algorithmmodule:<arxiv_id>:<slug(模块名)>` | `algorithmmodule:2411.06608:symmetry_aware_attachment_standardization` |
| CodeRepository | `coderepository:<slug(owner__repo)>` | `coderepository:raulorteg_molminer` |
| CodeFunction | `codefunction:<repo_slug>:<file_slug>:<func>` | `codefunction:raulorteg_molminer:molminer_processor_py:get_all_possible_attachments` |
| Benchmark | `benchmark:<slug(名称)>`；预置库为 `benchmark:kb:<slug>`；表格临时为 `benchmark:table:<n>` | `benchmark:zinc` / `benchmark:kb:qm9` |

`label` 是显示名，`attrs.name` 是规范化名；两者在 Algorithm / Benchmark /
CodeFunction 上通常一致，但 `label` 可能被截断到 90 字。

---

## 3. 类详解

### 3.1 Paper（论文）· 808 个

**定义**：一篇论文的客观载体。核心是「研究什么问题」与「属于哪个领域」，
其余元数据由文件名/CSV 决定。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `title` | must | 规则（md 首行） | 100% | 论文标题 |
| `arxiv_id` | should | 规则（文件名） | 100% | arXiv 标识，等于 id 尾段 |
| `doi` | optional | 规则 | 0% | DOI（当前未解析） |
| `year` | optional | 规则 | 0.2% | 年份（仅 2 篇） |
| `venue` | optional | 规则 | 0% | 发表场所（当前未解析） |
| `research_question` | should | **LLM**（E1） | 100% | 一句话说清研究什么问题 |
| `problem_category` | should | **LLM**（E1）+ 词表校验 | 97% | 问题类别（复用算法库 `TASK_TYPES` 12 类） |
| `domain` | should | **规则**（`domain_code` → 中文） | 100% | 所属领域（11 个 D 码） |
| `flow_family` | should | **规则**（由算法族反查） | 4% | 和什么方向的方法比较（中文标签） |
| `why_hard` | optional | **LLM**（E1） | 99.9% | 现有方法的瓶颈 |
| `keywords` | optional | **规则**（词频×IDF） | 100% | 关键词 3–8 个 |
| `relation_hints` | optional | **LLM**（E1） | 100% | 关系线索（相关论文/算法/基准名） |

**关系**：出边 `PROPOSES_METHOD` / `HAS_CODE` / `EVALUATED_ON` / `RELATED_TO`；
入边仅 `EVALUATED_ON`（外部线索）与 `RELATED_TO`（被引）。

**真实实例** `paper:2411.06608`：

```json
{"title": "MolMiner: Towards Controllable, 3D-Aware, Fragment-Based Molecular Design",
 "arxiv_id": "2411.06608",
 "research_question": "提出MolMiner，一种基于片段、几何感知且顺序无关的自回归模型，支持对12个理化性质的高维条件控制分子设计。",
 "problem_category": "molecule_generation",
 "domain": "分子生成与从头设计",
 "flow_family": "片段/结构化生成",
 "why_hard": "现有自回归模型通常依赖固定展开顺序，且很少有框架在生成过程中整合动态几何信息，导致泛化能力受限。",
 "keywords": ["molminer", "d-aware", "fragment-based", ...],
 "relation_hints": {"related_papers": ["JTNN","HierVAE","G-SchNet","MoLeR"], "algorithms": ["MolMiner"], "benchmarks": ["Conditional Generation"]}}
```

出边：`HAS_CODE → raulorteg__molminer`、`PROPOSES_METHOD → MolMiner`、
`EVALUATED_ON → ZINC`、`RELATED_TO → ChemicalVAE / SchNet`。

> **未声明但存在的属性**：`domain_code`（783 个，供规则校准与领域回填）、
> `name`（36 个，迁移遗留）。前者是刻意保留的内部锚点，后者应清理。

### 3.2 Algorithm（算法）· 1674 个

**定义**：论文提出的方法，或作为基线被反复引用的方法（谱系补建）。
核心是「机理」与「能解决什么问题」。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `name` | must | **LLM**（E2） | 100% | 算法名，也是 id 来源 |
| `task_type` | should | **LLM**（E2）+ 词表 | 44% | 任务类型（12 类） |
| `flow_family` | should | **规则**（18 族枚举） | 2% | 算法族（英文 id，如 `fragment`） |
| `problems_solved` | should | **LLM**（E2） | 44% | 能解决什么问题（列表） |
| `mechanism` | should | **LLM**（E2） | 46% | 机理一句话 |
| `why_it_works` | optional | **LLM**（E2） | 44% | 为什么有效 |
| `applicable_to` | optional | **LLM**（E2） | 44% | 适用场景（列表） |
| `limitations` | optional | **LLM**（E2） | 26% | 局限（文本，不建节点） |

**关系**：出边 `HAS_MODULE`（2862）、`EVALUATED_ON`（109）、`SUBCLASS_OF`（1083）；
入边 `PROPOSES_METHOD`（1666）、`RELATED_TO`（22）、`SUBCLASS_OF`。

**真实实例** `algorithm:molminer`：

```json
{"name": "MolMiner",
 "task_type": "molecule_generation",
 "flow_family": "fragment",
 "problems_solved": ["生成具有特定属性的分子", "通过自回归方式构建分子结构"],
 "mechanism": "属性条件自回归模型，通过中间解码状态支持顺序轨迹发散，形成从粗到细的边界。",
 "why_it_works": "固定随机带时保持化学凝聚的局部邻域，中间状态允许逐步细化分子身份。",
 "applicable_to": ["分子生成", "潜在空间导航分析"],
 "limitations": ["随机带变化时身份持久性未明确对比GDSS，但文中指出其保留局部化学凝聚"]}
```

出边：`HAS_MODULE → Symmetry-Aware Attachment Standardization / Geometry-Biased Attention /
Fragment Starter / Order-Agnostic Autoregressive Rollout`、`EVALUATED_ON → ZINC`。
入边：**2 条** `PROPOSES_METHOD`（来自 MolMiner 原文 + 另一篇引用它的论文）。

> **同名合并**：`_find` 按名称归一，跨论文同名算法会复用同一节点，
> 因此一个 Algorithm 可能有多个 `PROPOSES_METHOD` 父论文。
> 这是刻意的实体规范化，但也意味着无法区分「本文提出的 X」与「引用的 X」；
> `origin`（912 个，谱系补建标记）与 `paper_id`（912 个）可辅助判断。

### 3.3 AlgorithmModule（算法模块）· 2856 个

**定义**：算法的组成单元。命名沿用旧 TBox 的 `AlgorithmStep`，
刻意承载「接收什么 → 产生什么」的信息流，是模块追踪的落点。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `name` | must | **LLM**（E2） | 100% | 模块名 |
| `mechanism` | should | **LLM**（E2） | 100% | 该模块做什么 |
| `formula` | optional | **LLM**（E2） | 29% | 公式/方程（文本，不建节点） |
| `inputs` | should | **LLM**（E2） | 100% | 输入 |
| `outputs` | should | **LLM**（E2） | 100% | 输出 |

**关系**：出边 `MODULE_IMPLEMENTED_BY`（758）；入边 `HAS_MODULE`（2862）。

**真实实例**（MolMiner 的一个模块）：

```
algorithmmodule:2411.06608:symmetry_aware_attachment_standardization
  name      = Symmetry-Aware Attachment Standardization
  mechanism = 标准化片段连接点，使同一片段的多种连接方式归一到唯一表示
  inputs    = 片段集合及其原子索引映射
  outputs   = 片段原子环境及索引映射
  formula   = （空）
  出边      = MODULE_IMPLEMENTED_BY → _get_all_possible_attachments（CodeFunction）
```

> 语义层只存**静态结构**（模块名/机理/输入输出）。
> 「step_order / depends_on / data_flow」这类顺序与信息流属于**抽取期范式层的
> 派生结果**（写在 `semantic_extraction/<aid>.json` 的 `paradigm.modules`），
> 不回写图，避免把推断当事实。

### 3.4 CodeRepository（代码仓库）· 10 个

**定义**：论文对应或引用的代码仓库。全部由规则/AST 填充，**不允许 LLM 抽**。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `repo_name` | must | 规则（目录名） | 100% | 仓库名 `owner__repo` |
| `repo_url` | should | 规则（原文 GitHub URL） | 90% | 远程地址 |
| `local_path` | optional | 规则（本地克隆路径） | 100% | 本地路径 |
| `license` | optional | 规则（LICENSE 文件） | 90% | 许可证 |
| `is_original_repo` | should | 规则（作者署名匹配） | 100% | 是否作者原仓库 |

**关系**：出边 `HAS_FUNCTION`（49）；入边 `HAS_CODE`（10）。

**真实实例** `coderepository:raulorteg_molminer`：`repo_url=https://github.com/raulorteg/molminer`、
`license=Apache License`、`is_original_repo=true`、
出边 49 条 `HAS_FUNCTION`。

### 3.5 CodeFunction（代码函数）· 49 个

**定义**：模块的实现证据。**全部字段来自 AST**，`contracts.NON_LLM` 明确排除 LLM。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `name` | must | AST | 100% | 函数名 |
| `purpose` | should | AST（docstring 首句/启发式） | 100% | 作用 |
| `comment` | optional | AST（docstring） | 69% | 注释/文档 |
| `params` | optional | AST（参数列表） | 78% | 参数 |
| `returns` | optional | AST（返回注解） | 29% | 返回值 |
| `func_type` | should | AST（`_ast_func_type`） | 100% | generator / forward / init / loss / io / transform / accessor… |

**关系**：入边 `HAS_FUNCTION`（49）、`MODULE_IMPLEMENTED_BY`（758）；
出边 `BELONGS_TO_MODULE`（0，未使用）。

**真实实例** `codefunction:raulorteg_molminer:molminer_processor_py:get_all_possible_attachments`：

```
name      = _get_all_possible_attachments
params    = self, canonical_smiles, isring
purpose   = Compute all possible attachment points for a grain
comment   = Compute all possible attachment points for a grain. Parameters ---------- ...
returns   = List[List[int]]
func_type = accessor
lineno    = 68          （未声明属性，AST 原始行号）
入边      = MODULE_IMPLEMENTED_BY ← Symmetry-Aware Attachment Standardization,
            HAS_FUNCTION ← raulorteg__molminer
```

> `comment` 只有 69% 是**源码本身**只有这么多 docstring，不是抽取失败。

### 3.6 Benchmark（评测基准/数据集）· 604 个

**定义**：评测所用的数据集/任务设定 + 其上的数值。结构由 LLM 抽，
数值**只允许表格/AST 填**（`NON_LLM`）。

| 字段 | 级别 | 来源 | 填充率 | 含义 |
|---|---|---|---|---|
| `name` | must | **LLM**（E3） | 100% | 基准名 |
| `input_form` | should | **LLM**（E3）+ 词表 | 100% | 输入形式（SMILES/3D坐标/向量/图/序列…） |
| `output_form` | should | **LLM**（E3）+ 词表 | 100% | 输出形式 |
| `n_samples` | should | **LLM**（E3） | 51% | 样本量（如 `1000M`） |
| `scale` | optional | **LLM**（E3） | 48% | 规模档位 |
| `modality` | optional | **LLM**（E3） | 97% | 数据模态（molecule/protein…） |
| `research_object` | optional | **LLM**（E3） | 100% | 研究对象（ligand/pocket…） |
| `metrics` | should | **LLM**（E3） | 71% | 指标列表 `[{name,unit,direction,sota_model,sota_value}]` |
| `model_results` | should | **规则**（表格 E4） | 25% | 数值行 `[{model,metric,value,unit,is_sota,paper_id,provenance}]` |
| `sota_by_metric` | optional | **规则**（动态 SOTA 重算） | 3% | 每指标当前最优 |
| `is_evaluation` | should | **规则**（是否有数值） | 11% | 是否真正的评测基准 |

**关系**：入边 `EVALUATED_ON`（984）。

**真实实例** `benchmark:zinc`：

```json
{"name": "ZINC", "input_form": "SMILES", "output_form": "SMILES",
 "n_samples": "1000M", "scale": "1000M pairs",
 "modality": "molecule", "research_object": "ligand",
 "metrics": [{"name":"validity","unit":"","direction":"max"},
             {"name":"novelty","unit":"","direction":"max"}],
 "model_results": [{"model":"GDSS","metric":"uniqueness","value":"99.6",
                    "unit":"","is_sota":false,"paper_id":"paper:2411.06608",
                    "provenance":"table_extract:1"}, ... 共 155 行],
 "sota_by_metric": {"uniqueness": {"model":"HierVAE","value":"100.0","numeric":100.0, ...}}}
```

入边：5 条 `EVALUATED_ON`（MolMiner 原文、MolMiner 算法本身、NeVAE、
GCPN、一篇材料学论文）—— 同一个基准被多篇论文评测，才会形成可更新榜单。

---

## 4. 关系详解

每条形如 `source -RELATION-> target`，可带属性（`kind` / `evidence` / `paper_id` /
`layer` / `task`）。`layer="semantic"` 表示语义层事实，`layer="application"`
表示任务层派生。

### 4.1 `PROPOSES_METHOD` · Paper → Algorithm · 1666 条

- **含义**：这篇论文提出（或首次系统描述）了这个算法。
- **基数**：1 Paper → 1..N Algorithm；1 Algorithm ← 1..N Paper（同名合并时多父）。
- **属性**：`paper_id`（回填时写入）。
- **约束**：`check_domain_range("Paper","PROPOSES_METHOD","Algorithm")` 必须通过。
- **示例**：`paper:2411.06608 -PROPOSES_METHOD-> algorithm:molminer`。
- **用途**：论文库「方法」分组、算法库溯源、`repair()` 自动补边。

### 4.2 `HAS_CODE` · Paper → CodeRepository · 10 条

- **含义**：论文关联的代码仓库。
- **基数**：1 Paper → 0..N Repository。
- **属性**：`is_original_repo` 体现在节点上，不在边上。
- **示例**：`paper:2411.06608 -HAS_CODE-> coderepository:raulorteg_molminer`。
- **坑**：只有 10 条 —— 783 篇里绝大多数论文没给可克隆仓库，不是抽取漏，是数据现实。

### 4.3 `EVALUATED_ON` · Paper|Algorithm → Benchmark · 984 条（875 + 109）

- **含义**：在哪个基准上评测。复合域：论文级（整篇在 ZINC 上评）与算法级
  （某个算法在 ZINC 上评）都允许。
- **基数**：N:N（同一基准被多篇论文评测，是动态 SOTA 的前提）。
- **示例**：`paper:2411.06608 -EVALUATED_ON-> benchmark:zinc`、
  `algorithm:molminer -EVALUATED_ON-> benchmark:zinc`。
- **用途**：数据树的「评测」分组、榜单页 `Benchmark -HAS_ENTRY-> 行`（应用层）。

### 4.4 `HAS_MODULE` · Algorithm → AlgorithmModule · 2862 条

- **含义**：算法由哪些模块构成。
- **基数**：1 Algorithm → 1..N Module；Module 只属于一个算法（id 含 arxiv_id）。
- **约束**：`check_domain_range("Algorithm","HAS_MODULE","AlgorithmModule")`。
- **示例**：`algorithm:molminer -HAS_MODULE-> algorithmmodule:2411.06608:fragment_starter`。

### 4.5 `MODULE_IMPLEMENTED_BY` · AlgorithmModule → CodeFunction · 758 条

- **含义**：模块由哪个真实函数实现（代码联系的核心边）。
- **来源**：E2 的 `code_symbols` 与 AST `CodeFunction` 名称对齐，命中才建边；
  未命中记入 `apply_one` 的 `gaps`，**不硬造**。
- **示例**：`algorithmmodule:2411.06608:symmetry_aware_attachment_standardization
  -MODULE_IMPLEMENTED_BY-> codefunction:...:_get_all_possible_attachments`。
- **坑**：跨语言/改名/装饰器包装会失配，758/2862 ≈ 26% 的模块有实现证据。

### 4.6 `HAS_FUNCTION` · CodeRepository → CodeFunction · 49 条

- **含义**：仓库包含哪些函数（AST 解析结果）。
- **基数**：1 Repository → N Function。
- **示例**：`coderepository:raulorteg_molminer -HAS_FUNCTION-> codefunction:...:forward`。

### 4.7 `BELONGS_TO_MODULE` · CodeFunction → AlgorithmModule · **0 条**

- **含义**：函数所属模块（`MODULE_IMPLEMENTED_BY` 的反向）。
- **状态**：TBox 已声明，但**当前没有任何写入方**。查询时请用
  `MODULE_IMPLEMENTED_BY` 的 `incoming()`，不要依赖此边。
- **去留**：下一轮精简可删除，或由 `apply.py` 在建正向边时同步写反向。

### 4.8 `RELATED_TO` · Paper → Paper|Algorithm · 48 条（26 + 22）

- **含义**：**线索边**，不是严格学术引用。来自 E1 的 `relation_hints`，
  经 `source_resolution` 解析成真实节点或 proxy 占位。
- **基数**：N:N。
- **示例**：`paper:2411.06608 -RELATED_TO-> paper:1802.04364`（JTNN）、
  `paper:2411.06608 -RELATED_TO-> algorithm:chemicalvae`。
- **坑**：proxy 节点（`paper:src:<host>:<slug>`）只为让链可跳转，
  `domain="unknown"`，不要当成正式论文统计。

### 4.9 `SUBCLASS_OF` · Algorithm → Algorithm → 1083 条

- **含义**：算法继承/改进关系（科技树骨架）。
- **属性**：
  - `kind`：`extends` / `replaces` / `improves`（`compared_with` 只作线索不建边）
  - `evidence`：逐字引文（E6 抽取，`_norm_evidence` 校验）
  - `paper_id`：来源论文
  - `layer="semantic"`
- **幂等**：`apply_all` 重跑时先清掉所有带 `paper_id` 的 `SUBCLASS_OF` 再重建。
- **示例**：`algorithm:molminer -SUBCLASS_OF(extends)-> algorithm:jtnn`。
- **坑**：谱系边是**算法级**，不是论文级；`paper-论文` 的引用链走 `RELATED_TO`。

---

## 5. 一条完整链路（MolMiner）

```
Paper paper:2411.06608
  ├─ PROPOSES_METHOD → Algorithm algorithm:molminer
  │     ├─ HAS_MODULE → AlgorithmModule ...:fragment_starter
  │     │                → ...:symmetry_aware_attachment_standardization
  │     │                     └─ MODULE_IMPLEMENTED_BY → CodeFunction
  │     │                          codefunction:...:_get_all_possible_attachments
  │     ├─ EVALUATED_ON → Benchmark benchmark:zinc
  │     │                 └─ model_results[155 行]  (provenance=table_extract:1)
  │     └─ SUBCLASS_OF(extends) → algorithm:jtnn / algorithm:hiervae
  ├─ HAS_CODE → CodeRepository coderepository:raulorteg_molminer
  │              └─ HAS_FUNCTION → 49 个 CodeFunction
  ├─ EVALUATED_ON → ZINC
  └─ RELATED_TO → paper:1802.04364(JTNN) / algorithm:chemicalvae / ...
```

这条链同时覆盖「论文 → 算法 → 模块 → 函数」的实现链与
「论文 → 基准 → 数值」的评测链，是语义层设计目标的最小完整样例。

---

## 6. 与 legacy TBox 的映射（被删 9 类）

| legacy 类 | 语义层落点 | 应用层对应 |
|---|---|---|
| `ResearchQuestion` | `Paper.research_question`（字符串） | `ResearchQuestion` 节点（写作任务） |
| `ProblemCategory` | `Paper.problem_category`（枚举） | `ProblemCategory` 节点（聚类） |
| `MetricDefinition` | `Benchmark.metrics[]`（数组） | `MetricDefinition` 节点 |
| `LeaderboardEntry` | `Benchmark.model_results[]`（数组） | `LeaderboardEntry` 节点（复现任务） |
| `DataContract` | `Benchmark` 的 input/output/规模字段 | `DataContract` 节点 |
| `Evidence` | 数值行与节点的溯源字段（`paper_id` / `provenance`） | `Evidence` 节点 |
| `Limitation` | `Algorithm.limitations`（文本） | `Limitation` 节点 |
| `SourcePaper` | 不建节点，用 `Paper -RELATED_TO-> Paper` | `SourcePaper` 节点 |
| `AlgorithmStep` | **改名** `AlgorithmModule`（同一概念） | — |

判断标准：**能被一句话说清且不需要独立查询的，降为属性**；
**需要按任务聚合/过滤的，上移应用层**。

## 7. 数据质量与已知偏差

这些是真实数据状态，不是设计目标，读图时必须知道：

| 项 | 现象 | 影响 / 处理 |
|---|---|---|
| `Algorithm.flow_family` 仅 2% | 34/1674（多为谱系补建节点） | `Paper.flow_family` 靠它反查，因此只有 4% |
| `Paper.flow_family` 是中文标签，`Algorithm.flow_family` 是英文 id | 「片段/结构化生成」vs `fragment` | 展示层各取所需；不要直接等值比较 |
| `Paper.doi / year / venue` 近 0 | 文件名与 CSV 未解析这三项 | 需要时补 `fill_metadata`，当前不影响主链 |
| `Benchmark.model_results` 25% | 152/604 有数值 | 多数基准只被提及未给表；`is_evaluation` 11% 可辅助筛选 |
| `Benchmark.sota_by_metric` 3% | 只有多论文评测的基准才重算 | 正常，单论文基准无「SOTA」概念 |
| `BELONGS_TO_MODULE` 0 条 | 声明但无写入方 | 查询请用 `MODULE_IMPLEMENTED_BY` 反向 |
| 同名 Algorithm 合并 | 1 个节点可能有 2+ `PROPOSES_METHOD` 父论文 | 用 `origin` / `paper_id` 辅助区分 |
| 未声明属性 | `Paper.domain_code`(783)、`Algorithm.origin`(912)、`CodeFunction.lineno/module_path`(49)、`Paper.name`(36)、`CodeRepository.name`(10) | `domain_code` 是内部锚点（保留）；`name` 重复键应清理；`lineno` 建议补进 TBox |
| proxy Paper | `paper:src:*`，`domain="unknown"` | 只为链可跳转，统计时排除 |

## 8. 维护入口

```bash
# 结构定义
capfactory/semantic/tbox_v4.py            # SEMANTIC_CLASSES / SEMANTIC_RELATIONS / REMOVED_CLASS_MAP
capfactory/semantic/extraction/contracts.py  # NON_LLM（规则字段）/ E_CONTRACTS / 阶段契约

# 写图
capfactory/semantic/apply.py::apply_all   # E1–E6 回填（含代码联系、谱系边）
capfactory/semantic/enrich.py             # repo_url/license/keywords/SUBCLASS_OF
capfactory/applayer/builder.py            # 应用层任务层（不写语义层）

# 读图 / 审计
capfactory/semantic/provenance.py::trace / audit / repair
capfactory/semantic/refresh.py::refresh_all   # 溯源修复→索引→CSV→关系→向量→快照

# 命令
.venv-linux/bin/python -c "from capfactory.semantic.tbox_v4 import snapshot; \
  print(snapshot())"                     # 类/关系计数
.venv-linux/bin/python -m capfactory.semantic.batch_extract --status
```

**新增一个字段的完整流程**：`tbox_v4.SEMANTIC_CLASSES` 加字段（定级别）→
若是 LLM 字段则在 `prompts.PROMPTS` 对应阶段加 → `validator` 加校验/词表 →
`apply.py` 写入 → `docs`/本文档同步 → 跑 `refresh_all` 与回归。

**新增一类或一条关系**：先问三件事 —— 是否一句话可表述（→ 属性）、
是否需要任务聚合（→ 应用层）、是否必须跨论文查询（→ 才进语义层）。
三者都不成立就不要加类。

## 9. 相关文档

- `md/EXTRACTION_OVERVIEW.md` — 抽取链路代码级说明
- `md/APPLICATION_TASK_LAYERS.md` — 复现/生成两种任务的应用层
- `md/TBOX_INVENTORY.md` — 全量 TBox 清点与精简方案
- `docs/PROVENANCE_AND_VECTOR_AUDIT.md` — 溯源与向量索引
