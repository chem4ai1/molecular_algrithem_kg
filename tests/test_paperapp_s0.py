"""S0 + v2-S0 验证：注册中心、等价闸门、信号、人类决策、覆盖率。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.paperapp import (config, coverage, gates, hitl, registry,
                                 signals, tbox, util)


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


def mini_graph(order=1):
    nodes = {"paper:a": _N("Paper", {"title": "A"}),
             "alg:b": _N("Algorithm", {"name": "B"})}
    edges = [_A("paper:a", "alg:b", "PROPOSES_METHOD"),
             _A("alg:b", "paper:a", "RELATED_TO")]
    if order == 2:
        edges.reverse()
    return _G(nodes, edges)


class TestS0(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.lock = mock.patch.object(config, "LOCK_FILE", self.d / ".lock")
        self.lock.start()
        registry.seed_defaults(out_dir=self.d, approver="test:s0")
        hitl.seed_choices(out_dir=self.d)

    def tearDown(self):
        self.lock.stop()
        self.tmp.cleanup()

    def test_t_s0_01_register(self):
        r = registry.load_registry(out_dir=self.d)
        self.assertTrue(r["classes"])
        self.assertEqual(registry.validate_dynamic_tbox(out_dir=self.d), [])

    def test_t_s0_02_class_not_in_vocab(self):
        r = registry.register_class({"name": "FakeClass", "fields": ["x"]},
                                    approver="test", out_dir=self.d)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "class_not_in_vocab")

    def test_t_s0_03_active_classes(self):
        a = registry.active_classes(out_dir=self.d)
        self.assertIn("KnowledgeSignal", a)
        self.assertIn("HumanDecision", a)

    def test_t_s0_04_repeated_register_no_corruption(self):
        for _ in range(3):
            registry.seed_defaults(out_dir=self.d, approver="test")
        p = self.d / "registry.json"
        self.assertTrue(p.exists())
        self.assertIsInstance(json.loads(p.read_text(encoding="utf-8")), dict)

    def test_t_s0_05_class_not_active_blocks_instance(self):
        from capfactory.paperapp.schemas import LLMNodeProposal
        registry.deprecate_class("ResearchGap", reason="test", out_dir=self.d)
        p = LLMNodeProposal("prop:x", "rq:x", "run:x", candidate_class="ResearchGap")
        from capfactory.paperapp.validate import validate_proposal
        r = validate_proposal(p, out_dir=self.d)
        self.assertFalse(r["ok"])
        self.assertIn("class_not_active", r["reasons"])

    def test_t_s0_06_graph_digest_order_independent(self):
        d = util.diff_graphs(mini_graph(1), mini_graph(2))
        self.assertTrue(all(d[k] == 0 for k in
                            ("n_missing", "n_extra", "n_attr_diff", "n_rel_diff")))

    def test_t_s0_07_storage_paths(self):
        self.assertEqual(config.STORAGE.name, "sciforge")
        self.assertTrue(str(config.SEMANTIC_GRAPH).startswith(str(config.REPO_ROOT)))

    def test_t_s0_08_phasegraph_valid(self):
        self.assertEqual(len(tbox.stage_defs()), 26)
        self.assertEqual(tbox.validate_phasegraph(), [])
        self.assertLess(tbox.STAGE_IDS.index("4broad"), tbox.STAGE_IDS.index("2"))

    def test_t_s0_09_six_state_verdict(self):
        self.assertEqual(len(gates.VERDICT_STATES), 6)
        v = gates.emit("2", "PASS", artifacts=["x"])
        self.assertEqual(v["stage"], "2")
        with self.assertRaises(ValueError):
            gates.emit("2", "MAYBE")

    def test_t_s0_10_verify_rebuild_equivalent(self):
        r = util.verify_rebuild(base_graph=mini_graph(1), prev_app=mini_graph(1),
                                full_app=mini_graph(2))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["reason_code"], "EQUIVALENT")

    def test_t_s0_11_verify_rebuild_drift(self):
        g2 = mini_graph(1)
        g2.nodes["paper:c"] = _N("Paper", {"title": "C"})
        r = util.verify_rebuild(base_graph=mini_graph(1), prev_app=mini_graph(1),
                                full_app=g2)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "DRIFT")

    def test_t_s0_12_semantic_classes_frozen(self):
        from capfactory.semantic.tbox_v4 import SEMANTIC_CLASSES
        self.assertEqual(len(SEMANTIC_CLASSES), 6)

    # ---- v2 增补 ----
    def test_t_v2_01_human_decision_is_node(self):
        r = hitl.decide("3", "survivor_1", approver="human:z", out_dir=self.d)
        self.assertTrue(r["ok"])
        d = r["decision"]
        self.assertTrue(d["decision_id"])
        self.assertTrue((self.d / "decisions" / f"verdict_3.json").exists())

    def test_t_v2_02_all_v2_classes_active(self):
        for c in ("KnowledgeSignal", "SignalCluster", "MiningCoverage",
                  "ExplorationFrontier", "ChoicePoint", "HumanDecision",
                  "HumanHypothesis", "MethodAlternative", "HumanIntent",
                  "HumanOverride"):
            self.assertIn(c, registry.active_classes(out_dir=self.d))

    def test_t_v2_03_gate_timeout_blocked(self):
        self.assertEqual(config.GATE_TIMEOUT_POLICY, "BLOCKED")
        r = hitl.decide("6b", "kill", approver="", timeout=True, out_dir=self.d)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "choice_timeout_blocked")

    def test_t_v2_04_mining_coverage(self):
        c = coverage.build(out_dir=self.d)
        self.assertIn("coverage_ratio", c)
        self.assertTrue(c["fields"])
        self.assertTrue(c["assertions"])
        self.assertTrue((self.d / "MINING_COVERAGE.json").exists())
        self.assertGreaterEqual(signals.signal_stats(out_dir=self.d)["n_signals"], 1)

    def test_t_v2_05_reinjection_and_supersede(self):
        r1 = hitl.decide("6", "theory-only", approver="human:z", out_dir=self.d)
        self.assertTrue(r1["ok"])
        r2 = hitl.supersede(r1["decision"]["decision_id"], "6", "hybrid",
                            approver="human:z", reason="changed mind", out_dir=self.d)
        self.assertTrue(r2["ok"])
        self.assertEqual(len(hitl.active_decisions(out_dir=self.d)), 1)
        hitl.reinject(out_dir=self.d)
        texts = hitl.verbatim_for("10", out_dir=self.d)
        self.assertTrue(texts)

    def test_signals_capture_and_dismiss(self):
        s1 = signals.observe_event("gate_failed", "x", stage="2",
                                   paper_id="paper:a", out_dir=self.d)
        s2 = signals.observe_event("gate_failed", "x", stage="2",
                                   paper_id="paper:a", out_dir=self.d)
        self.assertEqual(s1["signal_id"], s2["signal_id"])
        self.assertEqual(s2["count"], 2)
        signals.dismiss_signal(s1["signal_id"], reason="expected", out_dir=self.d)
        st = signals.signal_stats(out_dir=self.d)
        self.assertEqual(st["dismiss_with_reason_rate"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
