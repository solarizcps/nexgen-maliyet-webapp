# -*- coding: utf-8 -*-
"""Active-formula warning scope — isolated DB only."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.calc_engine import calculate
from services.repository import fetch_all_data
from tests.test_helpers import login_client, setup_test_app


class ActiveWarningScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-warn-scope-")
        cls.data = fetch_all_data()

    def _formula(self, fid):
        return next(f for f in self.data["formulas"] if f["id"] == fid)

    def _missing_count(self, fid):
        c = calculate(self.data, self._formula(fid))
        return c["missing_price_count"]

    def test_neo_no_missing_prices(self):
        self.assertEqual(self._missing_count("neo-taban"), 0)

    def test_dakirs_four_missing(self):
        self.assertEqual(self._missing_count("dakirs"), 4)

    def test_wanderfull_three_missing(self):
        self.assertEqual(self._missing_count("wanderfull"), 3)

    def test_aym_valid(self):
        c = calculate(self.data, self._formula("aym"))
        self.assertTrue(c["valid"])
        self.assertEqual(c["missing_price_count"], 0)

    def test_darkir_valid(self):
        c = calculate(self.data, self._formula("darkir"))
        self.assertTrue(c["valid"])
        self.assertEqual(c["missing_price_count"], 0)

    def test_neo_profit_save_20_isolated(self):
        c = self.app.test_client()
        _, csrf = login_client(c)
        data = c.get("/api/data").json
        formulas = data["formulas"]
        neo = next(f for f in formulas if f["id"] == "neo-taban")
        others = {f["id"]: f["profit"] for f in formulas if f["id"] != "neo-taban"}
        neo["profit"] = 20
        r = c.put(
            "/api/formulas",
            json={"formulas": formulas, "version": data["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json
        self.assertIn("savedAt", body)
        self.assertIn("version", body)
        calc = c.get("/api/calculate/neo-taban").json["result"]
        self.assertTrue(calc["valid"])
        self.assertAlmostEqual(calc["cash_calculation"]["profit"], calc["cash_calculation"]["cost"] * 0.2, places=4)
        fresh = c.get("/api/data").json
        saved_neo = next(f for f in fresh["formulas"] if f["id"] == "neo-taban")
        self.assertEqual(float(saved_neo["profit"]), 20.0)
        for fid, profit in others.items():
            f = next(x for x in fresh["formulas"] if x["id"] == fid)
            self.assertEqual(float(f["profit"]), float(profit))
        # restore neo profit for isolated DB hygiene
        neo["profit"] = 0
        data2 = c.get("/api/data").json
        _, csrf2 = login_client(c)
        c.put(
            "/api/formulas",
            json={"formulas": data2["formulas"], "version": data2["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf2},
        )

    def test_neo_profit_relogin_persists_isolated(self):
        c = self.app.test_client()
        _, csrf = login_client(c)
        data = c.get("/api/data").json
        neo = next(f for f in data["formulas"] if f["id"] == "neo-taban")
        neo["profit"] = 20
        c.put(
            "/api/formulas",
            json={"formulas": data["formulas"], "version": data["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf},
        )
        c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        login_client(c)
        fresh = c.get("/api/data").json
        saved = next(f for f in fresh["formulas"] if f["id"] == "neo-taban")
        self.assertEqual(float(saved["profit"]), 20.0)
        neo2 = next(f for f in fresh["formulas"] if f["id"] == "neo-taban")
        neo2["profit"] = 0
        _, csrf2 = login_client(c)
        c.put(
            "/api/formulas",
            json={"formulas": fresh["formulas"], "version": fresh["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf2},
        )


if __name__ == "__main__":
    unittest.main()
