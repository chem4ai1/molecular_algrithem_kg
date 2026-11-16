"""S1 + v2-S1 验证：vocab 桥接、三层缓存、四态、对齐隔离、晋升、语义层保护。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.semantic.extraction import vocab

from capfactory.paperapp import (align, config, hitl, nodecache, promote,
                                 registry, signals, util, validate, vocab_bridge)


class TestS1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cache = self.d                      # 统一 out_dir，保证 registry 一致
        self.lock = mock.patch.object(config, "LOCK_FILE", self.d / ".lock")
        self.lock.start()
        registry.seed_defaults(out_dir=self.d, approver="test:s1")
        hitl.seed_choices(out_dir=self.d)
        self.vpatch = mock.patch.object(vocab, "VOCAB_FILE", self.d / "vocab.json")
        self.vpatch.start()

    def tearDown(self):
        self.vpatch.stop()
        self.lock.stop()
        self.tmp.cleanup()

    # ---- 用户点名的第一步：vocab.observe() → KnowledgeSignal ----
    def test_t_v2_08_vocab_bridge_creates_signal(self):
        r = vocab_bridge.observe_and_signal(
            "form", "分子图指纹", stage="E3_benchmark", paper_id="paper:a",
            run_id="run:1", out_dir=self.cache)
        self.assertTrue(r["ok"])
        self.assertTrue(r["signal_id"])
        sigs = signals.load_signals(out_dir=self.cache)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0].kind, "vocab_out_of_list")

    def test_t_v2_08b_promote_after_two(self):
        vocab_bridge.observe_and_signal("form", "新概念X", stage="s", out_dir=self.cache)
        r = vocab_bridge.observe_and_signal("form", "新概念X", stage="s",
                                            out_dir=self.cache)
        self.assertTrue(r["vocab"]["promoted"])
        self.assertTrue(r["promoted"])
        self.assertIn("新概念X", vocab.values("form"))

    def test_t_v2_08c_bridge_existing(self):
        vocab.observe("task_type", "新任务Y")
        r = vocab_bridge.bridge_existing(out_dir=self.cache, vocab_module=vocab)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["n_candidates"], 1)
        self.assertTrue((self.cache / "VOCAB_BRIDGE.json").exists())

    # ---- L1 幂等 ----
    def test_t_s1_03_cache_idempotent(self):
        calls = {"n": 0}

        def llm():
            calls["n"] += 1
            return {"value": 42}

        ident = nodecache.cache_identity("generation", "4broad", ["paper:a"])
        e1, h1 = nodecache.get_or_call(ident, llm, out_dir=self.cache)
        e2, h2 = nodecache.get_or_call(ident, llm, out_dir=self.cache)
        self.assertFalse(h1)
        self.assertTrue(h2)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(e1.output_sha, e2.output_sha)

    def test_t_s1_02_identity_dimensions(self):
        a = nodecache.cache_identity("generation", "2", ["p1"])
        b = nodecache.cache_identity("generation", "2", ["p1"], model_id="other")
        self.assertNotEqual(nodecache.request_key(a), nodecache.request_key(b))

    def test_t_v2_07_decision_fp_changes_key(self):
        a = nodecache.cache_identity("generation", "2", ["p1"])
        r = hitl.decide("6", "theory-only", approver="human:z", out_dir=self.d)
        self.assertTrue(r["ok"])
        b = nodecache.cache_identity("generation", "2", ["p1"],
                                     decision_fp=hitl.decision_fp(out_dir=self.d))
        self.assertNotEqual(nodecache.request_key(a), nodecache.request_key(b))

    # ---- 对齐与去重 ----
    def test_t_v2_09_align_cross_paper_isolation(self):
        e, _ = nodecache.get_or_call(
            nodecache.cache_identity("generation", "2", ["paper:a"]),
            lambda: {"value": "same concept"}, out_dir=self.cache)
        p1 = nodecache.put_proposal(e, {"value": "same concept"}, stage="2",
                                    paper_id="paper:a", run_id="run:1",
                                    candidate_class="IdeaNode", out_dir=self.cache)
        p2 = nodecache.put_proposal(e, {"value": "same concept"}, stage="2",
                                    paper_id="paper:b", run_id="run:1",
                                    candidate_class="IdeaNode", out_dir=self.cache)
        align.align(p1, out_dir=self.cache, emit_signal=False)
        r2 = align.align(p2, out_dir=self.cache, emit_signal=False)
        self.assertNotEqual(r2["action"], "reuse")

    def test_t_s1_06_unregistered_class(self):
        e, _ = nodecache.get_or_call(
            nodecache.cache_identity("generation", "2", ["p"]),
            lambda: {"v": 1}, out_dir=self.cache)
        p = nodecache.put_proposal(e, {"v": 1}, candidate_class="FakeClass",
                                   out_dir=self.cache)
        r = align.align(p, out_dir=self.cache, emit_signal=False)
        self.assertEqual(r["action"], "proposal")
        self.assertIn("unregistered_class", r["conflicts"])

    # ---- 四态与晋升 ----
    def test_t_s1_11_14_promotion_flow(self):
        e, _ = nodecache.get_or_call(
            nodecache.cache_identity("generation", "2", ["p"]),
            lambda: {"value": "z"}, out_dir=self.cache)
        p = nodecache.put_proposal(e, {"value": "z"}, stage="2",
                                   paper_id="paper:a", run_id="run:1",
                                   candidate_class="IdeaNode",
                                   canonical_id="appidea:a:z", out_dir=self.cache)
        p.evidence_ids = ["appev:1"]
        vr = validate.validate_proposal(p, gate_state="PASS", evidence_rank=1,
                                        out_dir=self.d)
        self.assertTrue(vr["ok"], vr)
        r = promote.promote(vr["proposal"], approver="human:z", run_id="run:1",
                            out_dir=self.d)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["promotion"]["to"], "registered")
        self.assertTrue(promote.audit_promotions(out_dir=self.d)["append_only"])

    def test_t_s1_13_semantic_layer_protected(self):
        ok, reason = promote.semantic_promotion_guard("semantic")
        self.assertFalse(ok)
        self.assertEqual(reason, "semantic_layer_protected")

    def test_t_s1_12_class_proposal_needs_approver(self):
        from capfactory.paperapp.schemas import LLMNodeProposal
        p = LLMNodeProposal("prop:c", "rq:c", "run:c", status="validated",
                            kind="class", candidate_class="IdeaNode",
                            evidence_ids=["e"], validation={"evidence_rank": 1})
        ok, reason = promote.can_promote(p, approver="", out_dir=self.d)
        self.assertFalse(ok)
        self.assertEqual(reason, "needs_human_approval")

    def test_t_s1_14_append_only_log(self):
        p1 = self.d / "append_only_probe.jsonl"   # 独立文件，避免与 seed 日志混用
        util.append_jsonl(p1, {"ts": "1", "event": "a"})
        util.append_jsonl(p1, {"ts": "2", "event": "b"})
        rows = util.read_jsonl(p1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event"], "a")

    # ---- 隔离与覆盖率 ----
    def test_t_s1_16_isolation_audit(self):
        from capfactory.paperapp import cli
        r = cli.audit_isolation()
        self.assertTrue(r["ok"])
        self.assertEqual(r["n_llm_proposal_in_semantic"], 0)

    def test_t_v2_06_dismiss_keeps_signal(self):
        s = signals.observe_event("align_unmatched", "q", out_dir=self.cache)
        signals.dismiss_signal(s["signal_id"], reason="dup", out_dir=self.cache)
        p = self.cache / "signals" / (s["signal_id"].replace(":", "_") + ".json")
        self.assertTrue(p.exists())
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(d["status"], "dismissed")
        self.assertEqual(d["dismiss_reason"], "dup")

    def test_t_v2_04_coverage_gap_emits_signal(self):
        from capfactory.paperapp import coverage
        c = coverage.build(out_dir=self.cache)
        self.assertGreater(c["n_gap_candidates"], 0)
        st = signals.signal_stats(out_dir=self.cache)
        self.assertGreaterEqual(st["by_kind"]["mining_gap"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
