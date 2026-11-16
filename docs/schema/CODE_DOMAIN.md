# 代码域设计（7 个节点）

> 目标：把「论文里的方法」接到「本地仓库里的代码」，并让实验域能追溯到「哪次运行、哪个产物」。

## 1. 调研依据

| 系统 | 节点/边设计 | 可借鉴 | 不借鉴 |
|---|---|---|---|
| **CodexGraph**（NAACL 2025） | 6 节点：MODULE / CLASS / FUNCTION / METHOD / FIELD / GLOBAL_VARIABLE；5 边：CONTAINS / HAS_METHOD / HAS_FIELD / INHERITS / USES | MODULE→CLASS/FUNCTION 的 CONTAINS 骨架 | FIELD / GLOBAL_VARIABLE（复现用不到） |
| **RepoGraph**（ICLR 2025） | 节点 = 一行代码（def/ref），边 = invoke/contain；检索取 k 跳邻域，k 不宜大 | 「k 跳子图 + 扁平化」的取数方式 | 行级粒度（节点爆炸） |
| **ARISE**（2026） | 指出 LocAgent 只到函数级、缺数据流 | 函数级是性价比最高的粒度 | 数据流建模（成本过高） |
| **MLflow / DVC** | Run → params + artifacts + metrics；Artifact 有版本 | Run / Artifact 二分 | 完整实验追踪栈（用文件即可） |
| **Agent Skills**（2025-12 开放标准） | 文件夹 + SKILL.md，渐进披露（渐进加载，不占满上下文） | 「按需展开」：文件→符号→行 | 技能本身不进图 |

**结论**：取 CodexGraph 的「模块-符号」骨架，取 MLflow 的「Run-Artifact」二分，粒度停在**符号级**，不做行级与字段级。

## 2. 与语义层的分工（关键决策）

| | 语义层 `CodeRepository` / `CodeFunction` | 应用层代码域 |
|---|---|---|
| 内容 | 论文**声明**有代码、被对齐到的函数（49 个） | 本地仓库**实际**结构（全量 AST） |
| 来源 | E2 的 `code_symbols` + `_find` 匹配 | tree-sitter / `ast` 扫 `data/repos/<name>` |
| 用途 | 证明「论文有实现」 | 支撑「怎么跑起来、改哪里」 |
| 规模 | 10 仓库 / 49 函数 | 全量（单仓库数百符号） |

**不合并**：语义层是「论文事实」，代码域是「本地事实」，二者可能不一致（论文说有代码但本地没 clone）。

## 3. 七个节点

| 节点 | 属性 | 生命周期 | 对应 |
|---|---|---|---|
| `CodeUnit` | path / lang / role(entry/lib/test/config) / loc / sha256 | global | CodexGraph MODULE |
| `CodeSymbol` | name / kind(class/function/method) / signature / qualname / loc / sha256 | global | CLASS+FUNCTION+METHOD 合并 |
| `Dependency` | name / version / declared_in / used_by[] | global | 无（RepoGraph 缺） |
| `EntryPoint` | path / cmd / args / cwd | global | 无 |
| `TestUnit` | name / path / covers[] / status | global | 无 |
| `EnvSpec` | python / cuda / packages[] / device | global | 无 |
| `RunArtifact` | run_id / kind(log/metric/file) / path / sha256 / produced_by | **task** | MLflow Artifact |

## 4. 域内关系（9 条）

| 关系 | Domain → Range | 说明 |
|---|---|---|
| `CONTAINS` | CodeUnit → CodeSymbol | 文件包含符号 |
| `IMPORTS` | CodeUnit → CodeUnit | 同仓库文件依赖 |
| `CALLS` | CodeSymbol → CodeSymbol | 调用（静态解析，可能不全） |
| `INHERITS` | CodeSymbol → CodeSymbol | 类继承 |
| `DEPENDS_ON` | CodeUnit → Dependency | 三方依赖 |
| `IN_UNIT` | EntryPoint → CodeUnit | 入口在哪个文件 |
| `USES_ENV` | EntryPoint → EnvSpec | 入口需要的环境 |
| `COVERS` | TestUnit → CodeSymbol | 测试覆盖 |
| `TEST_IN` | TestUnit → CodeUnit | 测试所在文件 |

