"""S2 + v2-S2 验证：PaperSpec 幂等、D1–D4 派生、人类思路、覆盖率。"""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.paperapp import (config, coverage, hitl, miners, paperspec,
                                 registry, tbox, util)


class _N:
    def __init__(self, t, attrs=None):
        self.type, self.attrs = t, dict(attrs or {})


class _A:
    def __init__(self, s, t, r, props=None):
        self.source, self.target, self.relation = s, t, r
        self.properties = dict(props or {})


class _G:
    def __init__(self, nodes, edges):
        self.nodes, self.assertions = nodes, edges


def graph():
    nodes = {
        "paper:a": _N("Paper", {"title": "A", "year": 2024}),
        "paper:b": _N("Paper", {"title": "B", "year": 2025,
                                "open_problems": ["x"]}),
        "alg:m": _N("Algorithm", {"name": "M"}),
        "mod:x": _N("AlgorithmModule", {"inputs": "完整分子结构",
                                        "outputs": "片段集合及其原子索引映射"}),
        "mod:y": _N("AlgorithmModule", {"inputs": "片段集合及其原子索引映射",
                                        "outputs": "潜在向量 z"}),
        "bench:z": _N("Benchmark", {"metrics": ["validity"]}),
        "fn:1": _N("CodeFunction", {"file": "src/a.py", "name": "f1"}),
        "fn:2": _N("CodeFunction", {"file": "src/a.py", "name": "f2"}),
    }
    edges = [_A("paper:a", "paper:b", "RELATED_TO"),
             _A("alg:m", "bench:z", "EVALUATED_ON"),
             _A("paper:a", "alg:m", "PROPOSES_METHOD")]
    return _G(nodes, edges)


class TestS2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.lock = mock.patch.object(config, "LOCK_FILE", self.d / ".lock")
        self.lock.start()
        registry.seed_defaults(out_dir=self.d, approver="test:s2")
        hitl.seed_choices(out_dir=self.d)
        coverage.build(out_dir=self.d)

    def tearDown(self):
        self.lock.stop()
        self.tmp.cleanup()

    def test_t_s2_01_phasegraph(self):
        self.assertEqual(len(tbox.stage_defs()), 26)
        self.assertEqual(tbox.validate_phasegraph(), [])
        self.assertEqual(len(tbox.CHOICEPOINTS), 14)
        self.assertIn("3", tbox.GATE_STAGES)

    def test_t_s2_02_spec_idempotent(self):
        s1 = paperspec.compile_paperspec(graph(), paper_id="paper:a", out_dir=self.d)
        s2 = paperspec.compile_paperspec(graph(), paper_id="paper:a", out_dir=self.d)
        self.assertEqual(s1.spec_hash, s2.spec_hash)
        self.assertTrue(s1.spec_hash.startswith("sha256:"))

    def test_t_s2_03_zero_llm(self):
        import inspect
        src = inspect.getsource(paperspec.compile_paperspec)
        for banned in ("chat", "llm(", "openai", "BgeEmbedder"):
            self.assertNotIn(banned, src)

    def test_t_v2_13_decision_changes_spec_hash(self):
        s1 = paperspec.compile_paperspec(graph(), paper_id="paper:a", out_dir=self.d)
        r = hitl.decide("6", "theory-only", approver="human:z", out_dir=self.d)
        self.assertTrue(r["ok"])
        hitl.reinject(out_dir=self.d)
        s2 = paperspec.compile_paperspec(graph(), paper_id="paper:a", out_dir=self.d)
        self.assertNotEqual(s1.spec_hash, s2.spec_hash)
        self.assertEqual(len(s2.human_decisions), 1)

    def test_t_v2_10_d1_chinese_tokens_not_split(self):
        d = miners.D1_flow_closure(graph())
        self.assertEqual(d["n_edges"], 1)
        self.assertEqual(d["edges"][0]["token"], "片段集合及其原子索引映射")
        self.assertEqual(d["n_cycles"], 0)

    def test_t_v2_11_human_hypothesis_requires_gap(self):
        r = miners.inject_human_hypothesis(
            {"statement": "换用扩散采样", "falsifiable_claim": "指标下降 > 5%"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "missing_gap_anchor")
        r2 = miners.inject_human_hypothesis(
            {"statement": "换用扩散采样", "falsifiable_claim": "指标下降 > 5%",
             "gap_anchor": "GAP-01"})
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["origin"], "human")
        self.assertTrue(r2["same_weight_as_machine"])

    def test_t_v2_12_human_boost_capped(self):
        self.assertEqual(config.HUMAN_BOOST_CAP, 0.0)
        r = miners.inject_human_hypothesis(
            {"statement": "s", "falsifiable_claim": "c", "gap_anchor": "g"}, boost=9)
        self.assertEqual(r["hypothesis"]["boost"], 0.0)

    def test_t_v2_14_existing_miners_untouched(self):
        from capfactory.applayer import miner
        self.assertTrue(hasattr(miner, "mine_all"))
        d = miners.run_derived(graph())
        self.assertEqual(d["n_miners"], 4)
        for k, v in d["derived"].items():
            self.assertEqual(v.get("provenance"), "deterministic")

    def test_d2_structural_gaps(self):
        d = miners.D2_method_benchmark_matrix(graph())
        self.assertEqual(d["n_cells"], 1)
        self.assertEqual(d["n_gaps"], 0)     # alg:m 已 EVALUATED_ON bench:z
        g2 = graph()
        g2.assertions = [a for a in g2.assertions if a.relation != "EVALUATED_ON"]
        self.assertEqual(miners.D2_method_benchmark_matrix(g2)["n_gaps"], 1)

    def test_d3_lineage_and_d4_capability(self):
        d3 = miners.D3_lineage_slice(graph())
        self.assertEqual(d3["n"], 1)
        self.assertEqual(d3["frontier_nodes"][0]["state"], "unsolved")
        d4 = miners.D4_capability_cooccurrence(graph())
        self.assertEqual(d4["n"], 1)
        self.assertEqual(d4["capabilities"][0]["n_functions"], 2)

    def test_t_v2_04_coverage_three_states(self):
        c = coverage.build(out_dir=self.d)
        self.assertGreaterEqual(c["coverage_ratio"], 0)
        self.assertGreater(c["n_gap_candidates"], 0)
        self.assertTrue(all("status" in f for f in c["fields"]))

    def test_t_s2_15_gate_choosepoint(self):
        c = hitl.open_choice("3", out_dir=self.d)
        self.assertTrue(c["ok"])
        self.assertEqual(c["choice"]["mode"], "gate")
        self.assertIsNone(c["choice"]["default_option"])

    def test_spec_save_load_roundtrip(self):
        s = paperspec.compile_paperspec(graph(), paper_id="paper:a", out_dir=self.d)
        p = s.save(self.d)
        s2 = paperspec.PaperSpec.load(p)
        self.assertEqual(s.spec_hash, s2.compute_hash())


if __name__ == "__main__":
    unittest.main(verbosity=2)
