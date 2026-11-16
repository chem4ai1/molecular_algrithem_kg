"""声明式抽取：配置加载、渲染等价性、二次抽取解析与写图。"""
from __future__ import annotations
import unittest
from pathlib import Path

from capfactory.po import POGraph
from capfactory.semantic import extractspec as ES
from capfactory.semantic.extractspec import loader, refine, render

TEXT = ("MolMiner is a fragment-based 3D-aware model for molecular design. "
        "We evaluate on ZINC and QM9 with validity and novelty.")
ARGS = dict(title="MolMiner", paper_text=TEXT,
            code_symbols="def encode(x): ...", rule_hints="method: generation")


class TestConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = loader.load(force=True)

    def test_no_errors(self):
        self.assertEqual(self.d["errors"], [])

    def test_stage_count_and_fields(self):
        self.assertEqual(len(self.d["stages"]), 6)
        e1 = self.d["stages"]["E1_paper"]
        self.assertIn("research_question", e1.fields)
        self.assertEqual(e1.classes, ["Paper"])

    def test_refine_specs(self):
        # S2 升级后：R1 贡献 / R2 实验组 / R3 假设 / R4 图表 / R5 引用
        self.assertGreaterEqual(len(self.d["refines"]), 5)
        r = self.d["refines"]["R1_contribution"]
        self.assertEqual(r.cls, "Contribution")
        self.assertEqual(r.relation, "DECLARES")
        self.assertIn("statement", r.field_names)
        self.assertTrue(any(f.enum for f in r.fields))

    def test_node_id_has_arxiv(self):
        for r in self.d["refines"].values():
            self.assertIn("{arxiv_id}", r.node_id)


class TestRenderEquivalence(unittest.TestCase):
    """配置渲染必须与既有硬编码逐字节一致（迁移不改行为）。"""

    def test_stage_order(self):
        from capfactory.semantic.extraction.prompts import stages as old
        self.assertEqual(old(), render.stages())

    def test_prompt_identical_for_unmodified_stages(self):
        """E4/E5/E6 未加字段，应与旧实现逐字节一致（证明机制没坏）。"""
        from capfactory.semantic.extraction.prompts import render as old
        for st in ("E4_values", "E5_relations", "E6_lineage"):
            self.assertEqual(old(st, **ARGS), render.render(st, **ARGS), st)

    def test_modified_stages_contain_new_fields(self):
        """E1–E3 有意新增方法论字段，prompt 必须包含它们。"""
        e1 = render.render("E1_paper", **ARGS)
        for k in ("paradigm", "evidence_type", "section_map"):
            self.assertIn(k, e1)
        e2 = render.render("E2_algorithm", **ARGS)
        for k in ("assumptions", "is_novel_component"):
            self.assertIn(k, e2)
        e3 = render.render("E3_benchmark", **ARGS)
        for k in ("protocol", "contribution_link"):
            self.assertIn(k, e3)

    def test_contract_contains_class_fields(self):
        spec = loader.stages()["E2_algorithm"]
        txt = render.contract_text(spec)
        self.assertIn("Algorithm:", txt)
        self.assertIn("AlgorithmModule:", txt)


class TestRefineLocate(unittest.TestCase):
    def test_locate_skips_table_captions(self):
        md = Path("data/docx/2411.06608.md")
        if not md.exists():
            self.skipTest("缺 md")
        spec = loader.refines()["R1_contribution"]
        paras = refine.locate_paragraphs(md, spec)
        self.assertTrue(paras)
        for p in paras:
            self.assertFalse(p["text"].lower().lstrip().startswith(
                ("table", "figure")), p["text"][:40])

    def test_prompt_has_context(self):
        spec = loader.refines()["R1_contribution"]
        p = refine.build_prompt(spec, context="我们在本文提出 X。",
                                existing="Algorithm:MolMiner")
        self.assertIn("我们在本文提出 X", p)
        self.assertIn("Algorithm:MolMiner", p)
        self.assertIn("statement", p)


class TestRefineParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = loader.refines()["R1_contribution"]

    def test_enum_enforced(self):
        out = refine.parse_payload(self.spec, {"contributions": [
            {"statement": "提出片段化 3D 生成", "kind": "method",
             "evidence": "we propose MolMiner"},
            {"statement": "x", "kind": "nonsense", "evidence": "y"}]})
        self.assertEqual(len(out["items"]), 1)
        self.assertTrue(any("不在枚举" in i for i in out["issues"]))

    def test_required_enforced(self):
        out = refine.parse_payload(self.spec, {"contributions": [
            {"kind": "method"}]})
        self.assertEqual(out["items"], [])
        self.assertTrue(any("缺必填" in i for i in out["issues"]))

    def test_bad_json(self):
        out = refine.parse_payload(self.spec, "not json")
        self.assertEqual(out["items"], [])
        self.assertIn("JSON", out["issues"][0])


class TestApply(unittest.TestCase):
    def test_creates_nodes_and_relation(self):
        g = POGraph("t")
        g.node("paper:2411.06608", "Paper", "MolMiner", arxiv_id="2411.06608")
        spec = loader.refines()["R1_contribution"]
        r = refine.apply_to_graph(g, spec, "2411.06608", [
            {"statement": "提出片段化 3D 生成", "kind": "method",
             "evidence": "we propose"}])
        self.assertEqual(r["nodes"], 1)
        nid = r["ids"][0]
        self.assertTrue(nid.startswith("contribution:2411.06608:"))
        self.assertEqual(g.nodes[nid].attrs.get("kind"), "method")
        rels = {a.relation for a in g.assertions}
        self.assertIn("DECLARES", rels)

    def test_no_parent_returns_error(self):
        g = POGraph("t")
        spec = loader.refines()["R1_contribution"]
        r = refine.apply_to_graph(g, spec, "9999.99999", [{"statement": "x"}])
        self.assertEqual(r["nodes"], 0)
        self.assertEqual(r["error"], "no_parent")


if __name__ == "__main__":
    unittest.main()
