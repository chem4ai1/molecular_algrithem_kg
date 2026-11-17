# `AlgorithmModule` · 算法模块（原 AlgorithmStep）

> 层：**语义层** ｜ 生命周期：**global** ｜ 图内实例：**2870**

## 1. 定位

算法模块（原 AlgorithmStep）。

与 Algorithm 的 id 策略不同：算法跨论文共享，模块按论文唯一（同名会重复 9 次）。`BELONGS_TO_MODULE` 定义了但当前 0 条。

## 2. 属性

| 字段 | 级别 | 说明 | 当前填充 |
|---|---|---|---|
| `name` | must | 模块名 | ✅ |
| `mechanism` | should | 该模块机理 | ✅ |
| `formula` | optional | 公式/方程（文本，不建节点） | ✅ |
| `inputs` | should | 输入 | ✅ |
| `outputs` | should | 输出 | ✅ |
| `is_novel_component` | optional | 是否论文声称的创新组件（消融规划用） | ✅ |
| `component_role` | optional | backbone/encoder/decoder/loss/sampler/other | ✅ |

## 3. 关系

**出边**

| 关系 | 目标 | 说明 |
|---|---|---|
| `MODULE_IMPLEMENTED_BY` | CodeFunction | 模块由哪个函数实现 |

**入边**

| 关系 | 来源 | 说明 |
|---|---|---|
| `HAS_MODULE` | Algorithm | 算法由哪些模块构成 |
| `BELONGS_TO_MODULE` | CodeFunction | 函数所属模块（反向） |

## 4. 抽取来源

- 一次抽取：`E2_algorithm`、`E5_relations`

## 5. 使用场景

- method/ordering/code_grounding 三类 SAU 的来源

## 6. 示例

```json
{
  "id": "algorithmmodule:<aid>:<slug>",
  "type": "AlgorithmModule",
  "name": "<name>",
  "mechanism": "...",
  "formula": "...",
  "inputs": "...",
  "outputs": "...",
  "is_novel_component": "..."
}
```
