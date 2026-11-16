"""S3 + v2-S3 验证：26 阶段门、约束再注入、事件重放、人方向留痕。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.paperapp import (config, gates, hitl, registry, runner,
                                 signals, tbox, util)


class _N:
    def __init__(self, t, attrs=None):
        self.type, self.attrs = t, dict(attrs or {})


class _A:
    def __init__(self, s, t, r):
        self.source, self.target, self.relation = s, t, r
        self.properties = {}


class _G:
    def __init__(self):
        self.nodes = {"p:a": _N("Paper", {"title": "A"}),
                      "b:z": _N("Benchmark", {"metrics": ["v"]})}
        self.assertions = [_A("p:a", "b:z", "EVALUATED_ON")]


GATES = {s: tbox.CHOICEPOINTS[s]["options"][0] for s in tbox.GATE_STAGES}


class TestS3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.lock = mock.patch.object(config, "LOCK_FILE", self.d / ".lock")
        self.lock.start()
        registry.seed_defaults(out_dir=self.d, approver="test:s3")
        hitl.seed_choices(out_dir=self.d)
        self.vpatch = mock.patch.object(config, "STAGE_IDS", config.STAGE_IDS)
        self.vpatch.start()

    def tearDown(self):
        self.vpatch.stop()
        self.lock.stop()
        self.tmp.cleanup()

    def _run(self, **kw):
        return runner.run(paper_id="paper:a", run_id="run:t", out_dir=self.d,
                          graph=_G(), **kw)

    def test_t_s3_14_full_26_stages(self):
        r = self._run(gate_decisions=GATES)
        self.assertEqual(r["n_stages"], 26)
        self.assertEqual(r["overall"], "PASS")
        self.assertEqual(len(r["verdicts"]), 26)

    def test_t_v2_15_gate_undecided_blocks(self):
        r = self._run(gate_decisions={})       # 没有任何 gate 决定
        self.assertEqual(r["overall"], "BLOCKED")
        self.assertGreaterEqual(sum(1 for v in r["verdicts"].values()
                                    if v == "BLOCKED"), 4)

    def test_t_v2_17_reinjection_every_boundary(self):
        hitl.decide("6", "theory-only", approver="human:z", out_dir=self.d)
        hitl.reinject(out_dir=self.d)
        self._run(gate_decisions=GATES)
        rows = util.read_jsonl(self.d / "run_t" / "events.ndjson", limit=10000)
        reinj = [r for r in rows if r.get("event") == "reinjection"]
        self.assertGreater(len(reinj), 0)
        self.assertIn("verbatim_text", reinj[0]["payload"])

    def test_t_s3_12_events_replay_consistent(self):
        r = self._run(gate_decisions=GATES)
        v = runner.verify_run(r["run_id"], out_dir=self.d)
        self.assertTrue(v["replay_ok"])
        self.assertGreater(v["n_events"], 26)

    def test_t_s3_10_audit_gates(self):
        self._run(gate_decisions=GATES)
        a = runner.audit_gates("run:t", out_dir=self.d)
        self.assertTrue(a["ok"], a)
        self.assertEqual(a["n"], 26)

    def test_t_s3_08_runner_never_writes_graph(self):
        before = util.sha256_file(config.APP_GRAPH)
        before_sem = util.sha256_file(config.SEMANTIC_GRAPH)
        self._run(gate_decisions=GATES)
        self.assertEqual(util.sha256_file(config.APP_GRAPH), before)
        self.assertEqual(util.sha256_file(config.SEMANTIC_GRAPH), before_sem)

    def test_t_s3_09_two_thresholds(self):
        self.assertEqual(config.BOUNDARY_FLOOR, 6.0)
        self.assertEqual(config.S2_REBUTTAL_BAR, 8.0)
        self.assertNotEqual(config.BOUNDARY_FLOOR, config.S2_REBUTTAL_BAR)

    def test_t_v2_16_human_direction_failure_in_lessons(self):
        r = self._run(gate_decisions=GATES,
                      human_hypotheses=[{"statement": "换用扩散采样",
                                         "falsifiable_claim": "指标下降",
                                         "gap_anchor": "GAP-1",
                                         "succeeded": False}])
        lessons = json.loads((self.d / "run_t" / "LESSONS.json").read_text(encoding="utf-8"))
        self.assertEqual(len(lessons), 5)
        self.assertEqual(len(lessons["human_hypothesis_rollbacks"]), 1)
        self.assertEqual(r["n_human_hypotheses_accepted"], 1)

    def test_t_v2_16b_invalid_human_direction_signal(self):
        self._run(gate_decisions=GATES,
                  human_hypotheses=[{"statement": "空想", "falsifiable_claim": "c"}])
        st = signals.signal_stats(out_dir=self.d)
        self.assertGreaterEqual(st["by_kind"]["human_direction_unadopted"], 1)

    def test_t_s3_11_fail_at(self):
        r = self._run(gate_decisions=GATES, fail_at="10")
        self.assertEqual(r["overall"], "FAIL")
        self.assertEqual(r["verdicts"]["10"], "FAIL")

    def test_debug_stage_and_budget(self):
        self._run(gate_decisions=GATES)
        d = runner.debug_stage("run:t", "10", out_dir=self.d)
        self.assertIsNotNone(d["verdict"])
        b = runner.budget("run:t", out_dir=self.d)
        self.assertIn("exploration_regret", b)

    def test_not_applicable_requires_artifacts(self):
        v = {"x": {"state": "NOT_APPLICABLE", "artifacts": []}}
        a = gates.audit(v)
        self.assertFalse(a["ok"])
        self.assertEqual(a["not_applicable_without_file"], ["x"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
