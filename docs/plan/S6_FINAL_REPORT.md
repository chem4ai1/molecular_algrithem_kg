# S6 最终验收签字（v2）

生成时间：2026-11-18T14:48:22Z

## 16 硬门实测

| 门 | 判据 | 实测 |
|---|---|---|
| H1_语义层冻结 | 见 plan/README.md §5 / §10.3 | PASS |
| H2_重建等价 | 见 plan/README.md §5 / §10.3 | FAIL |
| H3_基础契约 | 见 plan/README.md §5 / §10.3 | FAIL |
| H4_缓存幂等 | 见 plan/README.md §5 / §10.3 | PASS |
| H5_LLM节点隔离 | 见 plan/README.md §5 / §10.3 | PASS |
| H6_spec幂等 | 见 plan/README.md §5 / §10.3 | PASS |
| H7_门完整 | 见 plan/README.md §5 / §10.3 | PASS |
| H8_回写可追溯 | 见 plan/README.md §5 / §10.3 | PASS |
| H9_API注册 | 见 plan/README.md §5 / §10.3 | PASS |
| H10_冒烟 | 见 plan/README.md §5 / §10.3 | PASS |
| H11_回归 | 见 plan/README.md §5 / §10.3 | PASS |
| H12_信号零丢失 | 见 plan/README.md §5 / §10.3 | PASS |
| H13_决定可追溯 | 见 plan/README.md §5 / §10.3 | PASS |
| H14_人类主权 | 见 plan/README.md §5 / §10.3 | PASS |
| H15_决定可传播 | 见 plan/README.md §5 / §10.3 | PASS |
| H16_覆盖率可见 | 见 plan/README.md §5 / §10.3 | PASS |

## 12 指标实测

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

## 人工签字项（需人工确认）

- [ ] 语义层仍为 6 类 / 9 关系，`batch10_semantic_v4.json` sha 与基线一致
- [ ] `vocab.py` / `research/gaps.py` / `applayer/miner.py` 的既有行为未被修改
- [ ] `human_boost_cap=0.0`、`gate_timeout_policy=BLOCKED`
- [ ] 所有被拒 / 被 supersede 的信号与决定仍可查询（append-only）
- [ ] `bash scripts/test_all.sh` 一键复现本报告

