# -*- coding: utf-8 -*-
"""UI truth + WANDERFULL reconciliation tests (isolated DB)."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from app import create_app
from db.connection import init_db
from services.calc_engine import calculate, formula_total_kg
from services.import_data import import_localstorage
from services.repository import fetch_all_data, save_materials
from tests.test_helpers import auth_client


class UiTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="nexgen-ui-truth-")
        cls.db = os.path.join(cls.tmp, "test.db")
        config.DB_PATH = cls.db
        config.DATA_DIR = cls.tmp
        init_db(force=True)
        cls.report = import_localstorage(force_recreate=False)
        cls.app = create_app({"TESTING": True})
        cls.client, cls.csrf = auth_client(cls.app)

    def test_four_formulas_in_db(self):
        self.assertGreaterEqual(self.report["formulas_db_count"], 4)
        ids = {f["id"] for f in fetch_all_data()["formulas"]}
        self.assertTrue({"aym", "darkir", "wanderfull", "dakirs"}.issubset(ids))
        self.assertIn("neo-taban", ids)

    def test_wanderfull_kg_exact(self):
        exact = self.report["wanderfull_total_kg_exact"]
        self.assertAlmostEqual(exact, 85.9755, places=4)
        data = fetch_all_data()
        wf = next(f for f in data["formulas"] if f["id"] == "wanderfull")
        self.assertAlmostEqual(formula_total_kg(wf), exact, places=6)
        self.assertEqual(self.report["wanderfull_row_count"], 17)

    def test_why_897_vs_976(self):
        """85.897 = valid rows only; 85.976 = full recipe total (display)."""
        data = fetch_all_data()
        wf = next(f for f in data["formulas"] if f["id"] == "wanderfull")
        c = calculate(data, wf)
        excluded = 0.004 + 0.008 + 0.0665
        self.assertAlmostEqual(c["recipeKg"], 85.9755, places=3)
        self.assertAlmostEqual(c["kg"], 85.897, places=3)
        self.assertAlmostEqual(c["recipeKg"] - c["kg"], excluded, places=4)

    def test_page_saves_present(self):
        data = fetch_all_data()
        for p in ("materials", "expenses", "formulas", "calc"):
            self.assertTrue(data["savedAt"].get(p), f"missing savedAt.{p}")

    def test_zz_missing_price_flow_on_test_db(self):
        data = fetch_all_data()
        mats = data["materials"]
        for code in ("PBLUE154", "BROWN600", "YELLOW313"):
            m = next(x for x in mats if x["code"] == code)
            m["cash"] = 1.5
        save_materials({"materials": mats, "version": data["versions"]["materials"]})
        data2 = fetch_all_data()
        wf = next(f for f in data2["formulas"] if f["id"] == "wanderfull")
        c = calculate(data2, wf)
        self.assertTrue(c["ok"], c["errors"])

    def test_term_zero_rate(self):
        data = fetch_all_data()
        wf = next(f for f in data["formulas"] if f["id"] == "wanderfull")
        self.assertEqual(wf["months"], 6)
        self.assertEqual(wf["monthlyRate"], 0)
        mats = data["materials"]
        for m in mats:
            if m["cash"] == 0:
                m["cash"] = 1.0
        wf_calc = calculate({**data, "materials": mats}, wf)
        self.assertAlmostEqual(wf_calc["sale"], wf_calc["cashSale"], places=6)

    def test_term_positive_rate(self):
        data = fetch_all_data()
        wf = next(f for f in data["formulas"] if f["id"] == "wanderfull")
        wf = {**wf, "monthlyRate": 2}
        mats = [{**m, "cash": m["cash"] if m["cash"] > 0 else 1.0} for m in data["materials"]]
        src = {**data, "materials": mats}
        c = calculate(src, wf)
        self.assertTrue(c["ok"])
        self.assertGreater(c["sale"], c["cashSale"])

    def test_aym_eva18_preserved(self):
        data = fetch_all_data()
        aym = next(f for f in data["formulas"] if f["id"] == "aym")
        c = calculate(data, aym)
        eva = next(r for r in c["allRows"] if r["code"] == "EVA-18")
        self.assertAlmostEqual(eva["kg"], 35, places=3)
        self.assertAlmostEqual(eva["cash"], 1.9, places=2)
        self.assertAlmostEqual(eva["cashTotal"], 66.5, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
