# `CodeRepository` · 代码仓库

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**10**

## 1. 定位

代码仓库。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `repo_name` | must | 仓库名 | ✅ |
| `repo_url` | should | 仓库地址 | ✅ |
| `local_path` | optional | 本地路径 | ✅ |
| `license` | optional | 许可证 | ✅ |
| `is_original_repo` | should | 是否作者原仓库 | ✅ |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `HAS_FUNCTION` | CodeFunction | 仓库包含函数 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HAS_CODE` | Paper | 论文关联代码仓库 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 定位原仓库；code_grounding 的入口

## 6. 示例

```json
{
  "id": "repo:<aid>:<slug>",
  "type": "CodeRepository",
  "repo_name": "<repo_name>",
  "repo_url": "...",
  "local_path": "...",
  "license": "...",
  "is_original_repo": "..."
}
```
