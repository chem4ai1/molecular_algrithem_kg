# `ExperimentArm` · 实验组（05：main/baseline/ablation/hyperparam）

> 层：**应用层** ｜ 生命周期：**global** ｜ 图内实例：**0**

## 1. 定位

实验组（05：main/baseline/ablation/hyperparam）。

「论文做过什么」是事实；「本次复现跑哪些」应进 `METHOD_LOCK.experiment_matrix`。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `kind` | must | 类别 | — |
| `name` | must | 名称 | — |
| `config` | optional | 配置描述 | — |
| `n_seeds` | optional | 种子数 | — |
| `benchmark` | optional | 基准名 | — |
| `evidence` | optional | 逐字引文 | — |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `ON` | Benchmark | 实验组跑在哪个基准 |
| `EXECUTED_BY` | EntryPoint | 实验组靠哪个入口跑 |
| `PRODUCES` | RunArtifact | 实验组产出的产物 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `TESTED_BY` | Contribution | 该贡献由哪个实验组验证 |
| `RUNS` | Paper | 论文做了哪些实验组 |

## 4. 抽取来源

- 二次抽取：`R2_experiment_arm`

## 5. 使用场景

- 实验矩阵完备性；消融规划

## 6. 示例

```json
{
  "id": "experiment:<aid>:<slug>",
  "type": "ExperimentArm",
  "kind": "<kind>",
  "name": "<name>",
  "config": "...",
  "n_seeds": "...",
  "benchmark": "...",
  "evidence": "..."
}
```
