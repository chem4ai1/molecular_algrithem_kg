"""标准范式层 / 全量批处理 / 关系页溯源卡片。"""
from __future__ import annotations
import json, unittest
from pathlib import Path

from capfactory.po import POGraph
from capfactory.semantic.extraction import paradigm as PD
from capfactory.semantic import batch_extract as BE

SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")
EXT = Path("storage_cf/sciforge/semantic_extraction")
REPORT = EXT / "2411.06608.json"


class TestParadigm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = POGraph.load(str(SEM))
        cls.r = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.sl = {"paper": "Our work builds on JTNN",
                  "algorithm": "forward(x) uses RDKit",
                  "benchmark": "Table 1 shows validity 99.6"}

    def test_ner(self):
        e = PD.recognize_entities(self.sl, self.g)
        self.assertTrue(e["algorithms"])
        self.assertTrue(e["benchmarks"])
        self.assertTrue(e["code_symbols"])
        self.assertTrue(any(x["source"] == "graph_catalog"
                            for x in e["algorithms"]))

    def test_canonicalize_exact(self):
        c = PD.canonicalize(self.r, self.g)
        self.assertGreater(c["n_exact"], 0)
        self.assertIn("canonical_map", c)

    def test_ground_relations(self):
        r = {"lineage": {"all": [
            {"from": "A", "to": "B", "kind": "extends",
             "evidence": "Our work builds on JTNN"}]}}
        g = PD.ground_relations(r, self.sl)
        self.assertEqual(len(g["grounded"]), 1)
        self.assertGreaterEqual(g["grounded"][0]["char_offset"], 0)

    def test_ungrounded_marked(self):
        r = {"lineage": {"all": [
            {"from": "A", "to": "B", "kind": "extends",
             "evidence": "this sentence is not in the text at all"}]}}
        g = PD.ground_relations(r, self.sl)
        self.assertEqual(len(g["ungrounded"]), 1)

    def test_track_modules(self):
        t = PD.track_modules(self.r)
        self.assertGreater(t["n_modules"], 0)
        c = t["chains"][0]["modules"]
        self.assertEqual(c[0]["step_order"], 1)
        self.assertEqual(c[1]["depends_on"], c[0]["name"])
        self.assertIn("->", c[1]["data_flow"])

    def test_slot_audit_only_ran_stages(self):
        r = {"stages": {"E1_paper": {"data": {
                "research_question": "Q", "problem_category": "T"}}},
             "model_results": {"deduplicated": 3}}
        a = PD.slot_audit(r, self.g)
        self.assertEqual(a["n_total"], 2)   # 不审计未跑的 E2/E3/E4 槽位

    def test_apply_paradigm_adds_field(self):
        r = json.loads(json.dumps(self.r))
        PD.apply_paradigm(r, graph=self.g, slices=self.sl)
        self.assertIn("paradigm", r)
        self.assertIn("slot_score", r["paradigm"]["summary"])


class TestBatch(unittest.TestCase):
    def test_papers_count(self):
        p = BE.papers()
        self.assertGreaterEqual(len(p), 4)
        self.assertTrue(all("." in x for x in p))

    def test_status_structure(self):
        s = BE.status()
        self.assertEqual(s["total"], len(BE.papers()))
        self.assertEqual(len(s["shards"]), 2)
        self.assertIn("remaining", s)

    def test_state_paths_isolated(self):
        self.assertNotEqual(BE.state_path(0, 2), BE.state_path(1, 2))

    def test_report_ok_tolerant(self):
        self.assertTrue(BE.report_ok("2411.06608"))
        self.assertFalse(BE.report_ok("9999.99999"))


class TestProvenanceCard(unittest.TestCase):
    def test_js_served(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        c = TestClient(app)
        js = c.get("/static/provenance_card.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("renderProvenance", js.text)

    def test_relations_page_refs_js(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        h = TestClient(app).get("/relations").text
        self.assertIn("provenance_card.js", h)
        self.assertIn("renderProvenance", h)

    def test_relations_node_has_provenance(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        d = TestClient(app).get(
            "/api/v8/relations/node/benchmark:zinc?view=benchmark").json()
        self.assertIn("provenance", d)
        self.assertGreater(d["provenance"].get("n_cells", 0), 0)

    def test_batch_status_api(self):
        from fastapi.testclient import TestClient
        from capfactory.web.server import app
        d = TestClient(app).get("/api/v8/extraction/batch-status").json()
        self.assertEqual(d["total"], len(BE.papers()))


if __name__ == "__main__":
    unittest.main()
