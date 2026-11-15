"""复现生命周期四环节：锁定漂移、DAG 校验、执行可重复、三级锚定、篡改检测。"""
from __future__ import annotations
import json, shutil, tempfile, unittest
from pathlib import Path

from capfactory.po import POGraph
from capfactory.reprospec import lifecycle as LC

WS = Path("storage/repro_test/2411.06608")
APP = Path("storage_cf/sciforge/app_reproduction.json")
PID = "paper:2411.06608"


def _load(n):
    return json.loads((WS / n).read_text(encoding="utf-8"))


@unittest.skipUnless(WS.exists(), "先跑 run_lifecycle")
class TestLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load(LC.LOCK_FILE)

    def test_locked_with_fingerprints(self):
        self.assertTrue(self.doc["locked"])
        self.assertEqual(self.doc["n_method_sau"],
                         len(self.doc["fingerprints"]))
        self.assertGreaterEqual(self.doc["n_method_sau"], 10)

    def test_set_hash_shape(self):
        self.assertTrue(self.doc["method_sau_hash"].startswith("sha256:"))
        self.assertEqual(self.doc["drift"], [])

    def test_drift_detected_when_sau_changes(self):
        from capfactory.reprospec.compiler import compile_reprospec
        with tempfile.TemporaryDirectory() as td:
            spec = compile_reprospec(paper_id=PID, out_dir=td)
            r1 = LC.run_lock(spec, Path(td))
            self.assertTrue(r1.ok, r1.blocked_by)
            spec.by_kind("method")[0].statement += "（被篡改）"
            r2 = LC.run_lock(spec, Path(td))
            self.assertFalse(r2.ok)
            self.assertIn(r2.metrics["drift"], (1,))
            self.assertGreaterEqual(r2.metrics["drift"], 1)


class TestCodegen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load(LC.CODEGEN_FILE)
        cls.src = (WS / "REPRO_SCRIPT.py").read_text(encoding="utf-8")

    def test_tasks_and_dag(self):
        self.assertGreater(len(self.doc["tasks"]), 5)
        orders = [t["order"] for t in self.doc["tasks"]]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(orders), len(set(orders)))

    def test_dependencies_reference_known_tasks(self):
        ids = {t["module_id"] for t in self.doc["tasks"]}
        for t in self.doc["tasks"]:
            for d in t["depends_on"]:
                self.assertIn(d, ids)

    def test_checks(self):
        c = self.doc["checks"]
        self.assertEqual(c["safety"], [])
        self.assertTrue(c["order_ok"])
        self.assertGreaterEqual(c["symbol_recall"], 0.95)

    def test_script_sha_matches_file(self):
        self.assertEqual(LC._sha(self.src, 20), self.doc["script"]["sha"])

    def test_script_is_stdlib_and_independent(self):
        for bad in ("import requests", "import numpy", "from capfactory"):
            self.assertNotIn(bad, self.src)


class TestExecute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load(LC.EXEC_FILE)

    def test_two_stages_and_repeatable(self):
        self.assertEqual(len(self.doc["stages"]), 2)
        self.assertTrue(self.doc["repeatable"])
        self.assertEqual(self.doc["double_run"]["sha1"],
                         self.doc["double_run"]["sha2"])

    def test_full_coverage(self):
        cov = self.doc["coverage"]
        self.assertEqual(cov["n_executed"], cov["n_method"])
        self.assertEqual(self.doc["failures"], [])

    def test_stage_rows_positive(self):
        for s in self.doc["stages"]:
            self.assertEqual(s["status"], "PASS")
            self.assertGreater(s["n_rows"], 0)
            self.assertGreater(s["steps_executed"], 0)


class TestAnchor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load(LC.ANCHOR_FILE)

    def test_claims_and_integrity(self):
        self.assertGreaterEqual(self.doc["n_claims"], 20)
        self.assertTrue(self.doc["integrity"])
        self.assertTrue(self.doc["double_run_equal"])

    def test_three_level_chain(self):
        self.assertGreaterEqual(self.doc["n_three_level"], 20)
        c = next(c for c in self.doc["claims"] if c["three_level"])
        self.assertTrue(c["level1_claim"]["metric"])
        self.assertTrue(c["level3_graph"]["benchmark_id"])
        self.assertTrue(c["level2_cell"]["entry_id"])

    def test_four_hashes(self):
        for c in self.doc["claims"][:5]:
            for k in ("spec", "code", "inputs", "outputs"):
                self.assertTrue(c["hashes"][k], k)

    def test_verify_ok(self):
        v = LC.verify_lifecycle(WS)
        self.assertTrue(v["ok"], v["issues"])

    def test_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "ws"
            shutil.copytree(WS, dst)
            p = dst / "REPRO_SCRIPT.py"
            p.write_text(p.read_text(encoding="utf-8") + "\n# tampered\n",
                         encoding="utf-8")
            v = LC.verify_lifecycle(dst)
            self.assertFalse(v["ok"])
            self.assertIn("script_modified_after_codegen", v["issues"])


class TestStatusAndAPI(unittest.TestCase):
    def test_stage_status_ready(self):
        s = LC.stage_status(WS)
        self.assertTrue(s["ready"])
        for k in ("lock", "codegen", "execute", "anchor"):
            self.assertEqual(s["stages"][k]["state"], "done")

    def test_api_endpoints(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        c = TestClient(app)
        for path in ("/api/v9/repro/papers", "/api/v9/repro/2411.06608/status",
                     "/api/v9/repro/2411.06608/method-lock",
                     "/api/v9/repro/2411.06608/code-plan",
                     "/api/v9/repro/2411.06608/execution",
                     "/api/v9/repro/2411.06608/anchors",
                     "/api/v9/repro/2411.06608/verify",
                     "/api/v9/repro/2411.06608/lifecycle"):
            self.assertEqual(c.get(path).status_code, 200, path)
        self.assertEqual(c.get("/repro").status_code, 200)


if __name__ == "__main__":
    unittest.main()
