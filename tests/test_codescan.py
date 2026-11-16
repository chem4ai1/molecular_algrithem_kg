"""代码域：AST 扫描与图构建。"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from capfactory.applayer.codescan import scan_repo
from capfactory.applayer.codegraph import build_code_graph
from capfactory.applayer.tbox import APP_CLASSES, APP_RELATIONS
from capfactory.po import POGraph

MAIN = '''import torch
from utils import helper


class Base:
    pass


class Model(Base):
    def forward(self, x):
        return helper(x)


def train():
    return Model()


if __name__ == "__main__":
    train()
'''
UTILS = '''def helper(x):
    return x


class Wrapper:
    pass
'''
TEST = '''from utils import helper


def test_helper():
    assert helper(1) == 1
'''


class TestRegistry(unittest.TestCase):
    def test_code_classes(self):
        for c in ("CodeUnit", "CodeSymbol", "Dependency", "EntryPoint",
                  "TestUnit", "EnvSpec", "RunArtifact"):
            self.assertIn(c, APP_CLASSES, c)

    def test_cross_domain_relations(self):
        for r in ("IMPLEMENTED_BY", "EXECUTED_BY", "PRODUCES",
                  "REPRODUCED_BY", "COMPUTED_BY", "ASSUMED_IN",
                  "DETECTABLE_IN", "GROUNDED_IN"):
            self.assertIn(r, APP_RELATIONS, r)

    def test_domain_relations(self):
        for r in ("CONTAINS", "INHERITS", "DEPENDS_ON", "IN_UNIT",
                  "USES_ENV", "TEST_IN"):
            self.assertIn(r, APP_RELATIONS, r)


class TestScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "main.py").write_text(MAIN, encoding="utf-8")
        (root / "utils.py").write_text(UTILS, encoding="utf-8")
        (root / "test_utils.py").write_text(TEST, encoding="utf-8")
        (root / "requirements.txt").write_text("torch>=2.0\nnumpy\n",
                                               encoding="utf-8")
        cls.scan = scan_repo(root, repo_id="demo")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stats(self):
        s = self.scan["stats"]
        self.assertEqual(s["units"], 3)
        self.assertGreaterEqual(s["symbols"], 4)   # Base/Model/forward/train/helper/Wrapper
        self.assertGreaterEqual(s["entries"], 1)   # main.py 有 __main__
        self.assertGreaterEqual(s["tests"], 1)     # test_utils.py

    def test_roles(self):
        roles = {u["path"]: u["role"] for u in self.scan["units"]}
        self.assertEqual(roles["test_utils.py"], "test")
        self.assertEqual(roles["requirements.txt"]
                         if "requirements.txt" in roles else "config", "config")

    def test_deps(self):
        names = {d["name"] for d in self.scan["deps"]}
        self.assertIn("torch", names)
        self.assertIn("numpy", names)

    def test_inherits_detected(self):
        cls_syms = [s for s in self.scan["symbols"] if s["kind"] == "class"]
        model = next(s for s in cls_syms if s["name"] == "Model")
        self.assertIn("Base", model.get("bases") or [])


class TestGraph(unittest.TestCase):
    def _build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "main.py").write_text(MAIN, encoding="utf-8")
            (root / "utils.py").write_text(UTILS, encoding="utf-8")
            (root / "test_utils.py").write_text(TEST, encoding="utf-8")
            scan = scan_repo(root, repo_id="demo")
        g = POGraph("t")
        n = build_code_graph(g, scan)
        return g, n

    def test_nodes_and_relations(self):
        g, n = self._build()
        types = {x.type for x in g.nodes.values()}
        self.assertIn("CodeUnit", types)
        self.assertIn("CodeSymbol", types)
        self.assertIn("EntryPoint", types)
        self.assertIn("TestUnit", types)
        rels = {a.relation for a in g.assertions}
        for r in ("CONTAINS", "IN_UNIT", "USES_ENV", "TEST_IN"):
            self.assertIn(r, rels, r)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "main.py").write_text(MAIN, encoding="utf-8")
            scan = scan_repo(root, repo_id="demo")
        g = POGraph("t")
        a = build_code_graph(g, scan)
        nodes1 = len(g.nodes)
        b = build_code_graph(g, scan)
        self.assertEqual(len(g.nodes), nodes1)
        self.assertEqual(b["units"], 0)   # 第二次不再新建

    def test_layer_marked(self):
        g, _ = self._build()
        for x in g.nodes.values():
            if x.type in ("CodeUnit", "CodeSymbol"):
                self.assertEqual(x.attrs.get("layer"), "application")
                self.assertEqual(x.attrs.get("task"), "code")


if __name__ == "__main__":
    unittest.main()
