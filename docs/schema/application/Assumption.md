# `Assumption` · 方法成立的前提（07 Type II）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

方法成立的前提（07 Type II）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `statement` | must | 一句话陈述 | — |
| `scope` | optional | global/module | — |
| `applicability` | optional | 适用范围 | — |
| `evidence` | optional | 逐字引文 | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `ASSUMES` | Algorithm | 算法依赖的前提 |

## 4. 抽取来源

- 二次抽取：`R3_assumption`

## 5. 使用场景

- Type II 泄露检查；限制章节

## 6. 示例

```json
{
  "id": "assumption:<aid>:<slug>",
  "type": "Assumption",
  "statement": "<statement>",
  "scope": "...",
  "applicability": "...",
  "evidence": "..."
}
```
