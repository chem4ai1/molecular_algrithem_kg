# `EntryPoint` · 可执行入口

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

可执行入口。

由 `if __name__ == '__main__'` 或文件名规则判定，可能把 demo 脚本也纳入。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `path` | must |  | — |
| `cmd` | optional |  | — |
| `args` | optional |  | — |
| `cwd` | optional |  | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `IN_UNIT` | CodeUnit | 入口所在文件 |
| `USES_ENV` | EnvSpec | 入口所需环境 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `EXECUTED_BY` | ExperimentArm | 实验组靠哪个入口跑 |

## 4. 抽取来源

- 规则/内置映射（不经 LLM）

## 5. 使用场景

- 实验组怎么跑；复现入口

## 6. 示例

```json
{
  "id": "entrypoint:<aid>:<slug>",
  "type": "EntryPoint",
  "path": "<path>",
  "cmd": "...",
  "args": "...",
  "cwd": "..."
}
```
