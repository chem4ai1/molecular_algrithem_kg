"""MolMiner 复现端到端测试：编译 → rubric 树 → 脚本执行 → 判定 → 锚点。

工作区：`storage/repro_test/molminer`（由 compile_reprospec + run_repro lite 生成）。
本测试只读产物 + 独立执行 REPRO_SCRIPT.py，不重复跑 lite。
"""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

WS = Path("storage/repro_test/2411.06608")
SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")
APP = Path("storage_cf/sciforge/app_reproduction.json")
AID = "2411.06608"
KINDS = {"method", "code_grounding", "protocol", "numeric", "ordering"}


def _load(name):
    return json.loads((WS / name).read_text(encoding="utf-8"))


@unittest.skipUnless(WS.exists(), "先跑 stages/4_reproduction/compile_run.py")
class TestReproSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = _load("REPRO_SPEC.json")
        cls.sau = _load("SAU_LIST.json")["sau"]

    def test_spec_has_all_kinds(self):
        self.assertEqual({s["kind"] for s in self.sau}, KINDS)
        self.assertGreater(len(self.sau), 60, "SAU 数量异常")

    def test_spec_hash_stable(self):
        from capfactory.reprospec.compiler import compile_reprospec
        again = compile_reprospec(paper_id="paper:" + AID, out_dir=None)
        self.assertEqual(again.spec_hash, self.spec["spec_hash"])
        self.assertEqual(len(again.sau), len(self.sau))

    def test_sau_ids_unique_and_required_typed(self):
        ids = [s["id"] for s in self.sau]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(isinstance(s["required"], bool) for s in self.sau))

    def test_every_sau_traces_back_to_graph(self):
        from capfactory.po import POGraph
        ids = set(POGraph.load(str(SEM)).nodes) | set(POGraph.load(str(APP)).nodes)
        miss = [x for s in self.sau for x in s["source_node_ids"]
                if x not in ids]
        self.assertEqual(miss, [], f"{len(miss)} 个 source_node_id 无法回溯")


class TestRubricTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _load("RUBRIC_TREE.json")
        cls.scores = _load("RUBRIC_TREE_SCORES.json")

    def test_all_mounted(self):
        self.assertEqual(self.tree["n_unmounted"], 0)
        self.assertEqual(self.tree["n_leaves"], self.tree["n_mounted"])

    def test_depth_and_branches(self):
        self.assertEqual(self.tree["depth_max"], 3)
        self.assertGreater(self.tree["n_branches"], 5)
        self.assertTrue(all(b["path"].startswith("paper:" + AID)
                            for b in self.tree["branches"]))

    def test_score_aggregation(self):
        self.assertGreaterEqual(self.scores["root_score"], 0.0)
        self.assertLessEqual(self.scores["root_score"], 1.0)
        self.assertEqual(self.scores["n_leaves"], self.tree["n_leaves"])
        for b in self.scores["by_branch"]:
            self.assertEqual(b["failed"], b["score"] < 1.0)


class TestRuntimeGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load("app_repro_runtime.json")

    def test_rubric_nodes(self):
        rn = [n for n in self.g["nodes"] if n["type"] == "RubricNode"]
        self.assertTrue({"root", "branch", "leaf"} <=
                        {n["attrs"].get("node_role") for n in rn})

    def test_has_sau_edges(self):
        e = [a for a in self.g["assertions"] if a["relation"] == "HAS_SAU"]
        leaves = [n for n in self.g["nodes"] if n["type"] == "RubricNode"
                  and n["attrs"].get("node_role") == "leaf"]
        self.assertEqual(len(e), len(leaves))

    def test_no_rubric_nodes_in_global_graphs(self):
        for f in (SEM, APP):
            g = json.loads(Path(f).read_text(encoding="utf-8"))
            self.assertFalse([n for n in g["nodes"]
                              if n["type"] == "RubricNode"], str(f))


