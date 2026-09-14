# -*- coding: utf-8 -*-
"""Formula UI isolation, profit calc, and banner state tests — isolated DB only."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app
from services.repository import fetch_all_data
from tests.test_helpers import login_client, setup_test_app


class FormulaUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-formula-ui-")

    def setUp(self):
        self.client = self.app.test_client()
        login_client(self.client)

    def _data(self):
        r = self.client.get("/api/data")
        self.assertEqual(r.status_code, 200)
        return r.json

    def test_formula_expansion_isolated_in_api(self):
        data = self._data()
        by_id = {f["id"]: f for f in data["formulas"]}
        self.assertAlmostEqual(float(by_id["neo-taban"]["baseExpansionMeasure"]), 1.45, places=2)
        for fid in ("aym", "dakirs", "darkir", "wanderfull"):
            val = by_id[fid].get("baseExpansionMeasure")
            self.assertTrue(val is None or val == "", fid)

    def test_neo_profit_save_and_calc(self):
        data = self._data()
        neo = next(f for f in data["formulas"] if f["id"] == "neo-taban")
        neo["profit"] = 15
        _, csrf = login_client(self.client)
        r = self.client.put(
            "/api/formulas",
            json={"formulas": data["formulas"], "version": data["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json.get("ok", True) is not False)
        calc = self.client.get("/api/calculate/neo-taban").json["result"]
        self.assertTrue(calc.get("valid"))
        self.assertEqual(calc["cash_calculation"]["profit"], calc["cash_calculation"]["cost"] * 0.15)

    def test_profit_persists_after_reload(self):
        data = self._data()
        neo = next(f for f in data["formulas"] if f["id"] == "neo-taban")
        neo["profit"] = 12
        _, csrf = login_client(self.client)
        self.client.put(
            "/api/formulas",
            json={"formulas": data["formulas"], "version": data["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf},
        )
        fresh = fetch_all_data()
        saved = next(f for f in fresh["formulas"] if f["id"] == "neo-taban")
        self.assertEqual(float(saved["profit"]), 12.0)
        # restore isolated DB default for other tests in same class
        neo["profit"] = 0
        data2 = self._data()
        _, csrf2 = login_client(self.client)
        self.client.put(
            "/api/formulas",
            json={"formulas": data2["formulas"], "version": data2["versions"]["formulas"]},
            headers={"X-CSRF-Token": csrf2},
        )

    def test_index_ready_has_banner_stack(self):
        html = self.client.get("/").data.decode("utf-8")
        self.assertIn('id="bannerStack"', html)
        self.assertIn('id="btnRetryLoad"', html)

    def test_monthly_production_positive(self):
        data = self._data()
        self.assertGreater(float(data["productionKg"]), 0)


if __name__ == "__main__":
    unittest.main()
