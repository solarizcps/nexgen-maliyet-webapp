# -*- coding: utf-8 -*-
"""Shared auth helpers for Phase 3 tests."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from app import create_app
from db.connection import init_db
from services.import_data import import_localstorage

# Test-only credential — not used in production UI or committed secrets file.
TEST_USERNAME = "altan"
TEST_PASSWORD = "104099"


def _login_body_json():
    import json

    return json.dumps({"username": TEST_USERNAME, "password": TEST_PASSWORD})


def browser_login_eval_script():
    body = _login_body_json()
    return (
        "(async()=>{const csrf=window.__LOGIN_CSRF;"
        "await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json',"
        "'X-CSRF-Token':csrf},body:"
        + body
        + "});location.href='/'})()"
    )


def browser_login_eval_script_check_ok():
    body = _login_body_json()
    return (
        "(async()=>{const csrf=window.__LOGIN_CSRF;"
        "const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json',"
        "'X-CSRF-Token':csrf},body:"
        + body
        + "});if((await r.json()).ok) location.href='/';})()"
    )


def browser_login_eval_script_csrf_api():
    body = _login_body_json()
    return (
        "(async()=>{const csrfResp=await fetch('/api/auth/csrf');"
        "const csrfBody=await csrfResp.json();"
        "await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json',"
        "'X-CSRF-Token':csrfBody.csrfToken},body:"
        + body
        + "});location.href='/'})()"
    )


def setup_test_app(prefix="nexgen-test-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    db = os.path.join(tmp, "test.db")
    config.DB_PATH = db
    config.DATA_DIR = tmp
    init_db(force=True)
    import_localstorage(force_recreate=False)
    app = create_app({"TESTING": True})
    return app, tmp


def get_csrf(client):
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200, r.data
    return r.json["csrfToken"]


def login_client(client, username=TEST_USERNAME, password=TEST_PASSWORD):
    csrf = get_csrf(client)
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    if r.status_code == 200:
        body = r.get_json(silent=True) or {}
        csrf = body.get("csrfToken") or csrf
    return r, csrf


def auth_client(app=None):
    if app is None:
        app, _ = setup_test_app()
    client = app.test_client()
    r, csrf = login_client(client)
    if r.status_code != 200:
        raise RuntimeError(f"Login failed: {r.status_code} {r.data}")
    return client, csrf
