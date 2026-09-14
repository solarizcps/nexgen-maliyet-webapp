import os
import sqlite3
from contextlib import contextmanager

import config


def _ensure_data_dir():
    os.makedirs(config.DATA_DIR, exist_ok=True)


def get_connection():
    _ensure_data_dir()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(force=False):
    _ensure_data_dir()
    if force and os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    with open(config.SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    with db_transaction() as conn:
        conn.executescript(schema)
        cur = conn.execute("SELECT COUNT(*) AS c FROM settings")
        if cur.fetchone()["c"] == 0:
            now = _now()
            conn.execute(
                """INSERT INTO settings
                   (id, monthly_production_kg, usd_try_rate, active_formula_id, version, updated_at)
                   VALUES (1, 420000, 42.45, NULL, 1, ?)""",
                (now,),
            )
            for key in ("materials", "expenses", "formulas", "calc"):
                conn.execute(
                    "INSERT OR IGNORE INTO meta_versions (key, version, updated_at) VALUES (?, 1, ?)",
                    (key, now),
                )
        from db.migrate_phase3 import migrate_phase3

        migrate_phase3(conn)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def foreign_keys_enabled():
    with get_connection() as conn:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        return bool(row[0])
