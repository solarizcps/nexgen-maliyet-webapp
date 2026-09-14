# -*- coding: utf-8 -*-
"""Kg save, response contract, calc refresh, and Waitress stability tests."""
import json
import os
import sqlite3
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from db.migrate_neo_overhead import NEO_FORMULA_ID, migrate_neo_overhead
from services.calc_engine import formula_total_kg
from services.import_data import import_localstorage
from services.repository import fetch_all_data
from tests.test_helpers import (
    TEST_PASSWORD,
    TEST_USERNAME,
    auth_client,
    setup_test_app,
)


def _neo_profor_kg(data):
    neo = next(f for f in data["formulas"] if f["id"] == NEO_FORMULA_ID)
    profor = next(
        m for m in data["materials"] if m["code"] == "PROFOR"
    )
    line = next(l for l in neo["lines"] if l["materialId"] == profor["id"])
    return line, neo


class KgSaveCalcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-kg-save-")
        import_localstorage(force_recreate=False)
        with cls.app.app_context():
            from db.connection import db_transaction

            with db_transaction() as conn:
                migrate_neo_overhead(conn)
        cls.client, cls.csrf = auth_client(cls.app)

    def _save_formulas(self, formulas, version):
        return self.client.put(
            "/api/formulas",
            json={"formulas": formulas, "version": version},
            headers={"X-CSRF-Token": self.csrf},
        )

    def test_save_response_json_contract(self):
        data = fetch_all_data()
        r = self._save_formulas(data["formulas"], data["versions"]["formulas"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/json", r.content_type)
        body = r.get_json()
        self.assertTrue(body.get("ok"))
        self.assertIn("savedAt", body)
        self.assertIn("version", body)

    def test_profor_128_to_200_kg(self):
        data = fetch_all_data()
        line, neo = _neo_profor_kg(data)
        line["kg"] = 2.0
        r = self._save_formulas(data["formulas"], data["versions"]["formulas"])
        self.assertEqual(r.status_code, 200)
        data2 = fetch_all_data()
        line2, neo2 = _neo_profor_kg(data2)
        self.assertAlmostEqual(line2["kg"], 2.0, places=3)
        self.assertAlmostEqual(formula_total_kg(neo2), 82.55, places=2)

    def test_profor_200_back_to_128(self):
        data = fetch_all_data()
        line, _ = _neo_profor_kg(data)
        line["kg"] = 1.28
        r = self._save_formulas(data["formulas"], data["versions"]["formulas"])
        self.assertEqual(r.status_code, 200)
        data2 = fetch_all_data()
        _, neo2 = _neo_profor_kg(data2)
        self.assertAlmostEqual(formula_total_kg(neo2), 81.83, places=2)

    def test_turkish_decimal_comma_parsed_via_api(self):
        data = fetch_all_data()
        line, _ = _neo_profor_kg(data)
        line["kg"] = "1,28"
        r = self._save_formulas(data["formulas"], data["versions"]["formulas"])
        self.assertEqual(r.status_code, 200)
        data2 = fetch_all_data()
        line2, _ = _neo_profor_kg(data2)
        self.assertAlmostEqual(line2["kg"], 1.28, places=3)

    def test_invalid_material_rolls_back(self):
        data = fetch_all_data()
        before = fetch_all_data()
        data["formulas"][0]["lines"][0]["materialId"] = "missing-material-id"
        r = self._save_formulas(data["formulas"], data["versions"]["formulas"])
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertFalse(body.get("ok"))
        after = fetch_all_data()
        self.assertEqual(len(before["formulas"]), len(after["formulas"]))
        self.assertEqual(
            before["versions"]["formulas"], after["versions"]["formulas"]
        )

    def test_csrf_missing_returns_403_json(self):
        data = fetch_all_data()
        r = self.client.put(
            "/api/formulas",
            json={"formulas": data["formulas"], "version": data["versions"]["formulas"]},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("application/json", r.content_type)

    def test_calculate_after_save_uses_new_kg(self):
        data = fetch_all_data()
        line, _ = _neo_profor_kg(data)
        line["kg"] = 2.0
        self._save_formulas(data["formulas"], data["versions"]["formulas"])
        calc = self.client.get(f"/api/calculate/{NEO_FORMULA_ID}")
        self.assertEqual(calc.status_code, 200)
        body = calc.get_json()
        self.assertAlmostEqual(body["result"]["recipe_total_kg"], 82.55, places=2)

    def test_neo_profit_preserved(self):
        data = fetch_all_data()
        neo = next(f for f in data["formulas"] if f["id"] == NEO_FORMULA_ID)
        neo["profit"] = 20
        self._save_formulas(data["formulas"], data["versions"]["formulas"])
        data2 = fetch_all_data()
        neo2 = next(f for f in data2["formulas"] if f["id"] == NEO_FORMULA_ID)
        self.assertAlmostEqual(float(neo2["profit"]), 20.0, places=2)


class WaitressSaveStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.join(ROOT, "data", "waitress_stability_tmp")
        os.makedirs(cls.tmp, exist_ok=True)
        cls.db = os.path.join(cls.tmp, "test.db")
        if os.path.exists(cls.db):
            os.remove(cls.db)
        cls.port = 2344
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.env = os.environ.copy()
        cls.env["NEXGEN_PORT"] = str(cls.port)
        cls.env["NEXGEN_HOST"] = "127.0.0.1"
        cls.env["NEXGEN_DB_PATH"] = cls.db
        cls.env["NEXGEN_SECRET_FILE"] = os.path.join(cls.tmp, ".secret")
        cls.env["NEXGEN_ENV"] = "test"
        cls.env["NEXGEN_WSGI"] = "waitress"
        with open(cls.env["NEXGEN_SECRET_FILE"], "w", encoding="utf-8") as f:
            f.write("test-secret-key-for-waitress-stability")
        from db.connection import init_db

        config.DB_PATH = cls.db
        config.DATA_DIR = cls.tmp
        init_db(force=True)
        import_localstorage(force_recreate=False)
        from db.connection import db_transaction

        with db_transaction() as conn:
            migrate_neo_overhead(conn)
        cls.proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "wsgi.py")],
            cwd=ROOT,
            env=cls.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(40):
            try:
                urllib.request.urlopen(cls.base + "/api/health", timeout=1)
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            cls.tearDownClass()
            raise RuntimeError("Waitress did not start")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "proc", None):
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    def _login_session(self):
        import re

        import requests

        s = requests.Session()
        html = s.get(self.base + "/login").text
        csrf = re.search(r"__LOGIN_CSRF\s*=\s*['\"]([^'\"]+)", html).group(1)
        lr = s.post(
            self.base + "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        body = lr.json()
        s.headers["X-CSRF-Token"] = body.get("csrfToken") or csrf
        return s

    def test_ten_saves_keep_process_alive(self):
        import requests

        s = self._login_session()
        pid_before = self.proc.pid
        for i in range(10):
            data = s.get(self.base + "/api/data").json()
            neo = next(f for f in data["formulas"] if f["id"] == NEO_FORMULA_ID)
            profor = next(m for m in data["materials"] if m["code"] == "PROFOR")
            line = next(l for l in neo["lines"] if l["materialId"] == profor["id"])
            line["kg"] = 1.28 if i % 2 == 0 else 2.0
            r = s.put(
                self.base + "/api/formulas",
                json={
                    "formulas": data["formulas"],
                    "version": data["versions"]["formulas"],
                },
                headers={"X-CSRF-Token": s.headers.get("X-CSRF-Token", "")},
            )
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("application/json", r.headers.get("Content-Type", ""))
            body = r.json()
            self.assertTrue(body.get("ok"), body)
            health = s.get(self.base + "/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(self.proc.poll(), None, f"process died on iteration {i}")
        self.assertEqual(self.proc.pid, pid_before)


if __name__ == "__main__":
    unittest.main()
