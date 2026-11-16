# `Dependency` · 第三方依赖

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

第三方依赖。

从 AST import + requirements.txt 双向收集，可能含标准库。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 名称 | — |
| `version` | optional |  | — |
| `declared_in` | optional |  | — |
| `used_by` | optional |  | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `DEPENDS_ON` | CodeUnit | 三方依赖 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 依赖冲突排查；环境复现

## 6. 示例

```json
{
  "id": "dependency:<aid>:<slug>",
  "type": "Dependency",
  "name": "<name>",
  "version": "...",
  "declared_in": "...",
  "used_by": "..."
}
```
