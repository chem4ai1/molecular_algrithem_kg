"""RubricNode / HAS_SAU 进入单篇运行时图，且不污染全量图。"""
from __future__ import annotations
import json, unittest
from pathlib import Path
from capfactory.po import POGraph

from capfactory.applayer.tasks import spec
from capfactory.reprospec.application import REPRO_APP_CLASSES, EFFECTIVE_CLASSES
from capfactory.reprospec.relations import REPRO_APP_RELATIONS
from capfactory.reprospec import rubric_runtime as RR

RUN = Path("storage_cf/repro_runs/2411.06608")


class TestSpec(unittest.TestCase):
    def test_task_spec_has_rubric(self):
        sp = spec("reproduction")
        self.assertIn("RubricNode", sp["classes"])
        self.assertIn("HAS_SAU", sp["relations"])

    def test_runtime_class_registered(self):
        self.assertIn("RubricNode", REPRO_APP_CLASSES)
        self.assertIn("RubricNode", EFFECTIVE_CLASSES)
        self.assertEqual(REPRO_APP_RELATIONS["HAS_SAU"][0], "RubricNode")

    def test_generation_task_does_not_have_rubric(self):
        sp = spec("generation")
        self.assertNotIn("RubricNode", sp["classes"])
        self.assertNotIn("HAS_SAU", sp["relations"])


class TestRuntimeGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f = RUN / "app_repro_runtime.json"
        if not f.exists():
            raise unittest.SkipTest("无运行时图")
        cls.g = POGraph.load(str(f))

    def test_nodes_and_edges(self):
        rns = self.g.by_type("RubricNode")
        self.assertGreater(len(rns), 0)
        roles = {n.attrs.get("node_role") for n in rns}
        self.assertTrue({"root", "branch", "leaf"} <= roles)
        edges = self.g.assertions
        self.assertTrue(any(a.relation == "HAS_SAU" for a in edges))

    def test_every_leaf_has_edge(self):
        leaves = [n for n in self.g.by_type("RubricNode")
                  if n.attrs.get("node_role") == "leaf"]
        targets = {a.target for a in self.g.assertions
                   if a.relation == "HAS_SAU"}
        self.assertTrue(set(n.id for n in leaves) <= targets)

    def test_edges_are_application_layer(self):
        for a in self.g.assertions:
            if a.relation == "HAS_SAU":
                self.assertEqual((a.properties or {}).get("layer"),
                                 "application")
                self.assertEqual((a.properties or {}).get("task"),
                                 "reproduction")

    def test_full_graphs_untouched(self):
        for f in ("storage_cf/sciforge/batch10_semantic_v4.json",
                  "storage_cf/sciforge/app_reproduction.json",
                  "storage_cf/sciforge/app_generation.json"):
            g = POGraph.load(f)
            self.assertFalse(g.by_type("RubricNode"), f)
            self.assertFalse(any(a.relation == "HAS_SAU"
                                 for a in g.assertions), f)


class TestIdempotent(unittest.TestCase):
    def test_attach_twice_no_duplicates(self):
        r1 = RR.attach(RUN, persist=False)
        r2 = RR.attach(RUN, persist=False)
        self.assertEqual(r1["n_leaf_nodes"], r2["n_leaf_nodes"])
        self.assertEqual(r1["n_has_sau"], r2["n_has_sau"])


if __name__ == "__main__":
    unittest.main()
