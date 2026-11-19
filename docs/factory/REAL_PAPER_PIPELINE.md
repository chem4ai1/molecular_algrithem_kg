# 真实论文生成流程（从 4 篇论文反推）

> 上一版 12 阶段是从 SciForge 抽象文档照搬的「知识管理阶段」，不是真做一篇论文的动作。
> 这一版从 52 篇里的 4 篇真实论文倒推：**每阶段产出什么代码/数据/表格/章节**。

## 1. 先看真实论文长什么样

### MECo（编辑序列，NeurIPS 风格）`data/docx/2510.14455.md`

```
3 Methods
  3.1 Problem formulation   ← 先给旧形式 Mo=F(Mi,T)，指出两个局限，再给自己的形式化
  3.2 Framework overview    ← 两模块：reasoning LLM 出 action + code LLM 执行
  3.3 Data construction     ← (Mi,A) →C；合成编辑(ZINC+片段替换池) + 真实编辑(ChEMBL35+MMPA)
  3.4 Model Training        ← fine-tune Qwen2.5-Coder-7B
  3.5 Benchmark & metrics   ← 两个基准：编辑执行准确率(诊断) + ChemCoTBench(应用端 VR%/SR%/Sim/CR%)
4 Experiments
  4.1 setup    ← 去泄漏 Tanimoto<0.6，每类采样 1000 条，DeepSeek-R1 vs Gemini-2.5-Pro
  4.2 主实验   ← Table 1: 99.9/98.3/98.3 vs baseline 50.3/9.9/12.2
  4.3 提升     ← ChemCoTBench 六任务属性优化
  4.4 case study
```

### SynFlowNet（GFlowNet，ICML 风格）`2405.01155.md`

```
3 Methods
  3.1 MDP of chemically accessible space   ← 状态/动作/奖励定义
  3.2 Challenges with generating backward paths
  3.3 Scaling of reactant space             ← 大规模 building block
4 Results
  4.1 Reaction-based MDP design
  4.2 GFlowNets as samplers
  4.3 Further comparison to baselines + 4.3.1 rediscovery
  4.4 Improved MDP consistency
```

### AgentDrug（LLM agent）`2410.13147.md`

```
2 Methodology   ← 纯 workflow 描述，没有数学形式化
3 Evaluation
4 Ablation Studies  ← 4.1 示例分子的影响 / 4.2 迭代次数的影响
```

### SynCraft（Nature MI）`2512.20333.md`

```
Results（42-216行，200行长，全部实验塞这里）
Discussion
Methods（后置）
Data availability / Code availability
```

**四个关键观察**：
1. **方法节结构因流派而异**：GFlowNet 要 MDP 定义；LLM agent 只写 workflow；编辑序列要「形式化+数据+训练+指标」
2. **实验节因流派而异**：GFlowNet 做采样质量+rediscovery；agent 做组件消融；编辑做「主表+提升+case study」
3. **Nature 系没有 Experiments 章节**，用 Results 替代，Methods 后置
4. **数据构造是方法节的一部分**（MECo 3.3），不是附录

## 2. 真实 12 个阶段

### P0 · 选题与问题形式化

| | |
|---|---|
| **动作** | 读同流派社区 → 写数学形式化 → 指出旧形式具体缺陷 |
| **产物** | `ProblemFormulation{olds, limits[], new_form, motivation}` |
| **证据** | MECo 3.1：先写 `Mo=F(Mi,T)`，再列「编辑不透明」「违反化学原则」两条局限 |
| **门** | 必须能写出公式 + 旧方法至少 1 条可验证缺陷 |
| **代码** | 无（但产出要能直接放进论文 3.1） |

### P1 · 技术路线与架构设计

| | |
|---|---|
| **动作** | 从 D1 流派社区选路线 → 划模块 → 画架构图 |
| **产物** | `TechnicalRoute{family, modules[], why_not_other}` |
| **证据** | MECo 3.2 两模块；SynFlowNet 3.1-3.3 MDP 三要素 |
| **门** | 必须回答「为什么不用同流派另一种做法」 |
| **代码** | 架构图（Figure 1/2） |

### P2 · 数据构造

