# 全量论文知识抽取：后台运行说明

## 状态（启动时）
- 论文总数 783 篇（data/docx/*.md），已完成 18，剩余 765，失败 0
- 2 个后台分片：shard 0/2 与 1/2，PID 见 /tmp/batch_0.pid /tmp/batch_1.pid
- 约 90-105 秒每篇每分片，2 并发预计 9-11 小时跑完

## 断点续跑设计
脚本 capfactory/semantic/batch_extract.py 用 nohup 独立运行。每篇完成即写报告并原子写 state；
中断后重跑自动跳过已经 ok 的报告。两分片独立 state 避免冲突；收尾要求 remaining==0 且拿
fcntl.flock 文件锁，保证只有一次回填/重建。

## 查进度
.venv-linux/bin/python -m capfactory.semantic.batch_extract --status
curl http://127.0.0.1:8091/api/v8/extraction/batch-status
tail -f storage_cf/sciforge/semantic_extraction/_batch_extract.log

返回 total / done / failed / remaining / shards[]。phase=extracting 抽取中，
finalizing 回填重建，done 全部完成。failed 非 0 时重跑会自动重试。

## 收尾自动执行
1. semantic.apply.apply_all()：写 E1/E2/E3 属性、E4 追加 model_results、
   E2 的 code_symbols 对齐 CodeFunction 建 MODULE_IMPLEMENTED_BY（代码联系）、E6 建谱系边。
2. semantic.refresh.refresh_all()：溯源修复、provenance 索引、缺失 CSV、
   关系索引、全量向量索引、应用层图重建。
3. 写 phase=done 与总耗时。

## 中断后续跑
nohup .venv-linux/bin/python -m capfactory.semantic.batch_extract --shard 0 --n-shards 2 > /tmp/batch_0.out 2>&1 &
nohup .venv-linux/bin/python -m capfactory.semantic.batch_extract --shard 1 --n-shards 2 > /tmp/batch_1.out 2>&1 &

限量试用：--limit 20 --n-shards 1。若两分片同时调 vllm 显存吃紧，停一个用单进程续跑。

## 产物
storage_cf/sciforge/semantic_extraction/<aid>.json  每篇报告（含 paradigm 范式层）
storage_cf/sciforge/semantic_extraction/_batch_state_0of2.json 与 _1of2.json  分片进度
storage_cf/sciforge/semantic_extraction/_batch_extract.log  逐篇日志
storage_cf/sciforge/batch10_semantic_v4.json  收尾后更新的语义层图
storage_cf/sciforge/batch10_app_v1.json  收尾后重建的应用层图
storage_cf/semantic/vector/nodes.npy  收尾后重建的向量索引
storage_cf/sciforge/provenance/*.csv  收尾后更新的缺失论文清单

## 注意
后台进程加载启动时的代码，之后改的 runner 原子写在下次续跑生效。
全量完成后不要手工改语义层图再重启批跑，会与 apply_all 冲突。


## 8. 实际完成情况（2026-11-14 16:30 补记）

抽取阶段在 14:54 全部跑完：783/783，ok 764（97.6%），not_ok 19，failed 0。
两个分片 phase=done 正常退出，共耗时约 12.5 小时（2 并发）。

**收尾首次失败**：apply_all 用 *.json glob 时把 vocab.json / _batch_state_*.json
当成抽取报告，触发 KeyError: arxiv_id。修复为只处理 <arxiv_id>.json。

**修复后重跑收尾**（从回填前备份图重建），并补了三处真实缺陷：
1. 783 篇里多数 Paper 不在图内，apply_one 只查不建 → 新增 _ensure_paper
   （标题从 md 首个标题行提取）；
2. E2 只建 HAS_MODULE 没建 PROPOSES_METHOD → 补建，repair 又补 886 条；
3. 新建 Paper 缺 domain 中文名 → 用 domain_code 映射回填 772 篇。

**最终规模**：
语义层 6001 节点 / 7460 断言；应用层 9100 节点 / 11826 关系；
关系索引 3030 实例 / 5343 关系；向量索引 6001×1024；
缺论文 CSV：算法 0、基准 14（全是预置知识库基准）；
溯源覆盖：算法 100%、基准 97.7%。
审计接口经 O(N^2)→O(N+E) 优化，从超时降到 1.18s。
