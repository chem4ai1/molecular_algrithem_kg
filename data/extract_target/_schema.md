# 配置字段说明（v1）

## 一次抽取 stage 文件（`stages/*.yaml`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `stage` | 是 | 唯一 id，如 `E1_paper` |
| `order` | 是 | 执行顺序 |
| `enabled` | 否 | 默认 true；false 则跳过 |
| `target.classes` | 是 | 本阶段产出的语义层类（用于裁剪契约与词表） |
| `target.wrapper` | 否 | 输出的数组字段名（如 `algorithms`），无则顶层平铺 |
| `contract.required` | 是 | 必填字段 |
| `contract.optional` | 否 | 可选字段 |
| `contract.note` | 否 | 追加到契约后的阶段说明 |
| `template` | 是 | prompt 正文，支持 `{slot}` 占位 |
| `slots` | 否 | 允许的占位名（多余占位会被校验拒绝） |
| `section_slice` | 否 | 从 md 取哪一段（`intro` / `method` / `experiment` / `full`） |
| `guards` | 否 | `max_items` / `max_chars` / `evidence_required` |

## 二次抽取 refine 文件（`refine/*.yaml`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `refine` | 是 | 唯一 id，如 `R1_contribution` |
| `order` | 是 | 执行顺序 |
| `enabled` | 否 | 默认 true |
| `target.class` | 是 | 新建或补充的类 |
| `target.node_id` | 是 | id 模板，支持 `{arxiv_id}` `{n}` `{parent}` |
| `target.relation` | 否 | 挂到父节点的关系，如 `DECLARES` |
| `target.parent_class` | 否 | 父节点类型（用于找父节点 id） |
| `section_hints` | 否 | 去哪些章节找证据（关键词匹配 md 标题） |
| `signal_words` | 否 | 命中这些词的段落优先送入 |
| `locate` | 否 | `max_paragraphs` / `window` / `strategy` |
| `fields` | 是 | 字段列表：`name` `required` `type` `enum` `max_items` `max_chars` |
| `template` | 是 | prompt 正文，支持 `{context}` `{existing}` `{fields}` |
| `merge` | 否 | `append`（默认）/ `overwrite`，决定与已有节点如何合并 |

## 校验规则

- 所有 `{slot}` 必须在 `slots` 里声明，否则加载即报错（防止模板漏传参）
- `contract.required` 必须是 `target.classes` 中某类的 LLM 字段（不能是 NON_LLM 字段）
- `fields[].enum` 必须与 `tbox_v4` 里该字段的枚举一致（不一致时告警不阻断）
- 二次抽取的 `target.relation` 必须在 `SEMANTIC_RELATIONS` 里（或应用层关系表）
