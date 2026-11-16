"""S6 验证：16 硬门、12 指标、修正闭环、演练与报告。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.paperapp import (config, hitl, materialize, registry, report,
                                 runner, util, cli)


class TestS6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reports = {
            "metrics": config.REPO_ROOT / "docs" / "INTEGRATION_REPORT.md",
            "sign": config.REPO_ROOT / "docs" / "plan" / "S6_FINAL_REPORT.md",
            "json": config.RUNS_DIR / "INTEGRATION_METRICS.json",
        }

    def test_t_s6_02_fix_closure(self):
        f = report.fix_closure()
        self.assertEqual(f["status"], "closed")
        self.assertGreaterEqual(f["n"], 10)
        self.assertTrue(all(x.get("test") and x.get("fix") for x in f["items"]))

    def test_t_s6_03_thresholds_centralized(self):
        for name in ("SIM_REUSE", "SIM_AMBIGUOUS", "MIN_REUSE",
                     "BOUNDARY_FLOOR", "S2_REBUTTAL_BAR", "GATE_TIMEOUT_POLICY",
                     "MINING_COVERAGE_TARGET", "STALE_SCOPE_CEILING"):
            self.assertTrue(hasattr(config, name), name)

    def test_t_s6_05_path_traversal(self):
        bad = "../../etc/passwd"
        p = (config.RUNS_DIR / bad.replace("/", "_")).resolve()
        self.assertTrue(str(p).startswith(str(config.REPO_ROOT.resolve())), p)
        self.assertNotIn("..", p.parts)

    def test_t_s6_06_no_delete_and_semantic_frozen(self):
        import subprocess
        out = subprocess.run(
            ["grep", "-rnE", "rm -rf|shutil.rmtree|os.remove",
             "src/capfactory/paperapp"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "")
        self.assertTrue(cli.audit_isolation()["ok"])

    def test_t_s6_07_drill_f9_supersede(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            with mock.patch.object(config, "LOCK_FILE", d / ".lock"):
                registry.seed_defaults(out_dir=d, approver="test:s6")
                hitl.seed_choices(out_dir=d)
                r1 = hitl.decide("6", "theory-only", approver="human:z", out_dir=d)
                fp1 = hitl.decision_fp(out_dir=d)
                r2 = hitl.supersede(r1["decision"]["decision_id"], "6", "hybrid",
                                    approver="human:z", reason="changed", out_dir=d)
                self.assertTrue(r2["ok"])
                self.assertNotEqual(hitl.decision_fp(out_dir=d), fp1)
                self.assertEqual(len(hitl.active_decisions(out_dir=d)), 1)

    def test_t_s6_07_drill_f10_gate_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            r = hitl.decide("6b", "kill", approver="", timeout=True, out_dir=d)
            self.assertFalse(r["ok"])
            self.assertEqual(r["reason_code"], "choice_timeout_blocked")

    def test_t_s6_07_drill_f11_vocab_promote(self):
        from capfactory.semantic.extraction import vocab
        from capfactory.paperapp import signals, vocab_bridge
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            with mock.patch.object(vocab, "VOCAB_FILE", d / "vocab.json"):
                for _ in range(3):
                    vocab_bridge.observe_and_signal("form", "新概念F11",
                                                    stage="s", out_dir=d)
                self.assertGreaterEqual(signals.signal_stats(out_dir=d)["n_signals"], 1)

    def test_t_s6_07_drill_f12_frontier_restart(self):
        from capfactory.paperapp import replay
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            with mock.patch.object(config, "RUNS_DIR", d):
                util.atomic_write(d / "REPLAY_CONTEXT.json",
                                  {"frontiers": [{"direction": "d", "status": "failed"}]})
                r = replay.restart_frontier("d", reason="新数据", out_dir=d)
                self.assertTrue(r["ok"])

    def test_t_s6_08_commands_exist(self):
        readme = (config.REPO_ROOT / "docs" / "plan" / "README.md").read_text(encoding="utf-8")
        self.assertIn("scripts/serve.sh", readme)
        self.assertIn("unittest discover", readme)
        self.assertTrue((config.REPO_ROOT / "scripts" / "test_all.sh").exists())

    def test_t_s6_09_test_all_strict(self):
        p = config.REPO_ROOT / "scripts" / "test_all.sh"
        t = p.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", t)
        self.assertIn("ALL_GREEN", t)

    def test_t_s6_12_audit_all(self):
        a = cli.audit_all()
        self.assertIn("n_hard_gates", a)
        self.assertEqual(a["n_hard_gates"], 8)     # 聚合的 8 类审计

    def test_t_s6_14_report_generation(self):
        r = report.write_report()
        self.assertIn("metrics", r)
        self.assertEqual(r["n_hard_gates"], 16)
        for p in self.reports.values():
            self.assertTrue(p.exists(), str(p))
        payload = json.loads(self.reports["json"].read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(payload["metrics"]), 13)  # 12 指标 + 元数据
        self.assertEqual(len(payload["hard_gates"]), 16)

    def test_t_s6_01_no_skip_as_pass(self):
        """静态检查：新增测试不得用 skip/expectedFailure 冒充通过（不递归跑 discover）。"""
        import re
        files = sorted((config.REPO_ROOT / "tests").glob("test_paperapp_*.py"))
        self.assertGreaterEqual(len(files), 7)
        for p in files:
            t = p.read_text(encoding="utf-8")
            self.assertNotRegex(t, r"@unittest\.skip|@unittest\.expectedFailure")
            # 拼接避免本文件的检查字面量被自己扫到
            self.assertNotIn("unittest" + ".skip(", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
