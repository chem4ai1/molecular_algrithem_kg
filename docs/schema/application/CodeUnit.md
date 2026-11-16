# `CodeUnit` · 代码文件/包（本地仓库实际结构）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

代码文件/包（本地仓库实际结构）。

与语义层 `CodeRepository` 不同：这里记本地仓库的实际文件，可能论文说开源但本地没 clone。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `path` | must |  | — |
| `lang` | optional |  | — |
| `role` | optional |  | — |
| `loc` | optional |  | — |
| `sha256` | optional |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `CONTAINS` | CodeSymbol | 文件包含符号 |
| `IMPORTS` | CodeUnit | 同仓库文件依赖 |
| `DEPENDS_ON` | Dependency | 三方依赖 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `IMPORTS` | CodeUnit | 同仓库文件依赖 |
| `IN_UNIT` | EntryPoint | 入口所在文件 |
| `TEST_IN` | TestUnit | 测试所在文件 |
| `ASSUMED_IN` | Assumption | 假设隐含在代码哪处 |
| `DETECTABLE_IN` | FailureMode | 该失败模式在代码哪处可检测 |
| `GROUNDED_IN` | Evidence | 证据来自代码哪处 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 定位「改哪个文件」；Type II 假设与失败模式落点

## 6. 示例

```json
{
  "id": "codeunit:<aid>:<slug>",
  "type": "CodeUnit",
  "path": "<path>",
  "lang": "...",
  "role": "...",
  "loc": "...",
  "sha256": "..."
}
```
