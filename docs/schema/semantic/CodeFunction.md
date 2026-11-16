# `CodeFunction` · 代码函数（模块的实现证据）

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**49**

## 1. 定位

代码函数（模块的实现证据）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 函数名 | ✅ |
| `purpose` | should | 作用 | ✅ |
| `comment` | optional | 注释/文档 | ✅ |
| `params` | optional | 参数 | ✅ |
| `returns` | optional | 返回值 | ✅ |
| `func_type` | should | 函数类型（generator/forward/loss/transform/io…） | ✅ |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `BELONGS_TO_MODULE` | AlgorithmModule | 函数所属模块（反向） |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `MODULE_IMPLEMENTED_BY` | AlgorithmModule | 模块由哪个函数实现 |
| `HAS_FUNCTION` | CodeRepository | 仓库包含函数 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 代码对齐的落点；与模块建 MODULE_IMPLEMENTED_BY

## 6. 示例

```json
{
  "id": "func:<aid>:<slug>",
  "type": "CodeFunction",
  "name": "<name>",
  "purpose": "...",
  "comment": "...",
  "params": "...",
  "returns": "...",
  "func_type": "..."
}
```
