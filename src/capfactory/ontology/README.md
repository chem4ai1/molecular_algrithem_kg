# ontology/ — TBox 定义与判定

**唯一权威入口：`tbox.py`**。任何运行时 domain/range 判定只走
`check_domain_range()`；定义源保留兼容，但不得再自行实现判定。

## 口径合并（历史 4 套 → 1 套）

| 定义源 | 内容 | 计数 |
|---|---|---|
| `model.py` | `V2_CLASSES` / `V2_RELATIONS`，17 类核心 schema | 17 / 17 |
| `layers.py` | 分层关系 `layer_relations()` | — |
| `generation.py` | 生成链关系 `gen_relations()` | — |
| `schema_v3.py` | `V3_CLASSES` / `V3_RELATIONS` / `ROOT_FAMILIES` | 5 / 30 |
| **`library.py::_all_relations()`** | **合并后的生效词表** | **46 类 / 105 关系** |

`tbox.py` 提供：
- `TBOX_VERSION = "v3.2-105"`
- `authoritative_relations()` / `authoritative_classes()`
- `resolve_type()`：类型别名归一（`MetricObservation → Observation` 等 7 条）
- `check_domain_range(src_type, rel, dst_type)`（先归一别名，再支持 `A|B` 复合 domain）
- `snapshot()` → `{version, n_classes, n_relations, n_active_*, n_reserved_*, hash}`
- `active_snapshot()` / `reserved_snapshot()` / `is_reserved(kind, name)`
- `compile_manifest()` → 延迟包装 `sciforge.intake.compile_tbox()`

## reserved 分组（第二档精简）

实测 45 类中 30 个零节点、105 关系中 87 个零使用，它们**保留定义但标记 reserved**：
- `RESERVED_CLASSES`（30）：评测链、生成任务链、叙事链、因果链、方法细化类
- `RESERVED_RELATIONS`（87）：layers/generation/V3 中尚未产生实例的关系

规则：**页面与抽取提示词只引用 `active_snapshot()`**（16 类 / 18 关系）；
`compile_tbox()` 仍输出全量计数（测试与 Manifest 依赖）。

## 文件职责

| 文件 | 职责 | 状态 |
|---|---|---|
| `tbox.py` | ★ 单一权威判定入口 | 核心 |
| `library.py` | `OntologyLibrary` / `default_library` / shapes / coverage / inventory | 核心 |
| `model.py`, `layers.py`, `generation.py`, `schema_v3.py` | 定义源 | 核心 |
| `chains.py` | 10 条链定义、`STAGES`/`ROOT_STAGES`、触手规格 | 核心 |
| `metrics.py` | 指标归一（exact → alias → canonicalize） | 核心 |
| `modules.py`, `prompts.py`, `refine.py`, `cad.py` | 生成/精修/提示词支撑 | 兼容层（测试依赖） |
| `instantiate.py` | 历史实例化器 | **已归档** `backup/capfactory/ontology/` |

## 边界

- `STAGES` 保留别名指向 `ROOT_STAGES`，不要一次性删除（660 测试依赖）。
- 新增关系：改定义源后必须确认 `tbox.snapshot()['n_relations']` 与
  `tests/test_ontology_library.py` / `tests/Phase/test_phase00_intake.py` 的计数断言同步。
