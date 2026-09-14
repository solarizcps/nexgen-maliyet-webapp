# -*- coding: utf-8 -*-
"""Phase 2 local DB tests — isolated test database only."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from app import create_app
from db.connection import db_transaction, init_db
from services.calc_engine import calculate
from services.import_data import import_localstorage
from services.repository import fetch_all_data, save_materials
from tests.test_helpers import auth_client, get_csrf, login_client


class Phase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="nexgen-phase2-test-")
        cls._db = os.path.join(cls._tmpdir, "test.db")
        config.DB_PATH = cls._db
        config.DATA_DIR = cls._tmpdir
        init_db(force=True)
        cls.import_report = import_localstorage(force_recreate=False)
        cls.app = create_app({"TESTING": True})
        cls.client, cls.csrf = auth_client(cls.app)

    def setUp(self):
        data = fetch_all_data()
        if len(data.get("expenses") or []) < 9 or len(data.get("formulas") or []) < 2:
            import_localstorage(force_recreate=True)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["source"], "sqlite")

    def test_foreign_keys(self):
        with db_transaction() as conn:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1)

    def test_integrity(self):
        r = self.client.get("/api/integrity")
        d = r.json
        self.assertTrue(d["foreign_keys_enabled"])
        self.assertEqual(d["orphan_formula_lines"], 0)
        self.assertEqual(d["duplicate_material_codes"], 0)

    def test_import_counts(self):
        rep = self.import_report
        self.assertEqual(rep["source_materials"], 18)
        self.assertGreaterEqual(rep["materials_db_count"], 23)
        self.assertGreaterEqual(rep["formulas_db_count"], 4)
        self.assertEqual(rep["formulas_db_count"], 4)
        self.assertFalse(rep["synthetic_neo_imported"])
        self.assertAlmostEqual(rep["aym_total_kg"], 87.226, places=3)
        self.assertAlmostEqual(rep["aym_eva18_price"], 1.9, places=2)
        self.assertAlmostEqual(rep["aym_eva18_line_cost"], 66.5, places=2)

    def test_aym_calculation(self):
        data = fetch_all_data()
        aym = next(f for f in data["formulas"] if f["id"] == "aym")
        c = calculate(data, aym)
        self.assertTrue(c["ok"], c["errors"])
        self.assertAlmostEqual(c["kg"], 87.226, places=3)
        self.assertAlmostEqual(c["cashRawKg"], 1.690, places=3)
        self.assertAlmostEqual(c["overhead"], 0.0837, places=4)
        self.assertAlmostEqual(c["cashCost"], 1.774, places=3)
        self.assertAlmostEqual(c["cashSale"], 2.129, places=3)

    def test_term_calc_17kg_eva18(self):
        data = fetch_all_data()
        formula = {
            "id": "test-term",
            "months": 6,
            "monthlyRate": 2,
            "profit": 20,
            "lines": [{"materialId": data["materials"][0]["id"], "kg": 17}],
        }
        eva = next(m for m in data["materials"] if m["code"] == "EVA-18")
        formula["lines"][0]["materialId"] = eva["id"]
        c = calculate(data, formula)
        self.assertTrue(c["ok"])
        expected_raw = 1.9 * (1 + 0.02 * 6) * 17
        self.assertAlmostEqual(c["rawKg"], expected_raw / 17, places=4)
        expected_sale = (c["cost"] * 1.2)
        self.assertAlmostEqual(c["sale"], expected_sale, places=4)

    def test_material_save_and_reload(self):
        data = fetch_all_data()
        mats = data["materials"]
        eva = next(m for m in mats if m["code"] == "EVA-18")
        eva["cash"] = 1.95
        ver = data["versions"]["materials"]
        result, code, err = save_materials({"materials": mats, "version": ver})
        self.assertIsNone(err, err)
        self.assertEqual(code, 200)
        data2 = fetch_all_data()
        eva2 = next(m for m in data2["materials"] if m["code"] == "EVA-18")
        self.assertAlmostEqual(eva2["cash"], 1.95)
        # restore
        eva["cash"] = 1.9
        save_materials({"materials": mats, "version": data2["versions"]["materials"]})

    def test_conflict_409(self):
        data = fetch_all_data()
        save_materials(
            {"materials": data["materials"], "version": data["versions"]["materials"]}
        )
        _, code, err = save_materials(
            {"materials": data["materials"], "version": 1}
        )
        self.assertEqual(code, 409)
        self.assertIn("Versiyon", err)

    def test_referenced_material_delete_blocked(self):
        data = fetch_all_data()
        eva = next(m for m in data["materials"] if m["code"] == "EVA-18")
        mats = [m for m in data["materials"] if m["id"] != eva["id"]]
        _, code, err = save_materials(
            {"materials": mats, "version": data["versions"]["materials"]}
        )
        self.assertEqual(code, 400)
        self.assertIn("Referanslı", err)

    def test_import_idempotent(self):
        before = fetch_all_data()
        rep2 = import_localstorage(force_recreate=False)
        after = fetch_all_data()
        self.assertEqual(len(before["materials"]), len(after["materials"]))
        self.assertEqual(len(before["formulas"]), len(after["formulas"]))
        self.assertGreaterEqual(len(before["formulas"]), 4)
        self.assertGreater(len(rep2["duplicates"]), 0)

    def test_api_data_endpoint(self):
        r = self.client.get("/api/data")
        self.assertEqual(r.status_code, 200)
        d = r.json
        self.assertEqual(d["meta"]["source"], "sqlite")
        self.assertGreaterEqual(len(d["materials"]), 18)

    def test_formula_kg_comma_save(self):
        data = fetch_all_data()
        aym = next(f for f in data["formulas"] if f["id"] == "aym")
        zno = next(
            l for l in aym["lines"] if l["materialId"].endswith("6sm1xt") or True
        )
        for line in aym["lines"]:
            mat = next(m for m in data["materials"] if m["id"] == line["materialId"])
            if mat["code"] == "ZNO":
                line["kg"] = 0.85
        r = self.client.put(
            "/api/formulas",
            json={"formulas": data["formulas"], "version": data["versions"]["formulas"]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(r.status_code, 200)
        data2 = fetch_all_data()
        aym2 = next(f for f in data2["formulas"] if f["id"] == "aym")
        zno_line = next(
            l
            for l in aym2["lines"]
            if next(m for m in data2["materials"] if m["id"] == l["materialId"])[
                "code"
            ]
            == "ZNO"
        )
        self.assertAlmostEqual(zno_line["kg"], 0.85, places=2)

    def test_calc_save_api(self):
        data = fetch_all_data()
        r = self.client.put(
            "/api/calc",
            json={
                "formulaId": "aym",
                "months": 6,
                "monthlyRate": 0,
                "profit": 20,
                "version": data["versions"]["calc"],
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("savedAt", r.json)

    def test_api_error_simulation(self):
        iso_dir = tempfile.mkdtemp(prefix="nexgen-api-err-")
        iso_db = os.path.join(iso_dir, "err.db")
        old_db, old_data = config.DB_PATH, config.DATA_DIR
        try:
            config.DB_PATH = iso_db
            config.DATA_DIR = iso_dir
            init_db(force=True)
            import_localstorage(force_recreate=False)
            os.environ["NEXGEN_SIMULATE_DB_ERROR"] = "1"
            err_app = create_app({"TESTING": True})
            c, csrf = auth_client(err_app)
            r = c.put(
                "/api/expenses",
                json={"productionKg": 420000, "usdTry": 42.45, "expenses": [], "version": 1},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(r.status_code, 500)
        finally:
            os.environ.pop("NEXGEN_SIMULATE_DB_ERROR", None)
            config.DB_PATH = old_db
            config.DATA_DIR = old_data


if __name__ == "__main__":
    unittest.main(verbosity=2)
