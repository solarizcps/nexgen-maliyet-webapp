# -*- coding: utf-8 -*-
"""NEO TABAN formula migration and calc tests."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db.connection import db_transaction, init_db
from db.migrate_neo_overhead import NEO_FORMULA_ID, migrate_neo_overhead
from services.calc_engine import calculate, formula_total_kg
from services.import_data import import_localstorage
from services.repository import fetch_all_data
from tests.test_helpers import auth_client, setup_test_app


class NeoTabanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-neo-")
        import_localstorage(force_recreate=False)
        cls.client, cls.csrf = auth_client(cls.app)
        cls.data = fetch_all_data()

    def test_neo_exists(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        self.assertEqual(f["company"], "NEO TABAN")
        self.assertEqual(f["name"], "NORMAL")
        self.assertEqual(f["colorName"], "Ekru")
        self.assertEqual(f["colorCode"], "0235")
        self.assertEqual(f["formulaDate"], "2026-09-14")
        self.assertAlmostEqual(f["baseExpansionMeasure"], 1.45, places=2)

    def test_duplicate_blocked(self):
        with db_transaction() as conn:
            rep = migrate_neo_overhead(conn)
        self.assertFalse(rep["neo_imported"])

    def test_twelve_lines(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        self.assertEqual(len(f["lines"]), 12)

    def test_total_kg(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        self.assertAlmostEqual(formula_total_kg(f), 81.83, places=3)

    def test_material_ids(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        codes = {l["code"] for l in f["lines"]}
        expected = {
            "EVA-28", "EVA-18", "POE-565", "TPE-8201", "CACO3", "ZNO", "ZNST",
            "STEARIC", "TAIC", "PEWAX", "DCP99", "PROFOR",
        }
        self.assertEqual(codes, expected)
        for line in f["lines"]:
            self.assertTrue(line["materialId"])

    def test_profor_binding(self):
        profor = next(m for m in self.data["materials"] if m["code"] == "PROFOR")
        self.assertEqual(profor["name"], "PROFOR")
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        line = next(l for l in f["lines"] if l["code"] == "PROFOR")
        self.assertAlmostEqual(line["kg"], 1.28, places=3)
        self.assertEqual(line["materialId"], profor["id"])

    def test_expansion_not_in_cost(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        base = calculate(self.data, f)
        bumped = calculate(self.data, {**f, "baseExpansionMeasure": 99.99})
        self.assertAlmostEqual(base["cashSale"], bumped["cashSale"], places=6)

    def test_valid_calc_all_prices(self):
        f = next(x for x in self.data["formulas"] if x["id"] == NEO_FORMULA_ID)
        c = calculate(self.data, f)
        self.assertTrue(c["valid"], c["errors"])
        cash_raw = sum(
            next(m for m in self.data["materials"] if m["id"] == l["materialId"])["cash"] * l["kg"]
            for l in f["lines"]
        )
        self.assertAlmostEqual(c["cashRawKg"], cash_raw / 81.83, places=4)

    def test_api_calculate(self):
        r = self.client.get("/api/calculate/" + NEO_FORMULA_ID)
        self.assertTrue(r.json["result"]["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
