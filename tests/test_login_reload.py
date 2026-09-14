# -*- coding: utf-8 -*-
"""Login/logout data reload regression — isolated DB only."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_helpers import login_client, setup_test_app


class LoginReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-reload-")

    def _data(self, client):
        r = client.get("/api/data")
        self.assertEqual(r.status_code, 200)
        return r.json

    def test_logout_login_data_reload_10_cycles(self):
        c = self.app.test_client()
        for i in range(10):
            _, csrf = login_client(c)
            data = self._data(c)
            self.assertGreaterEqual(len(data["formulas"]), 1, f"cycle {i+1}")
            self.assertGreaterEqual(len(data["materials"]), 1, f"cycle {i+1}")
            self.assertIn(
                data["meta"]["activeFormulaId"],
                [f["id"] for f in data["formulas"]],
                f"cycle {i+1}",
            )
            lo = c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
            self.assertEqual(lo.status_code, 200)
            self.assertEqual(c.get("/api/data").status_code, 401)

    def test_index_has_cache_bust_assets(self):
        c = self.app.test_client()
        login_client(c)
        html = c.get("/").data.decode("utf-8")
        self.assertIn("app.js?v=", html)
        self.assertIn("app.css?v=", html)

    def test_login_page_no_store_cache(self):
        r = self.app.test_client().get("/login")
        self.assertIn("no-store", r.headers.get("Cache-Control", ""))


if __name__ == "__main__":
    unittest.main()
