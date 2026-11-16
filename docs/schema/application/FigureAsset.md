# `FigureAsset` · 图表资产（08）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

图表资产（08）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `fig_label` | must | 图号 | — |
| `caption` | optional | 图注 | — |
| `kind` | optional | 类别 | — |
| `for_contribution` | optional | 支撑哪条贡献 | — |
| `placement` | optional | body/appendix | — |

## 3. 关系

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `SHOWN_BY` | Contribution | 该贡献由哪张图表支撑 |

## 4. 抽取来源

- 二次抽取：`R4_figure`

## 5. 使用场景

- 图表归属（正文/附录）；图-claim 绑定

## 6. 示例

```json
{
  "id": "figure:<aid>:<slug>",
  "type": "FigureAsset",
  "fig_label": "<fig_label>",
  "caption": "...",
  "kind": "...",
  "for_contribution": "...",
  "placement": "..."
}
```
