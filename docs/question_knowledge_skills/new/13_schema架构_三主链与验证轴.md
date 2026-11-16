# 13 · Schema 架构：三主链不变 + 一条验证轴（抽取版 v5）

> 回答的问题：E1–E6 从「禁令」改为「抽取」之后，语义层 schema 应该长什么样？
> 结论先行：**仍是 paper / algorithm / benchmark 三主链**，不新增第四条链；
> 增量是 2 个桥接节点（Contribution / ExperimentArm）+ 1 条纵向验证轴 + 一批属性/边属性。
> 本文档收敛 `04`（抽取层改动）、`11`（节点落点）、`12`（抽取位置）三份的结论。

---

## 13.0 先分清：禁令与抽取在架构里各占哪一层

上一版把「不许编造 seed、不许用 unit 承载方差」写成 prompt 禁令——那是**校验语义**，
schema 装不下它；这一版问「论文本身说了什么」——这才是 schema 的内容。

| | 上一版（禁令） | 这一版（抽取） |
|---|---|---|
| 性质 | 检查「有没有违规」 | 读出「论文说了什么」 |
| 落点 | `validator.py` + prompt 约束段（**不进 schema**） | schema 新字段（每条必须有原文锚点） |
| 能力 | 只能发现遗漏/违规 | 才能拿到事实 |
| 例子 | 不许编造 seed → 校验格式 | 问「几个 seed」→ `model_results[].seeds` + 定位器验收 |
| 例子 | 不许 unit 承载方差 | 问「± 值是什么」→ `value_note` 字段 |
| 例子 | 不许把表格多列拼成一个 value | 问「这行是主结果还是消融」→ `outcome_class` + `arm` |

关键联动：**加了字段之后禁令反而变强**。原来校验「unit 不是方差」只能查格式；
有了 `seeds` 字段 + `12` 的定位器，就能对照原文验证「这个 seed 数真的写在那句话里」。
检查与抽取不是替代关系，是分层关系。

---

## 13.1 为什么仍是三主链

**结论：保留。** 三个理由：

1. **E1–E6 的分工本身就是按证据源切的**，三主链正是这三类证据源在图里的形态：
   - E1（论文叙事）→ Paper 链
   - E2/E6（方法与谱系）→ Algorithm 链
   - E3/E4（实验与数值）→ Benchmark 链
   - E5（引用）→ Paper 链的 RELATED_TO 边
2. **新增的两个节点都不是新证据源，而是桥**：
   Contribution 桥接「叙事」与「验证」，ExperimentArm 桥接「叙事」与「数值」。
   桥的两端全部落在现有链上，不需要新的证据源类别。
3. **拉平成四条主链会产生归属歧义**：验证轴与实验链谁包含谁说不清；
   显式分层（横向三链 + 纵向一轴）没有这个问题。

## 13.2 架构图

```
① Paper 叙事链（E1/E5 落点）
   Paper ─PROPOSES_METHOD→ Algorithm
   Paper ─DECLARES→ Contribution              ← 新节点（E1 抽出）
   Paper ─RELATED_TO→ Paper|Algorithm         边属性 +context / cited_doi / cited_venue（E5 抽出）

② Algorithm 方法链（E2/E6 落点）
   Algorithm ─HAS_MODULE→ AlgorithmModule ─MODULE_IMPLEMENTED_BY→ CodeFunction
   Algorithm ─SUBCLASS_OF→ Algorithm(父)      边属性 +assumption_delta（E6 抽出）
   CodeRepository ─HAS_FUNCTION→ CodeFunction ←BELONGS_TO_MODULE─ AlgorithmModule

③ Benchmark 实验链（E3/E4 落点）
   Paper|Algorithm ─EVALUATED_ON→ Benchmark   边属性 +protocol{seeds,split,eval_script,epochs,hardware}（E3 抽出）

④ 验证轴（纵向，把三条链缝起来；E1→E3→E4 顺序产出）
   Paper ─RUNS→ ExperimentArm ─ON→ Benchmark
   Contribution ─TESTED_BY→ ExperimentArm
   Benchmark.model_results[].arm ──→ ExperimentArm（行级回指）
```

一句话：**横向三链回答「谁提出什么、怎么实现、在哪测出什么数」；
纵向验证轴回答「声称的贡献被哪组实验、以什么协议、在哪行数值上支撑」。**
后者正是「每条贡献是否有支撑」这一评分维度的图结构前提（`05` 的强制矩阵靠它逐组清点）。

---

## 13.3 TBox v5 增量定义（相对 v4.1：6 类/9 关系 → 8 类/13 关系）

### 新增类（2）

