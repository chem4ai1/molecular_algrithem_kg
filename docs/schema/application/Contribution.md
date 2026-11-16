# `Contribution` · 论文声称的贡献（04/06）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

论文声称的贡献（04/06）。

是「论文声称的贡献」；`numeric` SAU 是「可验证的声明」，二者不同层。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `statement` | must | 一句话陈述 | — |
| `kind` | must | 类别 | — |
| `novelty_basis` | optional | 新颖性依据[] | — |
| `section` | optional | 章节名 | — |
| `claimed_strength` | optional | proven/supported/suggests | — |
| `evidence` | optional | 逐字引文 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `TESTED_BY` | ExperimentArm | 该贡献由哪个实验组验证 |
| `SHOWN_BY` | FigureAsset | 该贡献由哪张图表支撑 |
| `CHALLENGED_BY` | ReviewPoint | 该贡献可能被如何质疑 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `DECLARES` | Paper | 论文声明贡献 |
| `ANCHORS` | ResearchGap | 该空白锚定了哪条贡献 |

## 4. 抽取来源

- 二次抽取：`R1_contribution`

## 5. 使用场景

- 生成时决定主推哪条；复现时决定验证顺序

## 6. 示例

```json
{
  "id": "contribution:<aid>:<slug>",
  "type": "Contribution",
  "statement": "<statement>",
  "kind": "<kind>",
  "novelty_basis": "...",
  "section": "...",
  "claimed_strength": "...",
  "evidence": "..."
}
```
