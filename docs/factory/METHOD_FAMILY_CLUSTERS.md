# 面向算法发现的社区分类（LLM 标题 + 方法流派）

> 回答两个问题：① LLM 怎么写社区标题；② 为什么 `problem_category` 分类不适合算法设计。

## 1. 为什么原来的分类不对

用户指出 `2512.20333 SynCraft`（分子编辑流派）在现有分类里找不到——因为它被标成
`molecule_optimization`，而 SynCraft 的本质是**编辑序列优化**，这是一个方法流派，不是问题类型。

| 现有维度 | 回答的问题 | 对算法设计有用吗 |
|---|---|---|
| `problem_category` = molecule_optimization | 这篇论文在做优化 | ❌ 太粗，50% 论文都在这类，无法判断「借鉴谁」 |
| `evidence_type` = experimental | 认什么证据 | ❌ 是评价标准，不是方法 |
| A–F 目录名（合成性/编辑/agent/逆合成） | 批量导入的粗略主题 | ❌ 和论文真实方法不完全一致（如 D 目录里混入 LLM 论文） |

**算法设计需要的分类是「用什么机制解决问题」**——即 method family。

## 2. 方法流派分类法（10 个流派）

`src/capfactory/applayer/method_taxonomy.py`：

| family | 名称 | 判别关键词（部分） | 对算法设计的意义 |
|---|---|---|---|
| `edit_sequence` | 编辑序列优化 | edit sequence / atom edit / syncraft / meco | 局部可控、增量设计 |
| `gflownet` | GFlowNet / 生成流 | gflownet / synflownet / rgfn / s3-gfn | 按奖励比例采样、多样性 |
| `diffusion_flow` | 扩散 / 流模型 | diffusion / discrete flow / field-based | 状态演化建模 |
| `llm_agent` | LLM 多智能体 / 工具编排 | multi-agent / tool-grounded / agentdrug / m3os | 自动化流程与协同 |
| `llm_frozen_incontext` | LLM 冻结 / 上下文学习 | in-context / prompt / zero-shot | 快速试错、低数据 |
| `llm_finetuned` | LLM 微调 | fine-tun / lora / synllama / stamp | 结构化输出、领域适配 |
| `retro_search` | 搜索式逆合成 | retrosynthesis / mcts / desp / retroplanner | 可解释合成路线 |
| `rule_symbolic` | 规则 / 符号系统 | shacl / datalog / owl / inference | 正确性保证、KG 治理 |
| `property_surrogate` | 性质预测 / 代理模型 | property prediction / qed / oracle | 优化目标的代理 |
| `benchmark_eval` | 评测 / 验证框架 | benchmark / audit / safety / trace | 门控与反馈信号 |

**52 篇标注结果**（规则优先，剩余 2 篇 unclassified）：

```
llm_agent 11 · retro_search 11 · rule_symbolic 8 · benchmark_eval 6
edit_sequence 4 · gflownet 3 · diffusion_flow 3 · llm_finetuned 3 · property_surrogate 1
```

SynCraft 正确归到 `edit_sequence` ✅；MECo 同流派 ✅；SynFlowNet/RGFN/S3-GFN 归 gflownet ✅。

## 3. LLM 怎么写社区标题（具体做法）

### 3.1 流程

```
① 特征图加入 method_family（权重 ×3，重复 3 次进入 Jaccard）
② Leiden (seed=42, resolution=1.0) → 4 个社区
③ 每个社区统计 findings（证据类型/问题类别/指标）
④ LLM prompt = 主导流派 + findings + 5 篇代表论文标题
   → 输出 {title, rationale, design_hint}
⑤ 限流时兜底：{流派中文名}·{主导问题}
```

### 3.2 Prompt（实际用的）

```
你是分子算法设计专家。根据一个论文社区的特征，输出该社区的方法流派名和算法设计启发。
只输出JSON：{"title":"6-12字流派名","rationale":"一句话解释",
"design_hint":"这个流派对后续算法设计的启发"}

主导方法流派：llm_agent（必须体现在标题中，且不同流派标题不能重复）
特征：问题类别: molecule_optimization(13) | 指标: QED(3), accuracy(1)...
代表论文：...SynCraft...；...MECo...；...MultiMol...
```