| | |
|---|---|
| **动作** | 选数据源 → 去泄漏 → 划分 → 造训练集 |
| **产物** | `DatasetSpec{sources, dedup_rule, split, sizes}` + 数据文件 |
| **证据** | MECo 3.3：ZINC 采样+片段替换池；ChEMBL35+MMPA；4.1 去泄漏 Tanimoto<0.6、每类 1000 条 |
| **门** | 测试集与训练集 Tanimoto 相似度 < 阈值；测试集不可见 |
| **代码** | `build_dataset.py`（含去泄漏检查） |

### P3 · 代码实现

| | |
|---|---|
| **动作** | 写模型/算法代码 + 训练脚本 + 数据处理 |
| **产物** | `CodeArtifact{modules[], entrypoints[], deps}` |
| **证据** | 语义层 `CodeFunction`（当前只抽到 49 个，严重不足） |
| **门** | smoke test 跑通（小样本前向） |
| **代码** | `model/`, `train.py`, `data/` |

### P4 · 训练与调试

| | |
|---|---|
| **动作** | 跑训练 → 调超参 → 看收敛 |
| **产物** | `TrainingRun{hyperparams, loss_curve, checkpoint, seed}` |
| **证据** | MECo 3.4 fine-tune Qwen2.5-Coder-7B |
| **门** | loss 收敛或验证指标达到可用 |
| **代码** | 训练日志 + checkpoint |

### P5 · Baseline 复现

| | |
|---|---|
| **动作** | 跑 baseline（同数据/同划分/同指标） |
| **产物** | `BaselineResult{method, metric_values, protocol}` |
| **证据** | MECo Table 1 的 Qwen2.5-7B-Instruct / -FT / Coder 三行 baseline |
| **门** | **同口径**：数据划分、指标定义、评测脚本一致 |
| **代码** | `run_baseline.py` |

### P6 · 主实验

| | |
|---|---|
| **动作** | 跑自己的方法 → 出对比表 |
| **产物** | `MainResultTable{methods[], metrics[], values}` |
| **证据** | MECo Table 1（99.9/98.3/98.3）；SynFlowNet 4.3 |
| **门** | ≥3 seeds；提升有显著性 |
| **代码** | `run_main.py` → CSV → LaTeX 表 |

### P7 · 消融与分析

| | |
|---|---|
| **动作** | 逐组件消融 + case study + 可视化 |
| **产物** | `AblationTable` + `CaseStudy` + `Figure`(t-SNE 等) |
| **证据** | AgentDrug 4.1/4.2（示例分子、迭代次数）；MECo 4.4 + Appendix Figure 6 t-SNE |
| **门** | **每个创新组件都有对应消融**；case 能复现 |
| **代码** | `run_ablation.py` |

### P8 · 图表制作

| | |
|---|---|
| **动作** | 架构图、结果图、case 图 |
| **产物** | `Figure{label, claim_ref, source_data}` |
| **证据** | MECo Figure 2A/2B（数据构造）、SynCraft 多图 |
| **门** | 每图绑定一条 claim；图能自解释 |
| **代码** | `plot_*.py` → PDF |

### P9 · 论文写作

| | |
|---|---|
| **动作** | 按 D5 venue 结构写各节（含方法节按 D1 流派变体） |
| **产物** | `SectionDraft`（每句可追溯到 claim/引用） |
| **证据** | MECo 全篇结构；Nature 系用 Results 替代 Experiments |
| **门** | 措辞 ≤ D2 证据允许上限；方法节结构与流派匹配 |
| **模板** | 见 §3 流派差异表 |

### P10 · 引用核验

| | |
|---|---|
| **动作** | 整理引用 → 三层核验（存在性/元数据/上下文） |
| **产物** | `CitationVerification{existence, metadata_ok, context_ok}` |
| **证据** | MECo References 约 100 条；必须逐条核 |
| **门** | 三层全 pass；无幻觉引用 |
| **代码** | `verify_citations.py` |

### P11 · 复现包与投稿

| | |
|---|---|
| **动作** | 打包代码/数据/环境/一键脚本 → 第三方验证 |
| **产物** | `ReproductionPackage{code, data, env, script, verification}` |
| **证据** | MECo Code availability；Nature 系 Data/Code availability |
| **门** | 第三方按 README 能跑出主表数值 |
| **代码** | `run.sh` + `environment.yml` |

## 3. 流派差异：同阶段做什么不同

