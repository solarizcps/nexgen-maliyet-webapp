# -*- coding: utf-8 -*-
"""Port 2333 config and live HTTP checks (read-only against running server)."""
import json
import os
import re
import sys
import unittest
import urllib.error
import urllib.request

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config
from tests.test_helpers import TEST_PASSWORD, TEST_USERNAME


def _get(url, timeout=5):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8"), dict(resp.headers)


class TestPort2333Config(unittest.TestCase):
    def test_default_port_is_2333(self):
        self.assertEqual(config.PORT, 2333)

    def test_host_localhost(self):
        self.assertEqual(config.HOST, "127.0.0.1")


class TestPort2333Live(unittest.TestCase):
    BASE = f"http://{config.HOST}:{config.PORT}"

    @classmethod
    def setUpClass(cls):
        try:
            code, body, _ = _get(cls.BASE + "/api/health")
        except (urllib.error.URLError, TimeoutError):
            raise unittest.SkipTest("NEXGEN not running on port 2333")
        if code != 200:
            raise unittest.SkipTest(f"health HTTP {code}")
        data = json.loads(body)
        if data.get("app") != "NEXGEN Maliyet Merkezi":
            raise unittest.SkipTest("listener is not NEXGEN")

    def test_health_200_and_port(self):
        code, body, _ = _get(self.BASE + "/api/health")
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertTrue(data.get("db_connected"))
        self.assertEqual(data.get("port"), 2333)

    def test_root_redirects_to_login(self):
        code, body, _ = _get(self.BASE + "/")
        self.assertEqual(code, 200)
        self.assertIn("/login", body.lower())

    def test_data_requires_auth(self):
        try:
            _get(self.BASE + "/api/data")
            self.fail("expected 401 without session")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 401)

    def test_login_and_data_reload(self):
        session = requests.Session()
        login_html = session.get(self.BASE + "/login", timeout=5).text
        m = re.search(r"__LOGIN_CSRF\s*=\s*['\"]([^'\"]+)", login_html)
        self.assertTrue(m, "login CSRF token missing")
        csrf = m.group(1)
        lr = session.post(
            self.BASE + "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            headers={"X-CSRF-Token": csrf},
            timeout=5,
        )
        self.assertEqual(lr.status_code, 200)
        csrf = lr.json().get("csrfToken") or csrf

        dr = session.get(self.BASE + "/api/data", timeout=5)
        self.assertEqual(dr.status_code, 200)
        data = dr.json()
        self.assertGreaterEqual(len(data.get("formulas") or []), 5)
        self.assertGreaterEqual(len(data.get("materials") or []), 23)
        self.assertEqual(data.get("productionKg"), 100000.0)

        lo = session.post(
            self.BASE + "/api/auth/logout",
            headers={"X-CSRF-Token": csrf},
            timeout=5,
        )
        self.assertEqual(lo.status_code, 200)
        self.assertEqual(session.get(self.BASE + "/api/data", timeout=5).status_code, 401)


if __name__ == "__main__":
    unittest.main()
