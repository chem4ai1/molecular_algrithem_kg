# `Algorithm` · 算法（论文提出的方法）

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**1674**

## 1. 定位

算法（论文提出的方法）。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 算法名 | ✅ |
| `task_type` | should | 任务类型（12 类枚举） | ✅ |
| `flow_family` | should | 算法族（18 族枚举） | ✅ |
| `problems_solved` | should | 能解决什么问题 | ✅ |
| `mechanism` | should | 机理 | ✅ |
| `why_it_works` | optional | 为什么有效 | ✅ |
| `applicable_to` | optional | 适用场景 | ✅ |
| `limitations` | optional | 局限（文本，不建节点） | ✅ |
| `assumptions` | optional | 方法成立的前提[]（Type II 泄露检查用） | ❌ 0% |
| `novelty_basis` | optional | 新颖性依据[]：technical_constraint/theoretical_blind_spot/data_availability | ❌ 0% |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `EVALUATED_ON` | Benchmark | 在哪个基准上评测 |
| `HAS_MODULE` | AlgorithmModule | 算法由哪些模块构成 |
| `SUBCLASS_OF` | Algorithm | 算法继承/改进关系 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `PROPOSES_METHOD` | Paper | 论文提出算法 |
| `RELATED_TO` | Paper | 相关文献/方法 |
| `SUBCLASS_OF` | Algorithm | 算法继承/改进关系 |

## 4. 抽取来源

- 一次抽取：`E2_algorithm`、`E6_lineage`

## 5. 使用场景

- 跨论文对比方法；编译 method SAU

## 6. 示例

```json
{
  "id": "algorithm:<aid>:<slug>",
  "type": "Algorithm",
  "name": "<name>",
  "task_type": "...",
  "flow_family": "...",
  "problems_solved": "...",
  "mechanism": "...",
  "why_it_works": "..."
}
```
