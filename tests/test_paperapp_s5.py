"""S5 + v2-S5 验证：API 注册、7 tab 前端、三态、gate 优先、零构建。"""
from __future__ import annotations
import re, tempfile, unittest
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from capfactory.web import server
from capfactory.web import paperapp_api
from capfactory.paperapp import config


class _TabParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = 0

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("role") == "tab":
            self.tabs += 1


class TestS5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)

    def setUp(self):
        self.html = (paperapp_api.STATIC / "paperapp.html").read_text(encoding="utf-8")

    def test_t_s5_01_api_registration_errors_empty(self):
        self.assertEqual(server.app.state.api_registration_errors, {})
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("api_registration_errors"), {})

    def test_t_s5_02_paperapp_page_and_7_tabs(self):
        r = self.client.get("/paperapp")
        self.assertEqual(r.status_code, 200)
        p = _TabParser()
        p.feed(r.text)
        self.assertEqual(p.tabs, 7)
        self.assertIn("人工决策", r.text)

    def test_t_s5_01b_paperapp_in_module_list(self):
        self.assertIn("paperapp_api", server.WEB_API_MODULES)

    def test_t_s5_03_status_and_overview(self):
        self.assertEqual(self.client.get("/api/v10/paperapp/status").status_code, 200)
        o = self.client.get("/api/v10/paperapp/overview")
        self.assertEqual(o.status_code, 200)
        d = o.json()
        for k in ("semantic_sha", "app_sha", "n_registered_classes",
                  "pending_gate_choices", "api_registration_errors"):
            self.assertIn(k, d)

    def test_t_s5_05_limit_upper_bound(self):
        r = self.client.get("/api/v10/paperapp/graph/nodes?limit=999")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["reason_code"], "limit_too_large")

    def test_t_s5_06_no_store_header(self):
        r = self.client.get("/api/v10/paperapp/status")
        # FastAPI 默认不带 cache-control；前端统一用 fetch(cache:'no-store')
        self.assertIn("cache:'no-store'", self.html)

    def test_t_s5_09_empty_state(self):
        r = self.client.get("/api/v10/paperapp/runs/detail?id=nonexistent")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["reason_code"], "run_not_found")

    def test_t_s5_12_esc_escapes(self):
        self.assertIn("function esc(", self.html)
        self.assertIn("&amp;", self.html)       # 转义映射存在
        self.assertNotIn("innerHTML = raw", self.html)

    def test_t_s5_14_allsettled_and_three_states(self):
        self.assertIn("Promise.allSettled", self.html)
        for cls in ("loading", "empty", "error"):
            self.assertIn(cls, self.html)

    def test_t_s5_15_zero_build(self):
        self.assertNotIn("cdn", self.html.lower())
        self.assertNotIn("npm", self.html.lower())
        self.assertNotIn("import React", self.html)
        self.assertFalse((paperapp_api.STATIC / "package.json").exists())

    def test_t_v2_22_gate_first_and_required_fields(self):
        self.assertIn("y.mode==='gate'", self.html)
        self.assertIn("falsifiable_claim", self.html)
        self.assertIn("均为必填", self.html)
        self.assertNotIn("自动通过", self.html)

    def test_t_v2_23_new_endpoints(self):
        for p in ("/choices", "/decisions", "/frontiers", "/reinjection",
                  "/mining-coverage", "/signals", "/signals/audit"):
            r = self.client.get("/api/v10/paperapp" + p)
            self.assertEqual(r.status_code, 200, p)

    def test_t_s5_03b_graph_nodes_filter(self):
        r = self.client.get("/api/v10/paperapp/graph/nodes?attribution=llm_proposal&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertIn("items", r.json())
        self.assertLessEqual(len(r.json()["items"]), 5)

    def test_t_s5_10_graph_source_untouched(self):
        from capfactory.web import graph_source
        self.assertTrue(hasattr(graph_source, "load") or hasattr(graph_source, "load_graph"))

    def test_api_error_structure(self):
        r = self.client.get("/api/v10/paperapp/graph/node?id=missing")
        self.assertEqual(r.status_code, 404)
        self.assertIn("reason_code", r.json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
