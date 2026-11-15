"""词表注入标准：top20 筛选 / other 扩表 / 不全量注入 / 无禁止造类提示。"""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from capfactory.semantic.extraction import vocab, prompts, contracts, validator


class TestVocabStandard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patcher = mock.patch.object(vocab, "VOCAB_FILE",
                                         self.tmp / "vocab.json")
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_no_forbidden_classes_in_contract(self):
        c = contracts.contract_text()
        self.assertNotIn("禁止输出", c)
        self.assertIn("other", c)
        self.assertIn("proposed_new", c)

    def test_vocab_not_full_dump_in_prompt(self):
        t = prompts.render("E1_paper", paper_text="molecular generation")
        self.assertIn("动态词表", t)
        self.assertIn("语义层契约", t)
        self.assertNotIn("FORM_VOCAB =", t)
        self.assertNotIn("TASK_TYPES =", t)

    def test_top20_when_vocab_large(self):
        big = [f"task_{i:02d}" for i in range(35)]
        with mock.patch.object(vocab, "BASE_VOCABS",
                               {**vocab.BASE_VOCABS, "big": big}):
            items, total = vocab.select("big", "task_07 is relevant", k=20)
            self.assertEqual(total, 35)
            self.assertEqual(len(items), 20)
            self.assertIn("task_07", items)   # 字面命中优先

    def test_vector_fallback_when_no_literal(self):
        big = [f"concept_{i:02d}" for i in range(30)]
        with mock.patch.object(vocab, "BASE_VOCABS",
                               {**vocab.BASE_VOCABS, "big": big}):
            items, total = vocab.select("big", "concept_12 appears", k=20)
            self.assertEqual(len(items), 20)
            self.assertIn("concept_12", items)

    def test_render_marks_truncation(self):
        big = [f"x_{i:02d}" for i in range(30)]
        with mock.patch.object(vocab, "BASE_VOCABS",
                               {**vocab.BASE_VOCABS, "big": big}):
            r = vocab.render("some text")
            self.assertIn("已按向量相似度筛选", r)

    def test_other_collects_and_promotes(self):
        r1 = vocab.observe("form", "NEW_FORM")
        self.assertTrue(r1["observed"])
        self.assertFalse(r1["promoted"])
        self.assertNotIn("NEW_FORM", vocab.values("form"))
        r2 = vocab.observe("form", "NEW_FORM")
        self.assertTrue(r2["promoted"])
        self.assertIn("NEW_FORM", vocab.values("form"))

    def test_validator_out_of_vocab_becomes_other(self):
        d, iss = validator.validate("E1_paper", {
            "research_question": "Q",
            "problem_category": "NEW_TASK_XYZ"}, source_text="x")
        self.assertEqual(d["problem_category"], "other")
        self.assertTrue(any("out_of_vocab" in x for x in iss))
        self.assertEqual(validator.fatal(iss), [])

    def test_manual_promote(self):
        self.assertTrue(vocab.promote("form", "CUSTOM_FORM"))
        self.assertFalse(vocab.promote("form", "CUSTOM_FORM"))
        self.assertIn("CUSTOM_FORM", vocab.values("form"))

    def test_stats(self):
        s = vocab.stats()
        self.assertEqual(s["limit"], 20)
        self.assertEqual(s["promote_after"], 2)
        self.assertIn("task_type", s["sizes"])


if __name__ == "__main__":
    unittest.main()
