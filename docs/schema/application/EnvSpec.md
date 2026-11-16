# `EnvSpec` · 运行环境

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

运行环境。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `python` | optional |  | — |
| `cuda` | optional |  | — |
| `packages` | optional |  | — |
| `device` | optional |  | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `USES_ENV` | EntryPoint | 入口所需环境 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 环境复现（python/cuda/packages）

## 6. 示例

```json
{
  "id": "envspec:<aid>:<slug>",
  "type": "EnvSpec",
  "python": "...",
  "cuda": "...",
  "packages": "...",
  "device": "..."
}
```
