# A/B 抽取对照：30 字段一次 vs 规则+LLM 分层

> 4 篇不同流派论文，旧方案（E1 30 字段一次 / E2 13 字段）vs 新方案（E1 14 LLM + 8 规则 / E2 8 LLM）。
> 都用 vLLM，同一篇文章，对照字段完整度与原文吻合度。

## 1. 改动内容

| | 旧方案 | 新方案 |
|---|---|---|
| E1 LLM 字段 | 30 | **14**（语义字段） |
| E1 规则字段 | 6 | **8**（+figures） |
| E2 LLM 字段 | 13 | **8**（去掉低价值/难点字段） |
| 模板 | 大段字段说明 | 紧凑 JSON 示例 + 明确「不抽这些」（交规则） |

**LLM 保留的 14 个 E1 字段**：research_question / problem_category / why_hard / relation_hints /
paradigm / evidence_type / evidence_norm / section_map / writing_style /
claims / gaps / delta_claims / method_limits / old_forms

**交给规则的 8 个**：data_sources / dedup_rule / split_spec / hyperparams /
result_tables / formal_def / figures（+ preprocess=normalize_pdf）

**E2 精简到 8 个**：name / task_type / mechanism / limitations / modules /
arch_modules / key_challenge / why_not_other

## 2. 字段完整度对照

| 论文 | 方案 | research_q | claims | limits | old_forms | arch_mod | key_chal |
|---|---|---:|---:|---:|---:|---:|---:|
| MECo | 旧 | 51 | 2 | 3 | 1 | 3 | 36 |
| MECo | **新** | 31 | 2 | 3 | 1 | 1 | **42** |
| SynFlowNet | 旧 | 49 | 2 | 3 | 2 | 1 | 26 |
| SynFlowNet | **新** | 41 | 2 | 2 | 2 | **2** | **43** |
| AgentDrug | 旧 | 47 | 2 | 2 | **0** | 3 | 55 |
| AgentDrug | **新** | 32 | 2 | 2 | **2** | 2 | **60** |
| SHACL | 旧 | 49 | 2 | 1 | **0** | 2 | 36 |
| SHACL | **新** | 48 | 2 | 1 | **1** | 1 | **52** |

## 3. 结论：有得有失，不是全面变好

### 明显变好 ✅

1. **`old_forms` 从 0 → 2 篇**：AgentDrug 和 SHACL 旧方案完全抽不到，新方案都抽到了
   ——证明「减少字段数 + 明确要求」确实让模型不再忽略低优先级字段
2. **`key_challenge` 平均变长**：MECo 36→42、SynFlowNet 26→43、SHACL 36→52 字
   ——更具体，不是泛泛而谈
3. **`method_limits` 全部保留**：4 篇都有（1–3 条），精简没有牺牲关键字段
4. **`ok=True` 率 4/4**——三次重试内全部成功

### 变差 ⚠️

1. **`research_question` 变短**：MECo 51→31、AgentDrug 47→32 字
   ——新模板要求「一句话」，模型过度压缩，丢了细节
2. **`arch_modules` 数量下降**：MECo 3→1、AgentDrug 3→2
   ——E2 精简后，模型把系统模块合并成更粗粒度（MECo 只输出 1 个「MECo Framework」）

### 基本不变 =

`claims` 全部 2 条——这是模型的稳定上限，不是字段数问题。

## 4. 与原文吻合度（新方案 MECo 逐项）

```
research_question: 如何通过代码生成解决LLM在分子编辑中意图与执行不一致的问题？
                   ← 抓住 3.1 核心 ✅（虽比旧方案短）
why_hard:          SMILES线性表示与分子图结构存在模态不匹配...
                   ← 精准复述 3.1 对 SMILES 的批评 ✅
method_limits:     ['generated SMILES may not always be chemically plausible',
                    'valid outputs may diverge from the design rationale...',
                    'extensive uncontrolled edits may severely compromise...']
                   ← 三条对应 MECo 3.1 原文 ✅
arch_modules:      [('MECo Framework', '桥接推理与执行')]
                   ← ⚠️ 太粗，原文是 reasoning LLM + code LLM 两个模块
key_challenge:     SMILES线性表示与化学图结构推理之间的模态不匹配...
                   ← 精准（旧方案 36 字，新方案 42 字更完整）✅
```

**判断**：语义字段更准，但 `arch_modules` 粒度退化。

## 5. 调整建议

| 问题 | 修法 |
|---|---|
| `research_question` 太短 | 模板里把「一句话」改成「1–2 句，包含主体与矛盾」 |
| `arch_modules` 太粗 | E2 模板强调「列出原文提到的每个系统组件，不要合并」 |
| `figures` 规则没命中 | MECo md 用 HTML 图片标签，规则需加 `<img>` 与 `<!-- Start of picture text -->` 模式 |

## 6. 过程中修的两个真 bug

1. **备份文件被当 stage 加载**：`E1_paper_v1bak.yaml` 放在 stages/ 下，被 loader 扫描并**覆盖**了新配置——
   导致第一版改动"看起来改了实际没生效"。已移到 `_backup/` 目录。
2. **新 template 漏了 `{paper_text}`**：重写模板时没放正文占位符，LLM 看不到论文，全部填空 JSON，
   4 篇 ok=False。loader 只检查「声明的占位符必须存在」，不检查「声明了但没用」——检查盲区，待补。

## 7. 复现

```bash
PYTHONPATH=src python3 /tmp/run_ab.py
cat storage/ab.log
```
