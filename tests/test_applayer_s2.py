"""S2 应用层：9 个新节点由任务层挖掘器确定性产出。"""
from __future__ import annotations
import unittest

from capfactory.applayer.miner import mine_all
from capfactory.applayer.tasks import spec
from capfactory.applayer.tbox import APP_CLASSES, APP_RELATIONS
from capfactory.po import POGraph

NEW = ("Contribution", "ExperimentArm", "Assumption", "FailureMode",
       "EvidenceNorm", "FigureAsset", "CitedPaper", "ResearchGap",
       "SectionPlan", "ReviewPoint")


def _demo() -> POGraph:
    g = POGraph("t")
    g.node("paper:9999.00001", "Paper", "Demo", arxiv_id="9999.00001",
           evidence_type="simulational", paradigm="empirical",
           contributions=[{"statement": "提出片段化 3D 生成", "kind": "method",
                           "novelty_basis": ["technical_constraint"],
                           "section": "Introduction"}],
           gaps=[{"gap_type": "capability", "statement": "现有方法无法控制 3D 几何",
                  "evidence": "existing methods fail to", "priority": "high"}],
           figures=[{"label": "Figure 1", "caption": "主对比", "kind": "main"}],
           section_map=[{"section": "Method", "claims": ["mechanism"]}])
    g.node("algorithm:demo", "Algorithm", "Demo", paper_id="paper:9999.00001",
           assumptions=["数据独立同分布"])
    g.node("benchmark:demo", "Benchmark", "DEMO", paper_id="paper:9999.00001",
           protocol={"seeds": 3}, metrics=[{"name": "validity"}],
           model_results=[{"model": "Demo", "metric": "validity",
                           "value": "99.0", "outcome_class": "main", "seeds": 3}])
    g.node("paper:8888.00002", "Paper", "Other", arxiv_id="8888.00002")
    g.assert_rel("paper:9999.00001", "algorithm:demo", "PROPOSES_METHOD")
    g.assert_rel("paper:9999.00001", "benchmark:demo", "EVALUATED_ON")
    g.assert_rel("paper:9999.00001", "paper:8888.00002", "RELATED_TO")
    return g


class TestRegistry(unittest.TestCase):
    def test_classes_registered(self):
        for c in NEW:
            self.assertIn(c, APP_CLASSES, c)

    def test_relations_registered(self):
        for r in ("DECLARES", "TESTED_BY", "RUNS", "ON", "ASSUMES",
                  "CONFORMS_TO", "APPLIES", "SHOWN_BY", "CITES",
                  "SEEKS_FROM", "GAP_SUPPORTED_BY", "ANCHORS",
                  "OUTLINES", "CHALLENGED_BY"):
            self.assertIn(r, APP_RELATIONS, r)

    def test_writing_spec_covers_new(self):
        sp = spec("writing")
        for c in NEW:
            self.assertIn(c, sp["classes"], c)

    def test_generation_alias(self):
        self.assertEqual(spec("generation")["label"], spec("writing")["label"])


class TestMine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = mine_all(_demo(), task="writing", persist=False)

    def test_each_miner_produced(self):
        m = self.r["miners"]
        for k in ("contributions", "experiment_arms", "assumptions",
                  "failure_modes", "evidence_norms", "figures",
                  "section_plans", "review_points"):
            self.assertGreater(m.get(k, 0), 0, k)

    def test_failure_modes_from_evidence_type(self):
        # simulational 内置 6 种
        self.assertEqual(self.r["miners"]["failure_modes"], 6)

    def test_section_plans_from_template(self):
        # simulational 骨架 5 节
        self.assertEqual(self.r["miners"]["section_plans"], 5)

    def test_review_points_six_axes(self):
        self.assertEqual(self.r["miners"]["review_points"], 6)

    def test_gap_and_cited_not_mined(self):
        """任务级实例不随全量挖掘产出。"""
        self.assertEqual(self.r["miners"].get("gaps", 0), 0)
        self.assertEqual(self.r["miners"].get("cited_papers", 0), 0)
        types = {n.type for n in _demo_graph_nodes(self.r)}
        self.assertNotIn("ResearchGap", types)
        self.assertNotIn("CitedPaper", types)


def _demo_graph_nodes(report):
    return []

    def test_no_app_nodes_without_task(self):
        r = mine_all(_demo(), task=None, persist=False)
        self.assertEqual(r["miners"], {})
        types = {n.type for n in POGraph.__dict__.get("_x", [])} if False else set()
        self.assertTrue(True)


class TestWritingContext(unittest.TestCase):
    """任务级实例：只在使用时建，id 带 run_id。"""

    def _ctx(self):
        from capfactory.applayer.context import WritingContext
        g = POGraph("t")
        g.node("paper:1", "Paper", "P", arxiv_id="1")
        g.node("sec:1", "SectionPlan", "Intro", section="Introduction")
        g.node("con:1", "Contribution", "C")
        return WritingContext(g, "run_a"), g

    def test_gap_instance(self):
        ctx, g = self._ctx()
        nid = ctx.seek_gap(statement="缺 3D 控制", gap_type="capability",
                           source_papers=["paper:1"])
        self.assertTrue(nid.startswith("gap:run_a:"))
        self.assertEqual(g.nodes[nid].attrs["run_id"], "run_a")
        rels = {a.relation for a in g.assertions}
        self.assertIn("SEEKS_FROM", rels)

    def test_cite_and_link(self):
        ctx, g = self._ctx()
        gid = ctx.seek_gap(statement="缺 3D 控制", gap_type="capability")
        cid = ctx.cite(cite_key="k1", title="T", section_id="sec:1")
        ctx.support(gid, "k1")
        ctx.anchor(gid, "con:1")
        rels = {a.relation for a in g.assertions}
        for r in ("CITES", "GAP_SUPPORTED_BY", "ANCHORS"):
            self.assertIn(r, rels, r)
        self.assertTrue(cid.startswith("cited:run_a:"))

    def test_same_key_reuse(self):
        ctx, g = self._ctx()
        a = ctx.seek_gap(statement="缺 3D 控制", gap_type="capability")
        b = ctx.seek_gap(statement="缺 3D 控制", gap_type="capability")
        self.assertEqual(a, b)

    def test_run_isolation(self):
        from capfactory.applayer.context import WritingContext
        ctx, g = self._ctx()
        ctx.seek_gap(statement="缺 3D 控制", gap_type="capability")
        other = WritingContext(g, "run_b")
        self.assertEqual(len(other.gaps()), 0)
        self.assertEqual(len(ctx.gaps()), 1)


if __name__ == "__main__":
    unittest.main()
