"""S4 + v2-S4 验证：增量回写、DRIFT 拒写、回放与最小重算。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.paperapp import (config, hitl, materialize, nodecache,
                                 promote, registry, replay, signals, util)
from capfactory.paperapp.schemas import LLMNodeProposal


class TestS4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.lock = mock.patch.object(config, "LOCK_FILE", self.d / ".lock")
        self.lock.start()
        registry.seed_defaults(out_dir=self.d, approver="test:s4")
        hitl.seed_choices(out_dir=self.d)
        # 最小图副本：避免测试读 6001 节点全量图
        self.sem = self.d / "semantic.json"
        self.app = self.d / "app.json"
        util.atomic_write(self.sem, {"meta": {}, "nodes": [
            {"id": "p:a", "type": "Paper", "attrs": {"title": "A"}}],
            "assertions": []})
        util.atomic_write(self.app, {"meta": {}, "nodes": [
            {"id": "p:a", "type": "Paper",
             "attrs": {"layer": "semantic", "title": "A"}}],
            "assertions": []})
        self.psem = mock.patch.object(config, "SEMANTIC_GRAPH", self.sem)
        self.papp = mock.patch.object(config, "APP_GRAPH", self.app)
        self.psem.start()
        self.papp.start()

    def tearDown(self):
        self.papp.stop()
        self.psem.stop()
        self.lock.stop()
        self.tmp.cleanup()

    def _proposal(self, pid="prop:a"):
        p = LLMNodeProposal(proposal_id=pid, request_key="rq:a", run_id="run:a",
                            paper_id="paper:a", stage="2",
                            candidate_class="IdeaNode",
                            canonical_id="appidea:a:new",
                            attrs={"value": "新方向"},
                            evidence_ids=["appev:1"], derived_from=["p:a"],
                            attribution="llm_proposal")
        nodecache.save_proposal(p, out_dir=self.d)
        return p

    def test_t_s4_05_drift_rejects_write(self):
        bad = self.d / "bad_app.json"
        util.atomic_write(bad, {"meta": {}, "nodes": [
            {"id": "p:a", "type": "Paper", "attrs": {"layer": "semantic",
                                                     "title": "TAMPERED"}}],
            "assertions": []})
        v = materialize.verify(app_path=bad, out_dir=self.d)
        self.assertFalse(v["ok"])
        self.assertEqual(v["reason_code"], "DRIFT")

    def test_t_s4_05b_verify_equivalent(self):
        v = materialize.verify(app_path=self.app, out_dir=self.d)
        self.assertTrue(v["ok"], v)

    def test_t_s4_14_incremental_write(self):
        self._proposal()
        with mock.patch.object(config, "ALLOW_INCREMENTAL_WRITE", True):
            r = materialize.materialize("run:a", out_dir=self.d, write=True,
                                        graph_path=self.app)
        self.assertTrue(r["rebuild_equivalence"], r)
        self.assertGreaterEqual(r["n_registered"], 1)
        self.assertEqual(len(r["files_written"]), 1)
        d = json.loads(self.app.read_text(encoding="utf-8"))
        ids = {n["id"] for n in d["nodes"]}
        self.assertIn("appidea:a:new", ids)
        self.assertEqual(util.sha256_file(self.sem),
                         r["semantic_graph_sha_after"])   # 语义层不变

    def test_t_s4_09_append_only_promotions(self):
        self._proposal("prop:b")
        with mock.patch.object(config, "ALLOW_INCREMENTAL_WRITE", True):
            materialize.materialize("run:a", out_dir=self.d, write=True,
                                    graph_path=self.app)
            materialize.materialize("run:a", out_dir=self.d, write=True,
                                    graph_path=self.app)
        a = promote.audit_promotions(out_dir=self.d)
        self.assertTrue(a["append_only"])
        self.assertGreaterEqual(a["n"], 1)

    def test_t_s4_10_use_count(self):
        self._proposal()
        with mock.patch.object(config, "ALLOW_INCREMENTAL_WRITE", True):
            materialize.materialize("run:a", out_dir=self.d, write=True,
                                    graph_path=self.app)
        reg = registry.load_registry(out_dir=self.d)
        self.assertGreaterEqual(reg["classes"]["IdeaNode"]["use_count"], 1)

    def test_t_s4_15_report_fields(self):
        self._proposal()
        r = materialize.materialize("run:a", out_dir=self.d, write=False)
        for k in ("n_proposed", "n_validated", "n_registered", "n_rejected",
                  "n_conflicts", "rebuild_equivalence", "decision_fp",
                  "signal_capture_rate", "files_written"):
            self.assertIn(k, r)
        self.assertEqual(r["files_written"], [])   # dry-run 不写

    def test_t_v2_11_replay_avoid(self):
        p = self.d / "run_x" / "LESSONS.json"
        p.parent.mkdir(parents=True)
        util.atomic_write(p, {
            "failed_experiments": [{"lesson": "不要用 naive 采样", "evidence": "x"}],
            "idea_rollbacks": [], "code_errors": [], "what_worked": [],
            "human_hypothesis_rollbacks": [{"lesson": "扩散方向失败", "reason": "6b"}]})
        ctx = replay.build_context(["run:x"], out_dir=self.d)
        self.assertEqual(ctx["n_hard_excluded"], 2)
        self.assertTrue(replay.hard_excluded(ctx, "naive 采样"))

    def test_t_v2_20_frontier_restart(self):
        replay.build_context([], out_dir=self.d)
        p = self.d / "REPLAY_CONTEXT.json"
        util.atomic_write(p, {"frontiers": [{"direction": "d", "status": "failed"}]})
        r = replay.restart_frontier("d", reason="新数据可用", out_dir=self.d)
        self.assertTrue(r["ok"])
        ctx = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(ctx["frontiers"][0]["status"], "untried")
        self.assertFalse(replay.restart_frontier("d", reason="", out_dir=self.d)["ok"])

    def test_t_v2_19_decision_fp_in_report(self):
        hitl.decide("6", "theory-only", approver="human:z", out_dir=self.d)
        hitl.reinject(out_dir=self.d)
        self._proposal()
        r = materialize.materialize("run:a", out_dir=self.d)
        self.assertNotEqual(r["decision_fp"], "")

    def test_t_s4_04_dismissed_signal_kept(self):
        s = signals.observe_event("align_unmatched", "x", out_dir=self.d)
        signals.dismiss_signal(s["signal_id"], reason="dup", out_dir=self.d)
        self.assertTrue((self.d / "signals" /
                         (s["signal_id"].replace(":", "_") + ".json")).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
