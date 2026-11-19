# 框架审视：我的修改是否还在原有框架里

> 先修完 4 个问题，再诚实核对是否偏离。结论：**有 3 处实质偏离**。

## 1. 四个问题修复结果

| 问题 | 修法 | 结果 |
|---|---|---|
| `split_spec` 1/52 | 放宽正则：`80/10/10`、`8:1:1`、train%/valid% 多写法 | **1 → 14/52** |
| 表头识别错（`229M/68M` 当列名） | ① 列名不能是「纯数值+单位」② 主结果表第一列必须是 Model/Method | 2410.03494 等误判表被正确跳过 |
| 20 篇没生成表 | 放宽到 ≥2 行；但同时加严主表启发式 | 18/52 精选（质量优先） |
| `.tex` 未编译验证 | 加 `tex_escape()`：`& % $ # _ { } ~ ^ \` | `amlodipine\_mpo`、`\# Feature` 正确转义 |

**顺带修的两个真 bug（上一轮遗留）**：
- 指标方向：`SA score (↓)` 该取 min 而非 max
- 同名方法重复行：用行索引而非 model 名标记最优

**产物质量**（18 张表全部是真正的主结果表）：
```latex
Model & Mol. weight (↓) & QED (↑) & SA score (↓) & AiZynth (↑) \\
Saturn-GA-ChEMBL & \textbf{370.9} & \textbf{0.84} & 2.44 & 0.70 \\
```

## 2. 深入审视：逐项核对

### 2.1 仍在框架内的部分 ✅

| 项 | 证据 |
|---|---|
| 语义层仍是 6 类 / 9 关系 | `SEMANTIC_CLASSES` 未加类，只给 Paper 加字段（28→33） |
| 新字段已进 E1 YAML 契约 | `E1_paper.yaml` 的 `all_fields` 含 5 个新字段 |
| validator/apply 三处同步 | `_e1` 归一化 + `apply.py` 白名单都加了 |
| 应用层新类都注册在 tbox | `APP_CLASSES` 54 类、`APP_RELATIONS` 64 关系 |
| 任务级节点带 run_id/layer/miner | `ResultTable` 有 `run_id`，建时写 `layer=application` |
| 词表驱动抽取未破坏 | `vocab.render(stage)` 仍按阶段注入 |

### 2.2 实质偏离的三处 ❌

#### 偏离 1（最严重）：规则抽取绕过了 YAML 声明式框架

**你的原始要求**（`data/extract_target/README.md`）：
> 抽取对象、字段、prompt 模板全部写在这里，Python 只负责读取与执行。
> 新增一类节点 / 一个属性 / 一条关系，**只改这里的 YAML**，不动代码。

**我的做法**：`stages/2_knowledge/extract_rules.py` 里写了
```python
HP_PAT = re.compile(r"\b(number of iterations|temperature|...)\b")
def parse_md_tables(text): ...   # 90 行 Python 规则
```
把「抽什么、怎么抽」写死在了 Python 脚本里。

**判定**：**偏离**。YAML 里只声明了字段名，抽取逻辑在 Python 里——等于「改了代码才能改抽取」。

**修正方案（三选一）**：
| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A** | 在 E1 YAML 加 `rules:` 段，声明「哪个字段用哪个正则」 | 完全符合声明式 | 需扩展 schema.py 支持 rules |
| B | 用框架已有的 `render(rule_hints=...)` 把规则抽到的内容注入 LLM prompt | 零 schema 改动 | 仍是 Python 先跑规则 |
| C | 新建 `E7_rules.yaml` stage | 与 LLM stage 平级 | 需 runner 支持无 LLM 的 stage |

**推荐 A**：`rules:` 段最符合「只改 YAML」的初衷。

#### 偏离 2：应用层节点没走 miner 模式

**框架设计**（`applayer/miner.py`）：
```python
def mine_all(sem_g, *, task=None): ...   # 应用层节点由挖掘器从语义层派生
```
**我的做法**：`p2p6_e2e.py` 里直接 `g.node(tid, "ResultTable", ...)`。

**判定**：**偏离**。绕过了 miner 注册机制，导致：
- 无法用 `mine_all(task='writing')` 一次性重建
- 无法统计挖掘覆盖率

**修正**：把 ResultTable 加进 `miner.py` 的 miner 列表（`MINERS`），输入是 `Paper.result_tables`。

#### 偏离 3：选表启发式硬编码在生成脚本里

```python
if not any(k in first for k in ("model", "method", "approach", ...)):
    continue    # 主结果表判定
```
这条规则决定「哪张表是主结果表」——是业务判断，应该在配置里，不在代码里。

**修正**：放进 extract_target 的配置（如 `refine/R7_result_table.yaml` 的 `locate` 段）。

### 2.3 一个「不算偏离但要说清」的点

`dataset_spec.py` 里的 `extract_dataset_spec()` 和 `check_leakage()`：
- `check_leakage()` 是**运行时工具**（跑实验时用），不是抽取——放 applayer 合理
- `extract_dataset_spec()` 是抽取——应该走偏离 1 的修正

## 3. 结论：后续还用原框架做抽取吗？

**是，但要做两件事**：

1. **把规则抽取搬进 YAML**（修偏离 1）——这是你最初的核心要求
2. **把 ResultTable 搬进 miner**（修偏离 2）

否则继续加 LLM 抽取（第 2 步的 `formal_def`/`arch_modules`）会加剧偏离：
现在只是规则在 Python，下一步 LLM prompt 也会散在脚本里。

## 4. 建议的修正顺序（做第 2 步之前）

```
第 0 步（补债）：扩展 schema.py 支持 rules: 段
        → 把 extract_rules.py 的 5 条规则写进 E1_paper.yaml
        → 删掉 extract_rules.py 的 Python 规则（保留 check_leakage）
第 0.5 步：ResultTable 加进 miner.py，删 p2p6_e2e 的直接 g.node
第 1 步：主结果表判定搬进 refine/R7_result_table.yaml
第 2 步：再开始 LLM 抽取（formal_def / arch_modules / method_limits）
        → 这一次严格写在 E2 YAML 的 template 和 fields 里
```

## 5. 一句话

**四个问题修好了，产物质量也验证了（18 张 LaTeX 表逐行核对过）。**
**但抽取逻辑现在散在 Python 脚本里，偏离了「只改 YAML 不动代码」的原始设计。**
**建议先还这笔债，再做第 2 步 LLM 抽取——否则偏离会累积。**
