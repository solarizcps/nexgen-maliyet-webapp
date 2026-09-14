# -*- coding: utf-8 -*-
"""Invalid calc state, stale formula guard, DAKIRS isolated math — test DB only."""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.calc_engine import calculate, formula_total_kg, overhead
from services.repository import fetch_all_data
from tests.test_helpers import auth_client, setup_test_app

# Test-only prices for isolated DAKIRS validation (never written to real DB).
TEST_PAINT_PRICES = {
    "BROWN600": 2.10,
    "BROWN660": 2.20,
    "PYELLOW13": 1.80,
    "YELLOW313": 1.90,
}


def apply_test_prices(data):
    out = copy.deepcopy(data)
    for m in out["materials"]:
        if m["code"] in TEST_PAINT_PRICES:
            m["cash"] = TEST_PAINT_PRICES[m["code"]]
    return out


class CalcInvalidStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, _ = setup_test_app("nexgen-calc-invalid-")
        cls.client, cls.csrf = auth_client(cls.app)
        cls.data = fetch_all_data()

    def _formula(self, fid):
        return next(f for f in self.data["formulas"] if f["id"] == fid)

    def test_aym_valid_has_sale(self):
        c = calculate(self.data, self._formula("aym"))
        self.assertTrue(c["valid"])
        self.assertIsNotNone(c["cashSale"])
        self.assertAlmostEqual(c["cashSale"], 2.129, places=3)

    def test_dakirs_invalid_null_totals(self):
        c = calculate(self.data, self._formula("dakirs"))
        self.assertFalse(c["valid"])
        self.assertIsNone(c["cashSale"])
        self.assertIsNone(c["sale"])
        self.assertIsNone(c["cash_calculation"])
        self.assertEqual(c["missing_price_count"], 4)
        self.assertEqual(
            set(c["missing_materials"]),
            {"BROWN600", "BROWN660", "PYELLOW13", "YELLOW313"},
        )

    def test_wanderfull_invalid_null_totals(self):
        c = calculate(self.data, self._formula("wanderfull"))
        self.assertFalse(c["valid"])
        self.assertIsNone(c["cashSale"])

    def test_api_dakirs_invalid_null(self):
        r = self.client.get("/api/calculate/dakirs")
        res = r.json["result"]
        self.assertFalse(res["valid"])
        self.assertIsNone(res["cashSale"])

    def test_dakirs_recipe_kg(self):
        f = self._formula("dakirs")
        self.assertAlmostEqual(formula_total_kg(f), 85.86, places=2)
        c = calculate(self.data, f)
        self.assertAlmostEqual(c["recipe_total_kg"], 85.86, places=2)

    def test_isolated_dakirs_valid_math(self):
        src = apply_test_prices(self.data)
        f = self._formula("dakirs")
        c = calculate(src, f)
        self.assertTrue(c["valid"], c["errors"])
        self.assertEqual(len(c["allRows"]), 19)
        oh = overhead(src)
        cash_raw = sum(r["cashTotal"] for r in c["allRows"] if not r["invalid"])
        recipe_kg = formula_total_kg(f)
        expected_raw_kg = cash_raw / recipe_kg
        self.assertAlmostEqual(c["cashRawKg"], expected_raw_kg, places=4)
        self.assertAlmostEqual(c["overhead"], oh, places=4)
        expected_cost = expected_raw_kg + oh
        self.assertAlmostEqual(c["cashCost"], expected_cost, places=4)
        expected_profit = expected_cost * f["profit"] / 100
        self.assertAlmostEqual(c["cashProfit"], expected_profit, places=4)
        expected_sale = expected_cost + expected_profit
        self.assertAlmostEqual(c["cashSale"], expected_sale, places=4)

    def test_dakirs_zero_rate_term_same_as_cash(self):
        src = apply_test_prices(self.data)
        f = self._formula("dakirs")
        c = calculate(src, f)
        self.assertTrue(c["term_calculation"]["sameAsCash"])
        self.assertAlmostEqual(c["sale"], c["cashSale"], places=6)

    def test_dakirs_positive_rate_term(self):
        src = apply_test_prices(self.data)
        f = {**self._formula("dakirs"), "monthlyRate": 2}
        c = calculate(src, f)
        self.assertTrue(c["valid"])
        self.assertGreater(c["sale"], c["cashSale"])

    def test_no_partial_sale_when_invalid(self):
        c = calculate(self.data, self._formula("dakirs"))
        self.assertFalse(c["valid"])
        self.assertIsNone(c["cashSale"])
        self.assertNotAlmostEqual(c["cashSale"] or 0, 2.129, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
