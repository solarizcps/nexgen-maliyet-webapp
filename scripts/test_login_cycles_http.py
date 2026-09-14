# -*- coding: utf-8 -*-
"""HTTP login/logout cycle check against live NexGen (read-only)."""
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.test_helpers import TEST_PASSWORD, TEST_USERNAME

BASE = f"http://{config.HOST}:{config.PORT}"


def login_csrf(session):
    r = session.get(BASE + "/login")
    m = re.search(r"__LOGIN_CSRF\s*=\s*['\"]([^'\"]+)", r.text)
    return m.group(1) if m else ""


def cycle(session, n):
    csrf = login_csrf(session)
    lr = session.post(
        BASE + "/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    body = lr.json()
    csrf = body.get("csrfToken") or csrf
    dr = session.get(BASE + "/api/data")
    d = dr.json()
    formulas = len(d.get("formulas") or [])
    materials = len(d.get("materials") or [])
    active = (d.get("meta") or {}).get("activeFormulaId")
    print(
        f"cycle {n}: login={lr.status_code} data={dr.status_code} "
        f"formulas={formulas} materials={materials} active={active}"
    )
    lo = session.post(
        BASE + "/api/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    unauth = session.get(BASE + "/api/data")
    print(f"  logout={lo.status_code} unauth_data={unauth.status_code}")
    return formulas >= 5 and materials >= 23 and dr.status_code == 200 and unauth.status_code == 401


def main():
    session = requests.Session()
    ok = all(cycle(session, i + 1) for i in range(10))
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