| 阶段 | 编辑序列(MECo) | GFlowNet(SynFlowNet) | LLM agent(AgentDrug) | Nature(SynCraft) |
|---|---|---|---|---|
| P0 形式化 | 数学定义 + 旧形式缺陷 | MDP 定义（状态/动作/奖励） | **不写形式化**，写 workflow | 问题陈述 + 旧方法局限 |
| P1 架构 | 两模块（reasoning+coder） | 三要素（forward/backward/reward） | **无架构图**，画流程图 | 框架图 |
| P2 数据 | 合成+真实双轨 | 反应集合 + building blocks | **不造数据**（zero-shot） | 编辑序列数据 |
| P4 训练 | fine-tune 7B | 训练 GFlowNet | **不训练** | fine-tune |
| P6 主实验 | 执行准确率表 | 采样质量/多样性/rediscovery | evaluation 表 | Results 多小节 |
| P7 消融 | case study | MDP 一致性消融 | **组件+迭代次数** | 消融在 Results 里 |
| P9 写作 | Methods 5 子节 | Methods 3 子节 | Methodology 单节 | Results+Methods 后置 |

**这条表决定了 P9 的章节模板、P6 的指标选择、P7 的消融对象**——不能一套模板套所有论文。

## 4. 与上一版 12 阶段的差别

| 上一版（抽象） | 真实版 | 差别 |
|---|---|---|
| 01 问题锚定 | **P0 选题与问题形式化** | 加了「写数学形式化 + 指出旧形式缺陷」 |
| 02 领域学习 | 并入 P0/P1 | 读文献不是独立阶段，是 P0/P1 的输入 |
| 03 广域检索 | 并入 P0 | 同上 |
| 04 想法生成与证伪 | 并入 P0/P1 | 「想法」的物理形态就是 P0 的形式化 + P1 的架构 |
| 05 新颖性人择 | 并入 P1 门控 | 新颖性是 P1 的 `why_not_other` |
| 06 预注册方法 | **P1 + P9 的 Claim 冻结** | 方法锁 = P1 架构 + P9 措辞承诺 |
| 07 素材装配 | **P2–P7 六个阶段** | 这是上一版最大的错：把「造数据/写代码/训练/跑实验/消融」压成一个「素材装配」 |
| 08 起草 | P8 图表 + P9 写作 | 拆开图表制作和写作 |
| 09 拒稿论证 | 并入 P9/P10 门控 | 拒稿预演是写作时的自检，不是独立阶段 |
| 10 跨模型复审 | P10 引用核验 | 降级为核验 |
| 11 反驳响应 | 无需（投稿后） | — |
| 12 自检核验 | **P11 复现包** | 复现包是交付物，不是「自检」 |

**最大修正**：上一版把 P2–P7（造数据、写代码、训练、跑 baseline、主实验、消融）压缩成「阶段 07 素材装配」——这恰恰是真实科研 80% 的工作量。

## 5. 每阶段需要什么代码支撑

| 阶段 | 需要的代码 | 当前状态 |
|---|---|---|
| P0 | 无（但产出写入论文 3.1） | ❌ 无 `ProblemFormulation` 节点 |
| P1 | 架构图生成 | ❌ |
| P2 | `build_dataset.py` + 去泄漏检查 | ❌ 无 DatasetSpec 节点 |
| P3 | 模型/训练代码 | ⚠️ 只有 CodeFunction 抽取 |
| P4 | 训练脚本 + 日志 | ❌ |
| P5 | `run_baseline.py` | ❌ |
| P6 | `run_main.py` → CSV → LaTeX | ❌ |
| P7 | `run_ablation.py` + `plot_*.py` | ❌ |
| P8 | 图表脚本 | ❌ |
| P9 | 按流派模板生成 | ⚠️ 有 SectionPlan 但无流派模板 |
| P10 | `verify_citations.py` | ⚠️ 有 citation-audit skill |
| P11 | `run.sh` + env | ⚠️ 有 ReproductionPackage 节点 |

## 6. 结论

**真实流程的核心是 P2–P7 这 6 个「动手」阶段**，它们产出的不是文本，而是：

```
DatasetSpec → 数据文件
CodeArtifact → 代码
TrainingRun → checkpoint + loss 曲线
BaselineResult → 数值
MainResultTable → 表格
AblationTable + CaseStudy → 表格 + 图
```

**上一版把这 6 个压成一个「素材装配」，是根本性错误。** 论文不是写出来的，是这 6 步做出来的——写作只是把已经存在的东西组织成文。

下一步应该先建 **P2（数据构造）和 P3（代码实现）** 的节点与流程，因为它们是唯一无法用现有知识层替代的部分。
