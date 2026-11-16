# `CodeSymbol` · 类/函数/方法（符号级）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

类/函数/方法（符号级）。

粒度停在符号级（类/函数/方法），不做行级与字段级；见 `docs/schema/CODE_DOMAIN.md` §1。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 名称 | — |
| `kind` | must | 类别 | — |
| `signature` | optional |  | — |
| `qualname` | optional |  | — |
| `loc` | optional |  | — |
| `sha256` | optional |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `CALLS` | CodeSymbol | 符号调用 |
| `INHERITS` | CodeSymbol | 类继承 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `CONTAINS` | CodeUnit | 文件包含符号 |
| `CALLS` | CodeSymbol | 符号调用 |
| `INHERITS` | CodeSymbol | 类继承 |
| `COVERS` | TestUnit | 测试覆盖 |
| `IMPLEMENTED_BY` | AlgorithmModule | 模块由哪个符号实现（本地） |
| `COMPUTED_BY` | MetricDefinition | 指标由哪个函数算 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 模块实现定位；指标计算函数

## 6. 示例

```json
{
  "id": "codesymbol:<aid>:<slug>",
  "type": "CodeSymbol",
  "name": "<name>",
  "kind": "<kind>",
  "signature": "...",
  "qualname": "...",
  "loc": "...",
  "sha256": "..."
}
```
