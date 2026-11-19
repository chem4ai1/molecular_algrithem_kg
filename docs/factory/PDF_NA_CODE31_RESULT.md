# PDF 表格修复 + readiness NA + data3 代码节点 31 篇扩展

## 1. PDF→md 保留表格

新增 `stages/1_extraction/pdf_to_md_data3.py`：

- 用 PyMuPDF `find_tables()` 抽取 PDF 表格
- 排除表格区域的普通文本，避免重复
- 表格转为 markdown 管道表
- 全部 31 篇 data3 PDF 已重转到 `data/docx/<aid>.md`

转换统计中关键两篇：

```text
2505.23628 AutoSchemaKG: 26 页 / 11 张表 / 103272 字符
2607.01977 OntoLearner : 30 页 / 9 张表  / 151254 字符
```

重抽这两篇后：

```text
2505.23628: P0=READY P1=READY P2=PARTIAL P6=READY P7=READY
2607.01977: P0=READY P1=READY P2=READY   P6=READY P7=READY
```

**P6 从 BLOCKED 变 READY**——表格修复生效。

## 2. readiness 支持 NA

`data/extract_target/readiness.yaml` 新增 `na_rules`：

- `formal/interpretive` 范式下，数据构造相关字段可 NA
- 摘要/标题含 `zero-shot`、`survey`、`review`、`taxonomy` 等信号时可 NA
- 状态新增 `READY_NA`

逻辑：

```
critical 缺但不是 NA → BLOCKED
any_of 缺但全组 NA   → READY_NA
非关键缺但非 NA     → PARTIAL
无缺               → READY
```

同时新增 `extraction_status`：

- `proxy`：data3 只有元数据、还未语义抽取，不计入 readiness
- `extracted`：已应用 E1/E2 报告，计入审计

当前主图审计（54 篇已抽取论文）：

```text
P0: READY 6/54   READY_NA 0  BLOCKED 48
P1: READY 6/54   READY_NA 0  BLOCKED 48
P2: READY 29/54  READY_NA 5  PARTIAL 20  BLOCKED 0
P6: READY 50/54  READY_NA 0  BLOCKED 4
P7: READY 6/54   READY_NA 0  BLOCKED 48
```

P2 已经没有 BLOCKED。

## 3. data3 代码节点扩展到 31 篇

更新 `stages/2_knowledge/extract_code_nodes.py`：

- 31 篇论文全部建 `Paper` proxy（其中 2 篇已抽取，29 篇新 proxy）
- 48 个本地仓库全部建 `CodeRepository`
- 论文-仓库关联：
  - 8 条用 manifest `[owner/repo]` 精确匹配
  - 5 条用标题 token 弱匹配（标记 `title_token_weak`）
  - 18 条未匹配（不强行猜）
- 每个仓库抽取：
  - `CodeArtifact`
  - `CodeUnit`（.py 文件）
  - `CodeSymbol` / `CodeFunction`
  - `Dependency`
  - `EntryPoint`
  - `EnvSpec`
  - `TestUnit`

结果：

```json
{
  "before": {"nodes": 405, "assertions": 463},
  "after":  {"nodes": 2686, "assertions": 2496},
  "stat": {
    "papers_all": 29,
    "repos_all": 48,
    "links_exact": 8,
    "links_weak": 5,
    "links_unmatched": 18,
    "functions": 772,
    "codeunits": 273,
    "symbols": 772,
    "deps": 204,
    "entrypoints": 83,
    "env": 20,
    "aligned_modules": 63
  }
}
```

节点总数：

```text
Paper 83（52 原 + 31 data3）
CodeRepository 48
CodeFunction 772
CodeArtifact 48
CodeUnit 273
CodeSymbol 772
Dependency 204
EntryPoint 83
EnvSpec 20
TestUnit 32
```

所有代码节点都有 `source` 和 `miner=code_extract`。

## 4. Algorithm / AlgorithmModule 对齐

对齐规则：

```
Paper --PROPOSES_METHOD--> Algorithm --HAS_MODULE--> AlgorithmModule
      ↓ 模块名 token 与 CodeSymbol/CodeFunction 名匹配
AlgorithmModule --MODULE_IMPLEMENTED_BY--> CodeFunction
AlgorithmModule --IMPLEMENTED_BY--> CodeSymbol
```

结果：

```text
aligned_modules = 63
```

注意：
- 只有已经应用过 E1/E2、存在 Algorithm/Module 的论文才能对齐
- 大部分 data3 论文目前还是 proxy，没有 Algorithm 节点，所以还没法对齐
- 这 63 条是“尝试对齐”，不是强绑定；匹配结果写在模块的 `implementation_match` 属性里

## 5. 当前结论

三项任务完成：

1. **PDF 表格保留**：data3 论文 P6 不再因表格缺失 BLOCKED
2. **readiness NA**：原文不需要的字段不再误判成 PARTIAL/BLOCKED
3. **代码节点 31 篇**：48 仓库、772 函数、63 个模块对齐

但全量语义抽取还没开始。当前主图状态：

- 54 篇已抽取论文：6 篇 P0/P1/P7 READY，其余仍是旧抽取
- 29 篇 data3 论文只有元数据 proxy，尚未 E1/E2 抽取
- P2 已无 BLOCKED
- P6 仍有 4 篇旧论文 BLOCKED（老报告缺 result_tables）

下一步才适合启动真正全量：

```
data3 29 篇 proxy → E1/E2 抽取
原 52 篇 → 用新模板全量重抽
合并所有报告 → 统一主图 → readiness
```
