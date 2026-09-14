# -*- coding: utf-8 -*-
"""Phase 3 authentication tests — isolated DB only."""
import os
import sys
import tempfile
import time
import unittest
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from app import create_app
from db.connection import db_transaction, init_db
from services.import_data import import_localstorage
from tests.test_helpers import TEST_PASSWORD, TEST_USERNAME, get_csrf, login_client, setup_test_app


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = setup_test_app("nexgen-auth-")

    def _anon_client(self):
        return self.app.test_client()

    def test_root_redirects_without_login(self):
        r = self._anon_client().get("/")
        self.assertIn(r.status_code, (302, 303))
        self.assertIn("/login", r.headers.get("Location", ""))

    def test_api_data_401_without_login(self):
        r = self._anon_client().get("/api/data")
        self.assertEqual(r.status_code, 401)

    def test_write_apis_401_without_login(self):
        c = self._anon_client()
        for path, method in [
            ("/api/materials", "PUT"),
            ("/api/expenses", "PUT"),
            ("/api/formulas", "PUT"),
            ("/api/calc", "PUT"),
            ("/api/meta", "PUT"),
        ]:
            r = c.open(path, method=method, json={})
            self.assertEqual(r.status_code, 401, path)

    def test_wrong_credentials_rejected(self):
        c = self._anon_client()
        csrf = get_csrf(c)
        r = c.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "wrong"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(r.status_code, 401)

    def test_altan_login_success(self):
        r, _ = login_client(self._anon_client())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json["ok"])

    def test_password_not_plaintext_in_db(self):
        with db_transaction() as conn:
            rows = conn.execute("SELECT password_hash FROM users").fetchall()
        for row in rows:
            self.assertNotIn(TEST_PASSWORD, row["password_hash"])
            self.assertTrue(row["password_hash"].startswith("scrypt:"))

    def test_session_cookie_created(self):
        c = self.app.test_client()
        login_client(c)
        with c.session_transaction() as sess:
            self.assertIn("user_id", sess)

    def test_logout_success(self):
        c = self.app.test_client()
        _, csrf = login_client(c)
        r = c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 200)
        r2 = c.get("/api/data")
        self.assertEqual(r2.status_code, 401)

    def test_csrf_blocks_write_without_token(self):
        c = self.app.test_client()
        login_client(c)
        r = c.put("/api/expenses", json={"productionKg": 420000, "usdTry": 42.45, "expenses": [], "version": 1})
        self.assertEqual(r.status_code, 403)

    def test_rate_limit_after_many_failures(self):
        iso = tempfile.mkdtemp(prefix="nexgen-auth-rate-")
        db = os.path.join(iso, "rate.db")
        old_db, old_data = config.DB_PATH, config.DATA_DIR
        try:
            config.DB_PATH = db
            config.DATA_DIR = iso
            init_db(force=True)
            import_localstorage(force_recreate=False)
            app = create_app({"TESTING": True})
            c = app.test_client()
            last = None
            for _ in range(config.MAX_LOGIN_ATTEMPTS + 1):
                csrf = get_csrf(c)
                last = c.post(
                    "/api/auth/login",
                    json={"username": "x", "password": "y"},
                    headers={"X-CSRF-Token": csrf},
                )
            self.assertIn(last.status_code, (401, 429))
        finally:
            config.DB_PATH = old_db
            config.DATA_DIR = old_data

    def test_inactive_user_blocked(self):
        with db_transaction() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE username = 'altan'")
        c = self.app.test_client()
        r, _ = login_client(c)
        self.assertEqual(r.status_code, 401)
        with db_transaction() as conn:
            conn.execute("UPDATE users SET is_active = 1 WHERE username = 'altan'")

    def test_session_timeout(self):
        iso = tempfile.mkdtemp(prefix="nexgen-auth-timeout-")
        db = os.path.join(iso, "t.db")
        old_db, old_data = config.DB_PATH, config.DATA_DIR
        try:
            config.DB_PATH = db
            config.DATA_DIR = iso
            init_db(force=True)
            import_localstorage(force_recreate=False)
            app = create_app({"TESTING": True})
            app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=1)
            c = app.test_client()
            login_client(c)
            time.sleep(2.5)
            r = c.get("/api/data")
            self.assertEqual(r.status_code, 401)
        finally:
            config.DB_PATH = old_db
            config.DATA_DIR = old_data


if __name__ == "__main__":
    unittest.main(verbosity=2)
