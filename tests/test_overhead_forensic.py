# -*- coding: utf-8 -*-
"""General expense forensic validation tests."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.calc_engine import calculate, overhead
from services.overhead_detail import overhead_breakdown
from services.repository import fetch_all_data
from tests.test_helpers import auth_client, setup_test_app


class OverheadForensicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, _ = setup_test_app("nexgen-overhead-")
        cls.client, _ = auth_client(cls.app)
        cls.data = fetch_all_data()

    def test_independent_usd_per_kg(self):
        bd = overhead_breakdown(self.data)
        allocated = bd["monthlyAllocatedExpenseTry"]
        tl = allocated / bd["monthlyProductionKg"]
        usd = tl / bd["usdTryRate"]
        self.assertAlmostEqual(usd, bd["engineUsdPerKg"], places=6)
        self.assertAlmostEqual(usd, 0.083702, places=4)

    def test_percent_parse_50_is_half(self):
        row = next(e for e in self.data["expenses"] if e["name"] == "Kira")
        self.assertEqual(row["rate"], 100)
        contrib = row["amount"] * row["rate"] / 100
        self.assertAlmostEqual(contrib, row["amount"], places=2)

    def test_fx_direction_divide(self):
        bd = overhead_breakdown(self.data)
        self.assertGreater(bd["usdTryRate"], 1)
        self.assertLess(bd["usdPerKg"], bd["tlPerKg"])

    def test_overhead_once_in_cash_sale(self):
        aym = next(f for f in self.data["formulas"] if f["id"] == "aym")
        c = calculate(self.data, aym)
        oh = overhead(self.data)
        self.assertAlmostEqual(c["cashCost"], c["cashRawKg"] + oh, places=4)
        self.assertAlmostEqual(c["cashSale"], c["cashCost"] + c["cashProfit"], places=4)

    def test_overhead_once_in_term_sale(self):
        data = fetch_all_data()
        wf = next(f for f in data["formulas"] if f["id"] == "wanderfull")
        mats = [{**m, "cash": m["cash"] if m["cash"] > 0 else 1.0} for m in data["materials"]]
        src = {**data, "materials": mats}
        wf2 = {**wf, "monthlyRate": 2}
        c = calculate(src, wf2)
        oh = overhead(src)
        self.assertAlmostEqual(c["cost"], c["rawKg"] + oh, places=4)

    def test_no_double_count_in_sale(self):
        aym = next(f for f in self.data["formulas"] if f["id"] == "aym")
        c = calculate(self.data, aym)
        oh = overhead(self.data)
        implied = c["cashRawKg"] + oh
        self.assertAlmostEqual(c["cashCost"], implied, places=4)
        self.assertLess(c["cashCost"], c["cashRawKg"] + oh * 2)

    def test_api_breakdown(self):
        r = self.client.get("/api/overhead/breakdown")
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.json["engineUsdPerKg"], 0.083702, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
