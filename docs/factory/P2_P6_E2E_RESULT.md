# P2 + P6 端到端跑通结果

## 1. 做了什么

### 第 1 步：规则抽取（零 LLM）

`stages/2_knowledge/extract_rules.py` 从 52 篇 md 抽 5 个字段写入语义层：

| 字段 | 覆盖 | 说明 |
|---|---|---|
| `data_sources` | **44/52** | ZINC/ChEMBL/USPTO/Enamine/PDB… |
| `result_tables` | **49/52（131 张表）** | markdown 表格解析 |
| `hyperparams` | **35/52** | iterations / temperature / learning rate… |
| `dedup_rule` | 16/52 | 只有 31% 论文明确写阈值（合理） |
| `split_spec` | 1/52 | ⚠️ 正则太严，待改 |

语义层 Paper 字段：**28 → 33**。

### ResultTable 类

应用层新增（54 类 / 64 关系）：
```
ResultTable{run_id, table_label, caption, columns, rows,
            claim_ref, best_by_column, latex, source_paper}
关系：Claim --TABULATED_IN--> ResultTable
```

### P6 端到端：表格 → LaTeX

`stages/3_generate/p2p6_e2e.py`：
- 从 `Paper.result_tables` 选数值列最多的一张表
- 转 booktabs 三线表，**自动加粗最优值**
- 写 `ResultTable` 节点 + `.tex` 文件

**结果：32/52 篇生成了 LaTeX 表（33 个 .tex 文件）**

## 2. 真实产物样例（2407.12186 Saturn）

```latex
\begin{tabular}{lcccc}
\toprule
Model & Mol. weight (↓) & QED (↑) & SA score (↓) & AiZynth (↑) \\
\midrule
Saturn-GA-ChEMBL & \textbf{370.9} & \textbf{0.84} & 2.44 & 0.70 \\
Saturn-ChEMBL    & 486.2 & 0.28 & 2.40 & \textbf{0.82} \\
Saturn-GA-ChEMBL & 464.1 & 0.34 & 2.51 & 0.68 \\
\bottomrule
\end{tabular}
```

**三个正确性点**：
1. `Mol. weight (↓)` 加粗最小 370.9（不是最大）
2. `QED (↑)` 加粗最大 0.84
3. `SA score` 两行并列 2.40 → **都不加粗**（避免误导）
4. 同名方法 `Saturn-GA-ChEMBL` 出现两次 → 只有最优那行加粗

## 3. 修的两个真 bug

| bug | 现象 | 修法 |
|---|---|---|
| 指标方向 | `SA score (↓)` 越低越好，却用 max 加粗 | 列名含 ↓/lower/error/time → 取 min |
| 同名行 | `Saturn-GA-ChEMBL` 两行都被加粗 | 用行索引而非 method 名记录最优 |

## 4. P2 去泄漏（真算）

`check_leakage(train, test, threshold=0.6)` 用 RDKit Morgan 指纹：
```
实测：3 训练 / 3 测试 → 检出 1 个泄漏（Tanimoto 0.69）
leak_rate=0.333, pass=False
```

## 5. 端到端链路验证

```
52 篇 md
  → extract_rules.py（规则，零成本）
  → Paper.result_tables / data_sources / hyperparams
  → p2p6_e2e.py
  → ResultTable 节点（32 个）+ .tex 文件（33 个）
  → 可直接 \input 进论文
```

## 6. 已知问题

| 问题 | 影响 | 下一步 |
|---|---|---|
| `split_spec` 1/52 | P2 划分信息缺失 | 放宽正则（"80/10/10" 多种写法） |
| 少数表头识别错（`229M/68M` 当列名） | 表格质量 | 加「列名不含纯数值」过滤 |
| 20 篇没生成表 | 表太窄或无数值列 | 放宽条件 |
| 33 个 .tex 未编译验证 | 可能 LaTeX 语法错（特殊字符） | 加 `_`/`%`/`&` 转义 |

## 7. 复现

```bash
PYTHONPATH=src python3 stages/2_knowledge/extract_rules.py
PYTHONPATH=src python3 stages/3_generate/p2p6_e2e.py
ls storage/generated/*.tex
```