### 3.3 关键设计点

1. **必须告诉 LLM 主导流派**——第一次没注入，两个不同流派社区都写成「可合成性约束生成」
2. **必须 design_hint 字段**——这不只是标题，而是「这个流派对我设计算法有什么用」
3. **限流兜底用中文流派名**——`METHOD_FAMILIES[fid][0]`，不用英文 id
4. **固定 seed=42**——Leiden 每次运行划分会变（17/14/14/7 → 15/14/12/11 → 17/13/12/10），不可复现

## 4. 实测结果（4 个社区）

| 社区 | n | 主导流派 | LLM 标题 | design_hint（节选） |
|---|---:|---|---|---|
| 0 | 17 | llm_agent | LLM智能体分子优化 | 以LLM为规划核心，工具调用+多智能体分工+迭代反馈闭环 |
| 1 | 13 | retro_search | 逆合成搜索引导生成 | 把逆合成搜索作为可微奖励/硬约束与生成策略联合优化 |
| 2 | 12 | rule_symbolic | 规则符号约束验证 | 规则编译、约束传播、增量验证，提升效率与可解释性 |
| 3 | 10 | retro_search | 双向目标逆合成搜索 | 融合双向搜索与可合成性反馈，断键规则约束分支扩展 |

**对比原来的 5 个社区**（molecule_optimization / molecule_generation / reaction_prediction / other ×2）：
- 原分类是「论文在做什么」，新分类是「用什么机制」——后者才能回答「我该借鉴谁」
- SynCraft 现在和 MultiMol/MT-MOL 同社区（LLM 编辑流派），不再混在 13 篇泛 optimization 里

## 5. 对后续步骤的价值

### 算法发现
```
输入问题：「如何做可控的 3D 分子编辑？」
→ 查 method_family=edit_sequence 社区 → 得到 SynCraft/MECo 的 design_hint
→ GapTriple.frontier_baseline = "SynCraft/MECo 编辑序列流派"
→ IdeaCandidate 就能基于同流派做增量，而不是凭空想
```

### 跨流派组合
```
社区0(LLM agent) 的 design_hint 说「工具调用连接编辑模块」
社区1(retro_search) 说「逆合成作为可微奖励」
→ IdeaCandidate：LLM agent 调用逆合成工具作为奖励信号
   ← 这就是跨流派组合，有明确出处
```

### 门控
```
Community.rating（0.5-0.8）→ 决策置信度
design_hint → 注入 prompt 作为「领域设计规范」
```

## 6. 局限与下一步

- Ernie 免费模型限流频繁（4 次调用只有 2 次成功），生产用应配 vLLM 兜底或缓存标题
- `llm_agent` 和 `retro_search` 社区仍较大（17/13），可提 resolution 到 1.5 再细分
- 标题稳定性：固定 seed 后社区划分稳定，但 LLM 限流会使标题在「LLM生成」和「规则兜底」间跳动
- 2 篇 unclassified 需要人工确认或扩展词表

## 7. 产物与复现

```
src/capfactory/applayer/method_taxonomy.py        10 个流派定义
stages/2_knowledge/annotate_methods.py             52 篇标注 + 标题修正
stages/2_knowledge/build_method_communities.py     流派社区 + LLM 标题
storage/sciforge/factory_knowledge_annotated.json  带 method_family 的图
storage/sciforge/factory_knowledge_method_communities.json  378 节点/485 断言
storage/sciforge/method_communities.json           4 个社区完整报告
```

```bash
PYTHONPATH=src /home/zengshuxin/xKG-main/xKG-main/.venv-linux/bin/python \
  stages/2_knowledge/annotate_methods.py
PYTHONPATH=src /home/zengshuxin/xKG-main/xKG-main/.venv-linux/bin/python \
  stages/2_knowledge/build_method_communities.py
```
