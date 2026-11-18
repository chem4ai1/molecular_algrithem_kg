# 语义层当前架构（v4.2 · 2026-11-18）

> 权威来源：`src/capfactory/semantic/tbox_v4.py`（定义）+ `storage_cf/sciforge/batch10_semantic_v4.json`（实测）。
> 本文件由 `docs/schema/` 维护；旧版 `src/capfactory/md/SEMANTIC_LAYER_ARCHITECTURE.md` 为历史版本。

## 1. 一句话定位

**语义层 = 从论文里解析出的、可被任何后续任务反复复用的客观事实。**
只放「别人写了什么」，不放「本次生成决定做什么」（那是应用层）。

```
783 篇论文 md/PDF  ──E1–E6 抽取──▶  语义层 6 类 / 9 关系
                                      │
                                      ├─▶ 应用层 global 挖掘（13 个挖掘器）
                                      └─▶ 应用层 task 实例（WritingContext）
```

## 2. 规模总览

```
节点 7,755  ·  断言 9,885
Paper 808 · Algorithm 1,728 · AlgorithmModule 4,356
CodeRepository 10 · CodeFunction 49 · Benchmark 804
```

## 3. 六个类

### 3.1 Paper（808 实例 · 28 字段）

| 组 | 字段（覆盖率） |
|---|---|
| 身份与检索 | `title` 100% · `arxiv_id` 100% · `authors` 96.9% · `abstract` 96.9% · `doi` 20.4% · `venue` 96.9% · `year` 97% · `keywords` 100% · `references` 1.2% |
| 问题定义 | `research_question` 100% · `problem_category` 96.9% · `why_hard` 100% · `domain` 100% · `flow_family` 4.5% · `relation_hints` 100% |
| 方法论判定 | `paradigm` 95.8% · `evidence_type` 95.8% · `evidence_norm` 86.3% · `citation_style` 95.8% · `writing_style` 95.8% |
| 贡献与前沿 | `claims` 95.7% · `gaps` 95.7% · `open_problems` 31.9% · `delta_claims` 89.4% · `negative_results` 11.3% |
| 实验与写作 | `protocol_disclosure` 21.7% · `figures` 0% · `section_map` 95.5% |

**要点**：`open_problems` / `negative_results` / `protocol_disclosure` 低覆盖是**原文罕见**，不是抽取失败——论文很少明确写「未解决问题」「阴性结果」「协议声明」。

### 3.2 Algorithm（1,728 实例 · 10 字段）

```
name 100% · task_type 48.4% · flow_family 2% · problems_solved 48.4%
mechanism 49.3% · why_it_works 48.4% · applicable_to 48.4%
limitations 34.5% · assumptions 0% · novelty_basis 0%
```

**要点**：约一半算法是「被引用实体」（只在文献中出现，未抽方法），所以 mechanism 类字段 48% 是正常的。
`assumptions` / `novelty_basis` 为 0% 是新增字段尚未回填（E2 重抽排期中）。

### 3.3 AlgorithmModule（4,356 实例 · 7 字段）

```
name 100% · mechanism 100% · inputs 100% · outputs 100%
formula 27.8% · is_novel_component 55.1% · component_role 72.8%
```

**要点**：与前身的 `AlgorithmStep` 相比，新增 `is_novel_component` / `component_role` 让消融规划可枚举。
平均每个算法 4 个模块；模块 id 按论文隔离（`algorithmmodule:<aid>:<slug>`），同名不合并。

### 3.4 CodeRepository（10 · 5 字段）/ CodeFunction（49 · 6 字段）

```
Repo:  repo_name 100% · repo_url 90% · local_path 100% · license 90% · is_original_repo 100%
Func:  name 100% · purpose 100% · func_type 100% · params 77.6% · comment 69.4% · returns 28.6%
```

**要点**：代码证据极稀——只有 10 个仓库、49 个函数。`MODULE_IMPLEMENTED_BY` 只覆盖约 1/4 模块。

### 3.5 Benchmark（804 实例 · 13 字段）

```
name 100% · input_form 100% · output_form 100% · research_object 100%
modality 97.5% · protocol 81.3% · metrics 76.5%
n_samples 44.7% · scale 43.5%
model_results 19.9% · sota_by_metric 10.6% · is_evaluation 8.1%
failure_modes 0.1%
```

**要点**：`protocol` 回填效果好（81.3%），`model_results` 只有 19.9%——数值证据最薄弱，是阶段 07 素材装配的瓶颈。