## 5. 跨域关系（8 条，用户重点）

| 关系 | Domain → Range | 回答什么问题 |
|---|---|---|
| `IMPLEMENTED_BY` | AlgorithmModule → CodeSymbol | 这个模块在代码哪实现（**替换**原 `MODULE_IMPLEMENTED_BY→CodeFunction`） |
| `EXECUTED_BY` | ExperimentArm → EntryPoint | 这个实验组靠哪个入口跑 |
| `PRODUCES` | ExperimentArm → RunArtifact | 跑出了什么（日志/指标/文件） |
| `REPRODUCED_BY` | LeaderboardEntry → RunArtifact | 这个数值由哪次运行产生 |
| `COMPUTED_BY` | MetricDefinition → CodeSymbol | 这个指标由哪个函数算 |
| `ASSUMED_IN` | Assumption → CodeUnit | 假设隐含在代码哪处（Type II 定位） |
| `DETECTABLE_IN` | FailureMode → CodeUnit | 这条坑在代码哪处可检测 |
| `GROUNDED_IN` | Evidence → CodeUnit | 这条证据来自代码的哪处 |

## 6. 三个联系链（怎么用）

### 链 A：模块 → 符号 → 测试（改哪里）
```
AlgorithmModule -IMPLEMENTED_BY-> CodeSymbol
  -CALLS-> CodeSymbol (上下游)
  <-COVERS- TestUnit (有没有测试)
```
用途：复现时「模块没实现」的 mismatch，可直接定位到文件与函数。

### 链 B：实验组 → 入口 → 产物（怎么跑）
```
ExperimentArm -EXECUTED_BY-> EntryPoint
  -USES_ENV-> EnvSpec
ExperimentArm -PRODUCES-> RunArtifact (log/metric)
LeaderboardEntry -REPRODUCED_BY-> RunArtifact
```
用途：回答「这个数是怎么跑出来的」——入口 + 环境 + 日志三件套。

### 链 C：假设/坑 → 代码位置（为什么会错）
```
Assumption -ASSUMED_IN-> CodeUnit
FailureMode -DETECTABLE_IN-> CodeUnit
```
用途：Type II（隐藏违规）与「数据泄漏」这类坑，从领域知识落到**具体文件**，而不是停在「理论上可能」。

## 7. 不做的

| 不建 | 理由 |
|---|---|
| 行级节点（RepoGraph 式） | 单仓数万行，节点爆炸；检索用 `file:line` 属性即可 |
| `FIELD` / `GLOBAL_VARIABLE` | 复现不需要变量级 |
| 数据流边 | 静态分析成本高，且对「能不能跑通」帮助有限 |
| 完整实验追踪栈 | 用 `RunArtifact` 文件 + `sha256` 足够 |
| `Import` 作为节点 | 是边（IMPORTS），不是实体 |

## 8. 落地步骤

1. `applayer/tbox.py` 加 7 类 + 17 条关系（已做，见 §9）
2. `applayer/codescan.py`：`ast` 扫仓库 → CodeUnit / CodeSymbol / Dependency / EntryPoint / TestUnit / EnvSpec
3. `applayer/codegraph.py`：CALLS / IMPORTS / INHERITS 解析（先做同文件，跨文件用 import 表）
4. `reprospec` 执行后写 `RunArtifact`
5. 重跑 `gen_schema_docs.py` 生成 7 份新文档

## 9. 与现有结构的兼容

- `MODULE_IMPLEMENTED_BY` 保留（指向语义层 `CodeFunction`），新增 `IMPLEMENTED_BY` 指向应用层 `CodeSymbol`
- 两者不冲突：前者证明「论文有实现」，后者回答「本地怎么改」
- 代码域节点全部 `layer=application, task=code`，不写回 `app_writing.json` 之外的图
