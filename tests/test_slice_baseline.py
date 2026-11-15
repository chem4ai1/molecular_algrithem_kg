"""切片基线：图规模、报告齐备、关键入口可导入。"""
from __future__ import annotations
import json, unittest
from pathlib import Path

SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")
APP = Path("storage_cf/sciforge/app_reproduction.json")
GEN = Path("storage_cf/sciforge/app_generation.json")
RPT = Path("storage_cf/sciforge/semantic_extraction")
AIDS = ["2411.06608", "2405.03370", "2611.06237", "2302.09048"]


class TestSlice(unittest.TestCase):
    def test_graphs_exist(self):
        for p in (SEM, APP, GEN):
            self.assertTrue(p.exists(), str(p))

    def test_semantic_scale(self):
        from capfactory.po import POGraph
        g = POGraph.load(str(SEM))
        self.assertGreater(len(g.nodes), 100)
        self.assertGreater(len(g.assertions), 150)
        types = {n.type for n in g.nodes.values()}
        self.assertTrue({"Paper", "Algorithm", "AlgorithmModule",
                         "Benchmark"} <= types)

    def test_reports_present(self):
        for a in AIDS:
            f = RPT / f"{a}.json"
            self.assertTrue(f.exists(), str(f))
            d = json.loads(f.read_text(encoding="utf-8"))
            self.assertIn("stages", d)
            self.assertIn("paradigm", d)

    def test_page_snapshot_has_no_app_nodes(self):
        from capfactory.po import POGraph
        g = POGraph.load("storage_cf/sciforge/batch10_app_v1.json")
        app = [n for n in g.nodes.values()
               if n.attrs.get("layer") == "application"]
        self.assertEqual(app, [])

    def test_imports(self):
        from capfactory.applayer.builder import build_task_layer  # noqa: F401
        from capfactory.semantic.extraction.runner import run_extraction  # noqa: F401
        from capfactory.reprospec.rubric_tree import build_rubric_tree  # noqa: F401
        from capfactory.sciforge.repro import run_repro  # noqa: F401
        from capfactory.web.server import app

        self.assertTrue(hasattr(app, "routes"))


if __name__ == "__main__":
    unittest.main()
