"""层次化 rubric 树：挂载、加权聚合、SAU 字段、回填幂等。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.reprospec import rubric_tree as RT
from capfactory.reprospec.contract import SAU

RUN = Path("storage_cf/repro_runs/2411.06608")


class TestTreeBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f = RUN / "SAU_LIST.json"
        if not f.exists():
            raise unittest.SkipTest("无 SAU_LIST")
        cls.doc = json.loads(f.read_text(encoding="utf-8"))
        cls.sau = cls.doc["sau"]
        cls.tree = RT.build_rubric_tree(
            cls.sau, paper_id=cls.doc.get("paper_id", ""),
            arxiv_id=cls.doc.get("arxiv_id", ""),
            spec_hash=cls.doc.get("spec_hash", ""))

    def test_all_mounted(self):
        self.assertEqual(self.tree["n_unmounted"], 0)
        self.assertEqual(self.tree["n_mounted"], len(self.sau))

    def test_hierarchy_depth(self):
        self.assertEqual(self.tree["depth_max"], 3)
        self.assertGreater(self.tree["n_branches"], 5)
        self.assertTrue(all("/" in b["path"] for b in self.tree["branches"]))

    def test_parents_are_graph_nodes(self):
        from capfactory.po import POGraph
        sem = POGraph.load(str(RT.SEM))
        app = POGraph.load(str(RT.APP)) if RT.APP.exists() else None
        ids = set(sem.nodes) | (set(app.nodes) if app else set())
        for leaf in self.tree["leaves"]:
            self.assertIn(leaf["parent_id"], ids, leaf["id"])

    def test_sau_tree_fields_not_in_spec_hash(self):
        s = SAU(id="x", kind="method", statement="y", parent_id="p",
                path="a/b", depth=3, weight=2.0)
        self.assertNotIn("parent_id", s.stable_key())
        self.assertEqual(s.parent_id, "p")

    def test_weight_required(self):
        for s in self.sau:
            leaf = next(x for x in self.tree["leaves"] if x["id"] == s["id"])
            self.assertEqual(leaf["weight"], 2.0 if s.get("required", True) else 1.0)


class TestTreeScore(unittest.TestCase):
    def setUp(self):
        self.tree = {"root": "paper:x", "leaves": [
            {"id": "a", "path": "paper:x/algorithm:a/module:m", "weight": 2.0},
            {"id": "b", "path": "paper:x/algorithm:a/module:m", "weight": 1.0},
            {"id": "c", "path": "paper:x/benchmark:z", "weight": 2.0}]}

    def test_all_aligned(self):
        v = [{"sau_id": x, "verdict": "aligned"} for x in "abc"]
        sc = RT.tree_score(self.tree, v)
        self.assertEqual(sc["root_score"], 1.0)
        self.assertEqual(sc["failed_branches"], [])

    def test_weighted_failure_branch(self):
        v = [{"sau_id": "a", "verdict": "aligned"},
             {"sau_id": "b", "verdict": "mismatch"},
             {"sau_id": "c", "verdict": "aligned"}]
        sc = RT.tree_score(self.tree, v)
        self.assertAlmostEqual(sc["root_score"], 4 / 5)
        self.assertEqual(len(sc["failed_branches"]), 1)
        self.assertIn("module:m", sc["failed_branches"][0])
        self.assertIn("algorithm:a", sc["by_l1"])

    def test_missing_verdict_counts_as_fail(self):
        sc = RT.tree_score(self.tree, [])
        self.assertEqual(sc["root_score"], 0.0)


class TestBackfill(unittest.TestCase):
    def test_products_exist(self):
        for p in Path("storage_cf/repro_runs").rglob("SAU_LIST.json"):
            self.assertTrue((p.parent / "RUBRIC_TREE.json").exists(), str(p))

    def test_final_evaluation_has_tree(self):
        f = RUN / "FINAL_EVALUATION.json"
        if not f.exists():
            self.skipTest("无 FINAL_EVALUATION")
        d = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("rubric_tree", d)
        self.assertIn("evaluation", d)      # 旧结构保留
        self.assertIn("align_rubric", d)

    def test_backfill_is_idempotent(self):
        r1 = RT.backfill_all(persist=False)
        r2 = RT.backfill_all(persist=False)
        self.assertEqual(r1["total_leaves"], r2["total_leaves"])
        self.assertEqual(r1["files"], r2["files"])


if __name__ == "__main__":
    unittest.main()
