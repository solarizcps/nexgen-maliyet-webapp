# -*- coding: utf-8 -*-
import re
import sys

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.test_helpers import TEST_PASSWORD, TEST_USERNAME

BASE = f"http://{config.HOST}:{config.PORT}"


def main():
    s = requests.Session()
    r = s.get(BASE + "/login")
    csrf = re.search(r"__LOGIN_CSRF\s*=\s*['\"]([^'\"]+)", r.text).group(1)
    s.post(
        BASE + "/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    idx = s.get(BASE + "/")
    ok = "app.js?v=" in idx.text and "no-store" in idx.headers.get("Cache-Control", "")
    print("CACHE_BUST_OK" if ok else "CACHE_BUST_FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