```python
# tbox_v5.py 增量

"Contribution": ("论文声称的贡献", (
    ("statement",        "must",     "一句话贡献（≤80 字）"),
    ("kind",             "should",   "method | data | analysis | system"),
    ("convincing_via",   "optional", "说服方式 proof | numbers | system | explanation"
                                     "（Paper.evidence_type 相同时可省）"),
    ("why_not_before",   "should",   "为什么以前没人做（数组，每条 ≤40 字，"
                                     "需覆盖 技术约束/理论盲点/数据可得性 中 ≥2 类）"),
    ("claimed_strength", "should",   "proven | supported | suggests（论文自己的措辞）"),
    ("section",          "optional", "出现在哪一节"),
    ("evidence",         "must",     "逐字句锚点（接 source_locator 定位验收）"),
)),

"ExperimentArm": ("实验组（论文跑了哪几组实验）", (
    ("kind",     "must",     "main | baseline | ablation | hyperparam"),
    ("name",     "must",     "组名（如 GDSS / w/o geometry attention / lr=1e-3）"),
    ("config",   "optional", "超参、数据规模、运行次数"),
    ("n_seeds",  "should",   "该组跑了几个 seed"),
    ("evidence", "must",     "设置节原句锚点（'we compare against…' 等）"),
)),
```

### 新增关系（4）

```python
"DECLARES":  ("Paper",         "Contribution",  "论文声称贡献"),
"RUNS":      ("Paper",         "ExperimentArm", "论文跑了哪几组实验"),
"TESTED_BY": ("Contribution",  "ExperimentArm", "贡献被哪组实验验证"),
"ON":        ("ExperimentArm", "Benchmark",     "实验组在哪个基准上"),
```

### 属性增量（全部挂现有类/行，不建新节点）

| 落点 | 新增 | 抽取阶段 | 为什么不是节点 |
|---|---|---|---|
| `Paper` | `paradigm`（枚举）、`evidence_type`（proof/numbers/system/explanation）、`figures[]` | E1 | 一篇一个，不被引用 |
| `Algorithm` | `assumptions[]`（原文数组；应用层再升为 Assumption 节点） | E2 | 「写了什么假设」是事实，「验证了没」是任务判定 |
| `AlgorithmModule` | `is_novel_component: bool`、`component_role`（backbone/encoder/…） | E2 | 模块已有节点，只加标记 |
| `Benchmark.model_results[]` 行 | `arm`（→ExperimentArm）、`outcome_class`（primary/secondary）、`seeds`、`sample_size`、`train_scale`、`value_note`（±方差写这里） | E4 | 属于该数值行 |
| `Benchmark.metrics[]` 行 | `contribution`（"C1" 字符串引用，边在应用层重建） | E3 | 字符串引用即可 |

### 边属性增量（v4 没有的机制，见 13.4）

| 关系 | 新增边属性 | 抽取阶段 |
|---|---|---|
| `EVALUATED_ON` | `protocol = {seeds:int\|null, split:str\|null, eval_script:str\|null, epochs:int\|null, hardware:str\|null}` | E3 |
| `RELATED_TO` | `context`（支撑的原文句子，逐字 ≤120 字）、`cited_doi`、`cited_venue` | E5 |
| `SUBCLASS_OF` | `assumption_delta`（相比父方法改进了哪条前提，≤40 字） | E6 |

> `'we follow the standard split' 不是 split 值，填 null` 这类约束留在 prompt/validator，
> schema 只承诺「字段存在且可空」。

---

## 13.4 tbox_v5.py 实现要点

v4 的 `SEMANTIC_RELATIONS` 只有 `(rel, domain, range, note)`，**没有边属性槽**。
需要新增一个并列结构，而不是改元组签名（保持 `check_domain_range` 等现有调用不变）：

```python
SEMANTIC_VERSION = "v5-semantic"

# 新：边属性注册表（关系名 → {属性名: 类型说明}）
EDGE_ATTRS: Dict[str, Dict[str, str]] = {
    "EVALUATED_ON": {"protocol": "dict{seeds,split,eval_script,epochs,hardware}，值可 null"},
    "RELATED_TO":   {"context": "str(≤120)", "cited_doi": "str|null", "cited_venue": "str|null"},
    "SUBCLASS_OF":  {"assumption_delta": "str(≤40)|null"},
}

def edge_attr_names(rel: str) -> Tuple[str, ...]:
    return tuple(EDGE_ATTRS.get(rel, {}))
```

其余兼容性（沿用 `11` 的结论，逐条核对过）：