class TestReproScriptExecution(unittest.TestCase):
    """真正执行 REPRO_SCRIPT.py（自包含，约 0.1s）。"""

    @classmethod
    def setUpClass(cls):
        cls.p = subprocess.run(
            [sys.executable, "REPRO_SCRIPT.py"], cwd=str(WS),
            capture_output=True, text=True, timeout=300)
        cls.out = json.loads(cls.p.stdout) if cls.p.returncode == 0 else {}

    def test_exit_zero(self):
        self.assertEqual(self.p.returncode, 0, self.p.stderr[-800:])

    def test_payload_shape(self):
        self.assertEqual(self.out.get("status"), "PASS")
        stages = self.out.get("stages") or {}
        self.assertEqual(set(stages), {"subset", "full"})
        for s in stages.values():
            self.assertGreater(s["n_rows"], 0)
            self.assertGreater(s["steps_executed"], 0)

    def test_symbol_trace_references_modules(self):
        trace = self.out["stages"]["subset"]["symbol_trace"]
        self.assertTrue(trace)
        self.assertTrue(all("module" in x for x in trace))

    def test_matches_raw_results(self):
        raw = _load("raw_results.json")
        self.assertTrue(raw)
        rows = {s["n_rows"] for s in self.out["stages"].values()}
        self.assertTrue(any(str(r) in json.dumps(raw) for r in rows))


class TestVerdictsAndEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = _load("SAU_VERDICTS.json")
        cls.e = _load("FINAL_EVALUATION.json")["evaluation"]
        cls.anchors = _load("CLAIM_ANCHORS.json")

    def test_every_sau_has_verdict(self):
        sau = _load("SAU_LIST.json")["sau"]
        self.assertEqual(len(self.v["verdicts"]), len(sau))
        self.assertEqual({x["sau_id"] for x in self.v["verdicts"]},
                         {s["id"] for s in sau})

    def test_verdict_values_legal(self):
        legal = {"aligned", "mismatch", "stub", "absent", "unverified"}
        for x in self.v["verdicts"]:
            self.assertIn(x["verdict"], legal)

    def test_overall_and_metrics(self):
        self.assertIn(self.e["overall"], {"PASS", "PARTIAL", "BLOCKED"})
        self.assertGreaterEqual(self.e["coverage"], 0.9)
        self.assertEqual(self.e["exec_rate"], 1.0)
        self.assertIn("align_mixed", self.e)

    def test_mismatch_has_reason(self):
        bad = [x for x in self.v["verdicts"] if x["verdict"] == "mismatch"]
        self.assertTrue(bad, "MolMiner 应存在 method mismatch（真实信号）")
        for x in bad:
            self.assertTrue(x.get("note") or x.get("drift_type"))

    def test_anchor_hashes(self):
        for k in ("spec_hash", "code_sha", "inputs_sha", "outputs_sha"):
            self.assertIn(k, self.anchors)
            self.assertTrue(str(self.anchors[k]).startswith("sha256:"), k)
        self.assertIn("double_run_equal", self.anchors)


class TestNumericHelpers(unittest.TestCase):
    """REPRO_SCRIPT.py 的归一化函数必须能处理论文里的脏数据。"""

    @classmethod
    def setUpClass(cls):
        src = (WS / "REPRO_SCRIPT.py").read_text(encoding="utf-8")
        cls.ns = {}
        exec(compile(src.split("def main()")[0], "REPRO_SCRIPT.py", "exec"),
             cls.ns)

    def test_to_float(self):
        f = self.ns["to_float"]
        self.assertAlmostEqual(f("99.6"), 99.6)
        self.assertAlmostEqual(f("1,234"), 1234.0)
        self.assertAlmostEqual(f("0.90±0.01"), 0.90)
        self.assertAlmostEqual(f("98%"), 98.0)
        self.assertIsNone(f("n/a"))

    def test_normalize_model_and_metric(self):
        self.assertEqual(self.ns["normalize_model"]("MolMiner (ours)"),
                         "MolMiner")
        self.assertEqual(self.ns["normalize_model"]("GDSS*"), "GDSS")
        nmet = self.ns["normalize_metric_name"]
        self.assertEqual(nmet("Validity (%)"), "validity")
        self.assertEqual(nmet("Uniqueness (%)"), "uniqueness")


if __name__ == "__main__":
    unittest.main()
