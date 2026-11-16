# 声明式抽取与二次抽取

> 目标：新增一类节点 / 一个属性 / 一条关系，**只改 `data/extract_target` 下的 YAML**，不动 Python。
> 代码：`semantic/extractspec/`（schema / loader / render / refine）。

## 1. 为什么改

改造前，抽取对象与字段写死在两处：

```
semantic/extraction/contracts.py   E_CONTRACTS / NON_LLM / STAGE_CLASSES / STAGE_NOTE
semantic/extraction/prompts.py     COMMON / PROMPTS（6 个阶段模板）
```

加一个字段要同时改 `contracts.py`、`prompts.py`、`validator.py`、`tbox_v4.py` 四处，
且无法只对「某类论文」或「某个已有节点」做补抽。

## 2. 目录

```
data/extract_target/
├── README.md
├── _schema.md              字段说明与校验规则
├── stages/                 一次抽取（E1–E6）
│   ├── _common.yaml        通用规则（COMMON）
│   ├── E1_paper.yaml
│   ├── E2_algorithm.yaml
│   ├── E3_benchmark.yaml
│   ├── E4_values.yaml
│   ├── E5_relations.yaml
│   └── E6_lineage.yaml
└── refine/                 二次抽取（基于已有结果补抽）
    ├── R1_contribution.yaml
    ├── R2_experiment_arm.yaml
    └── R3_assumption.yaml
```

**加载优先级**：`data/extract_target/` > 内置常量。目录为空或文件缺失时自动退化，
保证迁移期行为完全不变。

## 3. 一次抽取配置（stage）

```yaml
stage: E1_paper
order: 1
enabled: true
target:
  classes: [Paper]          # 本阶段产出的语义层类（用于裁剪契约与词表）
  wrapper: null             # 输出数组字段名，无则顶层平铺
  target_desc: Paper
contract:
  required: [research_question, problem_category, why_hard]
  optional: [relation_hints, evidence]
  all_fields: [...]         # 落图字段（用于契约渲染校验）
  aux_fields: [domain_code, evidence]   # prompt 专用，不落图
  note: "domain/domain_code 由 papers.csv 校准"
section_slice: paper        # paper | algorithm | benchmark | lineage
slots: [paper_text, rule_hints]
template: |
  任务：抽 Paper 的核心属性……
  【论文标题】{title}
  【摘要与引言】{paper_text}
```

`contract.required/optional` 是**输出 JSON 的键**（可能是嵌套数组或关系名，如
`modules` / `from` / `to`），与语义层字段不是同一套；契约文本的字段直接读
`tbox_v4.SEMANTIC_CLASSES`，与改造前一致。

## 4. 二次抽取配置（refine）

```yaml
refine: R1_contribution
order: 1
target:
  class: Contribution
  node_id: "contribution:{arxiv_id}:{n}"
  relation: DECLARES
  parent_class: Paper
section_hints: [introduction, abstract, conclusion]
signal_words: [we propose, we introduce, our contribution]
locate:
  max_paragraphs: 6
fields:
  - name: statement
    required: true
    type: str
    max_chars: 80
  - name: kind
    enum: [method, data, analysis, system]
template: |
  任务：抽取作者明确声明的贡献……
  【已有抽取信息】{existing}
  【原文段落】{context}
  可用字段：{fields}
merge: append
```

`node_id` 支持 `{arxiv_id}` `{n}` `{kind}` `{parent}`；
`merge` 为 `append` 时已存在的 id 不覆盖。

## 5. 代码结构

| 文件 | 职责 |
|---|---|
| `extractspec/schema.py` | `StageSpec` / `RefineSpec` / `FieldSpec` + YAML 解析 |
| `extractspec/loader.py` | 扫描配置、按 mtime 缓存、校验（类存在性 / 占位声明 / 枚举） |
| `extractspec/render.py` | 配置优先渲染 prompt；无配置退化到 `prompts.render` |
| `extractspec/refine.py` | 段落定位 → 渲染 → 解析校验 → 写图 |

接入点只有一处：`extraction/runner.py` 的 `render/stages` 改为从 `extractspec.render` 导入。

```python
try:
    from ..extractspec.render import render, stages   # 配置优先
except Exception:
    from .prompts import render, stages               # 退化
```

## 6. 等价性（迁移不改行为）

`tests/test_extractspec.py` 断言 6 个阶段的 prompt **与改造前逐字节相同**：

```
E1_paper 1678 · E2_algorithm 1720 · E3_benchmark 1073
E4_values 846 · E6_lineage 1078 · E5_relations 764
```

阶段顺序也与旧 `PROMPTS` dict 顺序一致（E6 在 E5 前），避免执行顺序漂移。

## 7. 新增一个抽取目标的三步

**加一个属性（已在的类）**：改对应 `stages/E*.yaml` 的 `contract` + `template` + 同步 `tbox_v4` 字段 → 完成。

**加一类新节点（一次抽取）**：在 `stages/` 新建 YAML，`target.classes` 写新类 →
`tbox_v4` 加类定义 → loader 校验通过即生效。

**加二次抽取（基于已有信息补抽）**：在 `refine/` 新建 YAML，写 `target` / `section_hints` /
`signal_words` / `fields` / `template` → 直接可跑，无需改代码。

示例（新增「局限」抽取）：

```bash
cp data/extract_target/refine/R3_assumption.yaml data/extract_target/refine/R4_limitation.yaml
# 改 refine/target.class/fields/template 即可
python stages/1_extraction/refine_run.py --list
python stages/1_extraction/refine_run.py --paper 2411.06608 --target R4_limitation --dry-run
```

## 8. 用法

```bash
# 列出所有阶段与二次抽取目标（含配置错误）
python stages/1_extraction/refine_run.py --list

# 只看 prompt 与候选段落（不调模型）
python stages/1_extraction/refine_run.py --paper 2411.06608 --target R1_contribution --dry-run

# 调用模型并写回图（先备份）
python stages/1_extraction/refine_run.py --paper 2411.06608 --target R1_contribution --apply
```

## 9. 边界

- 二次抽取**只读原文段落**，不重新读全篇；定位靠 `section_hints + signal_words` 打分。
- 段落筛选会跳过 `Table/Figure/Equation` 标题段与参考文献之后的段落。
- `parse_payload` 对「枚举不符 / 缺必填」的行**整行丢弃**，不产出半残节点。
- 二次抽取不改 `stable_key()`，不影响历史 `spec_hash`。
- 配置里的 `contract.required/optional` 是输出键，别当成语义层字段（loader 不校验它）。
