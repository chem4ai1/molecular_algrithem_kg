# 集成验证报告（v2）

生成时间：2026-11-19T01:34:51Z

## 16 个硬门

| 门 | 结果 |
|---|---|
| H1_语义层冻结 | PASS |
| H2_重建等价 | FAIL |
| H3_基础契约 | FAIL |
| H4_缓存幂等 | PASS |
| H5_LLM节点隔离 | PASS |
| H6_spec幂等 | PASS |
| H7_门完整 | PASS |
| H8_回写可追溯 | PASS |
| H9_API注册 | PASS |
| H10_冒烟 | PASS |
| H11_回归 | PASS |
| H12_信号零丢失 | PASS |
| H13_决定可追溯 | PASS |
| H14_人类主权 | PASS |
| H15_决定可传播 | PASS |
| H16_覆盖率可见 | PASS |

## 12 项指标

| 指标 | 实测 |
|---|---|
| cache_hit_rate | `0.0` |
| llm_call_reduction | `0.0` |
| n_new_nodes_per_run | `{'n_proposals': 0, 'n_registered': 0, 'n_signals': 2}` |
| promotion_rate | `0.0` |
| semantic_graph_hash_stable | `True` |
| rebuild_equivalence | `False` |
| provenance_coverage | `1.0` |
| stale_recompute_scope | `0.0` |
| signal_capture_rate | `1.0` |
| decision_propagation_rate | `1.0` |
| mining_coverage_ratio | `0.9091` |
| exploration_regret | `0` |
| n_active_human_decisions | `0` |

## 修正闭环

共 10 条，状态 closed。

| id | 阶段 | 触发信号 | 修法 | 测试 |
|---|---|---|---|---|
| C1 | S0 | API 模块漏注册导致静默 404 | paperapp_api 加入 WEB_API_MODULES；/api/status 暴露错误 | T-S5-01 |
| C2 | S0 | graph_source 读的是 batch10_app_v1.json | 独立 /graph/nodes 直读 app_generation.json，不改 graph_source | T-S5-10 |
| C3 | S1 | flock 嵌套自锁导致 materialize 挂死 | util.with_lock 改为可重入（thread-local 深度计数） | T-S4-14 |
| C4 | S1 | verdict() 不接受 reason_code | 按真实签名用 notes，并附加 reason_code/state 字段 | T-S0-09 |
| C5 | S2 | 中文词元被拆单字造伪数据流 | miners._as_list 按分隔符切分、字符串整体作词元 | T-V2-10 |
| C6 | S3 | gate 超时被前端自动通过 | hitl.decide 超时返回 BLOCKED + verdict 文件 | T-V2-15 |
| C7 | S4 | 增量结果与全量重建分叉 | materialize.verify 校验语义层投影 + 注册项，DRIFT 拒写 | T-S4-05 |
| C8 | S5 | tab 动态生成导致静态可访问性为 0 | 7 个 tab 静态 HTML + route 只更新 aria-selected | T-S5-02 |
| C9 | S1 | tests/ 非包导致模块路径导入失败 | 统一用 unittest discover -s tests | 全阶段 |
| C10 | S1 | 提案缺 paper_id/stage 字段 | schemas.LLMNodeProposal 补齐两个字段 | T-V2-09 |
