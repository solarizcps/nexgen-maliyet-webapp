# -*- coding: utf-8 -*-
"""Neo Taban formula + formula metadata columns (idempotent)."""
from datetime import datetime, timezone

NEO_FORMULA_ID = "neo-taban"
NEO_COMPANY_ID = "co-neo-taban"

NEO_LINES = [
    ("EVA-28", 37.0),
    ("EVA-18", 17.0),
    ("POE-565", 7.0),
    ("TPE-8201", 3.0),
    ("CACO3", 13.0),
    ("ZNO", 0.85),
    ("ZNST", 0.65),
    ("STEARIC", 0.4),
    ("TAIC", 0.15),
    ("PEWAX", 0.8),
    ("DCP99", 0.7),
    ("PROFOR", 1.28),
]

FORMULA_EXTRA_COLUMNS = [
    ("color_name", "TEXT"),
    ("color_code", "TEXT"),
    ("formula_date", "TEXT"),
    ("base_expansion_measure", "REAL"),
]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _ensure_formula_columns(conn):
    existing = {r[1] for r in conn.execute("PRAGMA table_info(formulas)").fetchall()}
    for col, typedef in FORMULA_EXTRA_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE formulas ADD COLUMN {col} {typedef}")


def _material_id(conn, code):
    row = conn.execute("SELECT id FROM materials WHERE code = ?", (code,)).fetchone()
    return row["id"] if row else None


def migrate_neo_overhead(conn):
    _ensure_formula_columns(conn)
    if conn.execute("SELECT id FROM formulas WHERE id = ?", (NEO_FORMULA_ID,)).fetchone():
        return {"neo_imported": False, "reason": "already_exists"}
    for code, _kg in NEO_LINES:
        if not _material_id(conn, code):
            return {"neo_imported": False, "reason": "materials_not_ready", "missing": code}

    now = _now()
    conn.execute(
        """INSERT OR IGNORE INTO companies (id, name, version, created_at, updated_at)
           VALUES (?, ?, 1, ?, ?)""",
        (NEO_COMPANY_ID, "NEO TABAN", now, now),
    )
    # Vade/kâr kâğıtta yok — 0/0/0; kullanıcı Maliyet Hesabı'ndan girebilir.
    conn.execute(
        """INSERT INTO formulas
           (id, company_id, name, months, monthly_rate, profit_rate, version,
            color_name, color_code, formula_date, base_expansion_measure,
            created_at, updated_at)
           VALUES (?, ?, ?, 0, 0, 0, 1, ?, ?, ?, ?, ?, ?)""",
        (
            NEO_FORMULA_ID,
            NEO_COMPANY_ID,
            "NORMAL",
            "Ekru",
            "0235",
            "2026-09-14",
            1.45,
            now,
            now,
        ),
    )
    for i, (code, kg) in enumerate(NEO_LINES):
        mid = _material_id(conn, code)
        conn.execute(
            """INSERT INTO formula_lines
               (formula_id, material_id, quantity_kg, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (NEO_FORMULA_ID, mid, kg, i, now, now),
        )
    return {"neo_imported": True, "formula_id": NEO_FORMULA_ID, "line_count": len(NEO_LINES)}
