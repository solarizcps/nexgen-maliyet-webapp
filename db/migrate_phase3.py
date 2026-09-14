# -*- coding: utf-8 -*-
"""Phase 3 schema migration: users, weekly reviews, price history."""
from datetime import datetime, timezone

# Precomputed scrypt hash — plaintext password is never stored in source or DB.
ALTAN_PASSWORD_HASH = (
    "scrypt:32768:8:1$hG3AC7pbUANRP0wk$"
    "1fdf03292b14790fc14008fd4df4a0777c574c93d5fd6dda46f30aef658c9a71"
    "bec72bbaabd5ed4c21087f355e24dffb11b93247b8864caa134b0af4630d2c6b"
)

PHASE3_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(username)
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    username_normalized TEXT,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS weekly_price_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start_date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('updated', 'unchanged')),
    reviewed_by_user_id INTEGER NOT NULL REFERENCES users(id),
    reviewed_at TEXT NOT NULL,
    material_changes_count INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS material_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id TEXT NOT NULL REFERENCES materials(id),
    old_price REAL NOT NULL,
    new_price REAL NOT NULL,
    changed_by_user_id INTEGER NOT NULL REFERENCES users(id),
    changed_at TEXT NOT NULL,
    weekly_review_id INTEGER REFERENCES weekly_price_reviews(id),
    source TEXT NOT NULL DEFAULT 'materials_save',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip_address, attempted_at);
CREATE INDEX IF NOT EXISTS idx_price_history_material ON material_price_history(material_id);
CREATE INDEX IF NOT EXISTS idx_price_history_week ON material_price_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_weekly_reviews_start ON weekly_price_reviews(week_start_date);
"""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def migrate_phase3(conn):
    conn.executescript(PHASE3_DDL)
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count == 0:
        now = _now()
        conn.execute(
            """INSERT INTO users
               (username, display_name, password_hash, is_active, must_change_password,
                failed_login_count, created_at, updated_at, version)
               VALUES (?, ?, ?, 1, 0, 0, ?, ?, 1)""",
            ("altan", "Altan", ALTAN_PASSWORD_HASH, now, now),
        )
