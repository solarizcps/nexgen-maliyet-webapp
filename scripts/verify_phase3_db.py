# -*- coding: utf-8 -*-
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from app import bootstrap

bootstrap()
with sqlite3.connect(config.DB_PATH) as c:
    print("integrity", c.execute("PRAGMA integrity_check").fetchone()[0])
    print("users", c.execute("SELECT username, display_name FROM users").fetchall())
    print("materials", c.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
    print(
        "plaintext_password",
        c.execute(
            "SELECT COUNT(*) FROM users WHERE password_hash LIKE '%104099%'"
        ).fetchone()[0],
    )
    print(
        "weekly_reviews",
        c.execute("SELECT COUNT(*) FROM weekly_price_reviews").fetchone()[0],
    )
