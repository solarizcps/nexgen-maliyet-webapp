# -*- coding: utf-8 -*-
"""SQLite online backup API wrapper."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_counts(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c = conn.cursor()
    out = {"integrity": c.execute("PRAGMA integrity_check").fetchone()[0]}
    for t in [
        "users", "materials", "companies", "formulas", "formula_lines",
        "expenses", "weekly_price_reviews", "material_price_history", "audit_log",
    ]:
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    neo = c.execute(
        "SELECT profit_rate, base_expansion_measure FROM formulas WHERE id='neo-taban'"
    ).fetchone()
    out["neo_profit_rate"] = neo[0]
    out["neo_expansion"] = neo[1]
    s = c.execute(
        "SELECT monthly_production_kg, usd_try_rate FROM settings WHERE id=1"
    ).fetchone()
    out["monthly_production_kg"] = s[0]
    out["usd_try_rate"] = s[1]
    conn.close()
    return out


def backup(source, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return sha256_file(dest)


def main():
    if len(sys.argv) < 3:
        print("usage: sqlite_online_backup.py <source.db> <dest.db>", file=sys.stderr)
        return 1
    source = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    digest = backup(source, dest)
    counts = db_counts(dest)
    print(json.dumps({"sha256": digest, "dest": str(dest), **counts}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