| 项 | 处理 |
|---|---|
| `stable_key()` | 不变；新节点不参与 method SAU 指纹，历史 `spec_hash` 不失效 |
| 既有 5 套复现产物 | 继续可读；新节点缺失时判定降级为 qualitative |
| 抽取成本 | E1 +1 组字段、E2 +2 字段、E3 +1 段 +1 字段、E4 +4 字段、E5 +3 边属性、E6 +1 边属性；**不新增 LLM 阶段** |
| 节点规模 | 6001 → 约 12250（Contribution ≈2350 + ExperimentArm ≈3900）；`by_type` 全扫需加类型索引 |
| 与既有类边界 | Contribution ≠ `Algorithm.problems_solved`（声明 vs 能力）；ExperimentArm ≠ `model_results[]`（组 vs 行）；ExperimentArm ≠ 应用层 `ExperimentNode`（论文做了 vs 本次复现跑） |

---

## 13.5 E1–E6 抽取问题 → schema 落点总表

| 阶段 | 原来只问 | 现在还要问 | schema 落点 |
|---|---|---|---|
| E1 | 研究什么问题、什么领域 | 哪个范式？贡献靠什么说服人？列了哪几条贡献、每条为什么以前没人做？ | `Paper.paradigm`、`Paper.evidence_type`、**Contribution 节点**（statement/kind/why_not_before/claimed_strength） |
| E2 | 方法名、机理 | 依赖什么前提才成立？哪个模块是声称的创新组件？ | `Algorithm.assumptions[]`、`AlgorithmModule.is_novel_component` + `component_role` |
| E3 | 输入输出、指标 | 实验协议是什么？每个指标度量哪个贡献？ | `EVALUATED_ON.protocol` 边属性、`Benchmark.metrics[].contribution`、**ExperimentArm 节点**（设置侧） |
| E4 | 数值 | 几个 seed？样本量与训练规模？主结果还是消融？ | `model_results[].seeds/sample_size/train_scale/outcome_class/arm`（行属性，arm 回指节点） |
| E5 | 工具与公式 | 这条引用支撑哪句话？被引论文 DOI/venue？ | `RELATED_TO.context / cited_doi / cited_venue` 边属性 |
| E6 | 继承关系 | 相比父方法改进了哪条前提？ | `SUBCLASS_OF.assumption_delta` 边属性 |

注意两点一致性：
- ExperimentArm **拆在 E3+E4 两段抽**（`12` 的结论）：E3 读设置节（有哪些组、什么配置），
  E4 读数值行（哪行属于哪个组）。只放 E4 看不出「这是 baseline 还是消融」；
  只放 E3 无法落到具体数值行。
- 每条新字段都要求 `evidence` 逐字句锚点，由 `12` 的定位器验收
  （`locate_rate` / `value_not_in_text` 进抽取报告质量指标）。

---

## 13.6 实施顺序（沿用 `12.6`，先修地基再长节点）

| 步 | 做什么 | 依赖 | schema 变化 |
|---|---|---|---|
| 1 | `trace_to_source.py` 接进抽取收尾，出定位率 | — | 无 |
| 2 | E4 修表头错位（模型名/指标名互换、纯符号当模型名） | 步 1 | `model_results[]` 行修复（2411 的 135 个坏行降到 <30） |
| 3 | E1 加 Contribution 抽取 | 无 | +1 类、+DECLARES |
| 4 | E3+E4 加 ExperimentArm | 步 3（contribution 需被 arm 引用） | +1 类、+RUNS/TESTED_BY/ON、行属性 +arm |
| 5 | E2 加 assumption；E6 加 assumption_delta | 无 | `Algorithm.assumptions[]`、`SUBCLASS_OF` 边属性 |
| 6 | E5 边属性、E3 protocol 边属性（引入 EDGE_ATTRS 机制） | 步 6 前完成 tbox_v5.py | +3 组边属性 |

> 先修 E4 再加节点的理由（`12.6`）：当前 46.6% 的数值回不到原文，
> 在此基础上加 Contribution/ExperimentArm 只会把错误传导进新节点。

---

## 13.7 边界：明确不做的事

1. **schema 不装禁令**。「不许编造 seed」等约束只存在于 validator 与 prompt 约束段；
   schema 每条字段必须能用「论文说了什么」回答，且可空（`seeds=null` 是合法值，强制填会诱导编造）。
2. **不建第四条主链**。验证轴是轴不是链：它的三个节点（Contribution/ExperimentArm/数值行）
   分属三主链的缝，单独成链会造成归属歧义。
3. **不加第 9 个节点**。`11` 已核对 7 项信息（paradigm/evidence_type/protocol/seeds 等）
   只需属性或边属性；建节点会让图膨胀到 2 万+ 而查询能力不变。
4. **Assumption 在应用层**，不在语义层（与 Limitation 同法：语义层存文本，应用层逐条判定）。
