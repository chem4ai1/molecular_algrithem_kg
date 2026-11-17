"""networkx 适配层：转换、往返、统计、查询、导出、API。"""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path

from capfactory.po import POGraph
from capfactory.po import nx_adapter as NX

SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")


@unittest.skipUnless(SEM.exists(), "缺语义层图")
class TestConvert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = POGraph.load(str(SEM))
        cls.mg = NX.to_networkx(cls.g)

    def test_type_and_scale(self):
        self.assertEqual(type(self.mg).__name__, "MultiDiGraph")
        self.assertEqual(self.mg.number_of_nodes(), len(self.g.nodes))
        self.assertEqual(self.mg.number_of_edges(), len(self.g.assertions))

    def test_node_attrs_preserved(self):
        n = self.mg.nodes["paper:2411.06608"]
        self.assertEqual(n["type"], "Paper")
        self.assertIn("title", n)

    def test_edge_attrs_preserved(self):
        d = self.mg.get_edge_data("paper:2411.06608", "algorithm:molminer")
        rels = {v["relation"] for v in (d or {}).values()}
        self.assertIn("PROPOSES_METHOD", rels)

    def test_roundtrip(self):
        back = NX.from_networkx(self.mg)
        self.assertEqual(len(back.nodes), len(self.g.nodes))
        self.assertEqual(len(back.assertions), len(self.g.assertions))
        self.assertEqual(back.nodes["paper:2411.06608"].type, "Paper")

    def test_layer_filter(self):
        only = NX.to_networkx(self.g, layer="semantic")
        self.assertLessEqual(only.number_of_nodes(), self.mg.number_of_nodes())


class TestAlgorithms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = POGraph.load(str(SEM))

    def test_stats_shape(self):
        s = NX.stats(self.g)
        self.assertEqual(s["engine"], "networkx")
        self.assertGreaterEqual(s["n_nodes"], 6001)
        self.assertGreater(s["n_weak_components"], 1)
        self.assertGreaterEqual(s["density"], 0.0)
        self.assertIn("top_out_degree", s)

    def test_neighbours(self):
        r = NX.neighbours(self.g, "paper:2411.06608", 1)
        self.assertTrue(r["found"])
        self.assertGreater(r["count"], 3)
        self.assertTrue(all(x["hops"] == 1 for x in r["neighbours"]))

    def test_neighbours_missing(self):
        self.assertFalse(NX.neighbours(self.g, "nope:1")["found"])

    def test_shortest_path(self):
        r = NX.shortest_path(self.g, "paper:2411.06608",
                             "algorithm:molminer")
        self.assertTrue(r["found"])
        self.assertEqual(r["hops"], 1)
        self.assertEqual(r["edges"][0]["relation"], "PROPOSES_METHOD")

    def test_export_graphml_roundtrip(self):
        import networkx as nx
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "g.graphml"
            info = NX.export(self.g, str(p), "graphml")
            self.assertGreater(info["bytes"], 1000)
            mg = nx.read_graphml(str(p))
            self.assertGreaterEqual(mg.number_of_nodes(), 6001)


class TestAPI(unittest.TestCase):
    def test_endpoints(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        c = TestClient(app)
        for p in ("/api/v9/graph/nx/stats",
                  "/api/v9/graph/nx/neighbors/paper:2411.06608?hops=1",
                  "/api/v9/graph/nx/shortest?src=paper:2411.06608"
                  "&dst=algorithm:molminer"):
            self.assertEqual(c.get(p).status_code, 200, p)
        r = c.get("/api/v9/graph/nx/export?fmt=json")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 1000)


if __name__ == "__main__":
    unittest.main()
