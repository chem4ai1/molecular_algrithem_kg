# `TestUnit` · 测试单元

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

测试单元。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 名称 | — |
| `path` | optional |  | — |
| `covers` | optional |  | — |
| `status` | optional | pass/fail/unknown | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `COVERS` | CodeSymbol | 测试覆盖 |
| `TEST_IN` | CodeUnit | 测试所在文件 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 改完有没有测试兜底

## 6. 示例

```json
{
  "id": "testunit:<aid>:<slug>",
  "type": "TestUnit",
  "name": "<name>",
  "path": "...",
  "covers": "...",
  "status": "..."
}
```