## 4. 九条关系（实测条数）

| 关系 | Domain → Range | 条数 | 说明 |
|---|---|---:|---|
| `PROPOSES_METHOD` | Paper → Algorithm | 1,728 | 论文提出算法 |
| `HAS_CODE` | Paper → CodeRepository | 10 | 论文关联代码仓库 |
| `EVALUATED_ON` | Paper\|Algorithm → Benchmark | 1,219 | 在哪个基准上评测 |
| `HAS_MODULE` | Algorithm → AlgorithmModule | 4,402 | 算法由哪些模块构成 |
| `MODULE_IMPLEMENTED_BY` | AlgorithmModule → CodeFunction | 1,346 | 模块由哪个函数实现 |
| `HAS_FUNCTION` | CodeRepository → CodeFunction | 49 | 仓库包含函数 |
| `BELONGS_TO_MODULE` | CodeFunction → AlgorithmModule | **0** | ⚠️ 定义了但从未建边（死关系） |
| `RELATED_TO` | Paper → Paper\|Algorithm | **48** | ⚠️ 引用网络极稀疏 |
| `SUBCLASS_OF` | Algorithm → Algorithm | 1,083 | 算法继承/改进关系 |

**两个已知问题**：
- `BELONGS_TO_MODULE` 是死关系——要么补建反向边，要么从 tbox 删除
- `RELATED_TO` 仅 48 条，引用网络几乎为空；`Paper.references` 也只有 1.2%

## 5. 词表驱动（抽取的核心机制）

抽取不是让 LLM 自由生成枚举，而是**从受控词表选**：

```
BASE_VOCABS（13 组）  ──select(text, stage)──▶  top20 注入 prompt
                                                  │
                                    LLM 优先从词表选
                                    词表外 → "other" + proposed_new
                                                  │
                                    observe() → vocab.json 自动扩表
```

| 词表 | 项数 | 注入阶段 |
|---|---:|---|
| `task_type` / `problem_category` | 12 / 12 | E1 / E2 |
| `form` | 8 | E3 |
| `domain_code` | 11 | E1 |
| `flow_family` | 18 | E2 |
| `func_type` | 12 | E2（代码侧） |
| `paradigm` | 4 | E1 |
| `evidence_type` | 6 | E1 |
| `gap_type` | 5 | E1 / R6 |
| `component_role` | 6 | E2 |
| `outcome_class` / `arm_kind` | 2 / 4 | E3 / E4 |
| `claimed_strength` | 3 | R1 |

扩表状态：`storage_cf/sciforge/semantic_extraction/vocab.json` 含 `promoted` / `candidates` 两键。

## 6. 与应用层的边界

| 语义层（别人说过什么） | 应用层（我这次怎么做） |
|---|---|
| `Paper.claims[]` | `Claim` |
| `Paper.gaps[]` | `ResearchGap` |
| `Paper.negative_results[]` | `FalsificationRecord` |
| `Paper.protocol_disclosure[]` | `MethodLock` |
| `Paper.open_problems[]` | `Novelty` |
| `Benchmark.protocol` | `ExperimentArm` |
| `AlgorithmModule.is_novel_component` | `AblationLedger`（待建） |

详见 [`SEMANTIC_APPLICATION_SPLIT.md`](SEMANTIC_APPLICATION_SPLIT.md) §8。

## 7. 稳定性约束

| 约束 | 状态 |
|---|---|
| `stable_key()` 不含新增属性 | ✅ 保持 |
| 语义层仍是 6 类 / 9 关系 | ✅ 保持（H3 硬门） |
| 历史 `spec_hash` / `METHOD_LOCK` 有效性 | ✅ 不受影响 |
| 任务级节点不回流语义层 | ✅ `app_refine.json` 独立 |

## 8. 已知缺口与排期

| 缺口 | 状态 | 影响 |
|---|---|---|
| `Paper.figures` 0% | 待 E4 重抽 | 阶段 07 图表素材缺失 |
| `Algorithm.assumptions` / `novelty_basis` 0% | 待 E2 重抽 | Type II 泄露、新颖性判定 |
| `Benchmark.failure_modes` 0.1% | 待 E3 重抽 | 失败模式自检 |
| `Benchmark.model_results` 19.9% | 表格解析覆盖问题 | 数值证据薄弱 |
| `BELONGS_TO_MODULE` 0 条 | 死关系 | 反向查询不可用 |
| `RELATED_TO` 48 条 | 引用网稀疏 | 相关工作检索弱 |
