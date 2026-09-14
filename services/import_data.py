# -*- coding: utf-8 -*-
"""Idempotent migration: localStorage + HTML photo formulas -> SQLite."""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from db.connection import db_transaction, init_db
from services.html_seed_definitions import (
    PHOTO_FORMULAS,
    SEED_MATERIALS,
    SEED_MATERIAL_IDS,
    SYNTHETIC_SKIP_IDS,
    _seed_mat_id,
)

REAL_USER_FORMULA_IDS = {"aym", "darkir"}
PHOTO_FORMULA_IDS = {"wanderfull", "dakirs"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _company_id(formula_id):
    return f"co-{formula_id}"


def load_source(path=None):
    path = path or config.IMPORT_SOURCE
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def backup_db():
    if not os.path.exists(config.DB_PATH):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(config.DATA_DIR, f"nexgen_local_backup_{ts}.db")
    shutil.copy2(config.DB_PATH, dest)
    return dest


def _material_id_for_code(conn, code):
    row = conn.execute("SELECT id FROM materials WHERE code = ?", (code,)).fetchone()
    return row["id"] if row else None


def _ensure_seed_materials(conn, now, report):
    for code, name, category, cash in SEED_MATERIALS:
        existing = conn.execute(
            "SELECT id FROM materials WHERE code = ?", (code,)
        ).fetchone()
        if existing:
            report["duplicates"].append({"type": "material", "code": code})
            continue
        mid = _seed_mat_id(code)
        conn.execute(
            """INSERT INTO materials
               (id, code, name, category, cash_price, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (mid, code, name, category, cash, now, now),
        )
        report["seed_materials_imported"] = report.get("seed_materials_imported", 0) + 1


def _import_formula(conn, fdef, now, report, source_label):
    fid = fdef["id"]
    if fid in SYNTHETIC_SKIP_IDS:
        report["skipped_formulas"].append({"id": fid, "reason": "synthetic"})
        return

    existing = conn.execute("SELECT id FROM formulas WHERE id = ?", (fid,)).fetchone()
    if existing:
        report["duplicates"].append({"type": "formula", "id": fid})
        return

    cid = _company_id(fid)
    company = fdef["company"]
    conn.execute(
        """INSERT OR IGNORE INTO companies (id, name, version, created_at, updated_at)
           VALUES (?, ?, 1, ?, ?)""",
        (cid, company, now, now),
    )
    conn.execute(
        """INSERT INTO formulas
           (id, company_id, name, months, monthly_rate, profit_rate, version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            fid,
            cid,
            fdef["name"],
            float(fdef.get("months") or 0),
            float(fdef.get("monthlyRate") or 0),
            float(fdef.get("profit") or 0),
            now,
            now,
        ),
    )
    for i, (code, kg) in enumerate(fdef["lines"]):
        mid = _material_id_for_code(conn, code)
        if not mid:
            report["data_loss"].append(
                {"formula": fid, "line": i, "code": code, "reason": "material not found"}
            )
            continue
        conn.execute(
            """INSERT INTO formula_lines
               (formula_id, material_id, quantity_kg, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (fid, mid, float(kg), i, now, now),
        )
    report["formulas_imported"] = report.get("formulas_imported", 0) + 1
    report.setdefault("imported_formula_ids", []).append(fid)


def _ensure_page_saves(conn, now):
    for page in ("materials", "expenses", "formulas", "calc"):
        conn.execute(
            """INSERT INTO page_saves (page, saved_at, version)
               VALUES (?, ?, 1)
               ON CONFLICT(page) DO NOTHING""",
            (page, now),
        )


def _wanderfull_report(conn, report):
    rows = conn.execute(
        """SELECT fl.sort_order, m.code, m.name, m.id AS material_id,
                  fl.quantity_kg, m.cash_price
           FROM formula_lines fl
           JOIN materials m ON m.id = fl.material_id
           WHERE fl.formula_id = 'wanderfull'
           ORDER BY fl.sort_order"""
    ).fetchall()
    lines = []
    total = 0.0
    for r in rows:
        kg = float(r["quantity_kg"])
        total += kg
        lines.append(
            {
                "sort": r["sort_order"],
                "code": r["code"],
                "name": r["name"],
                "material_id": r["material_id"],
                "kg_exact": kg,
                "cash_price": r["cash_price"],
            }
        )
    report["wanderfull_lines"] = lines
    report["wanderfull_row_count"] = len(lines)
    report["wanderfull_total_kg_exact"] = total


def import_localstorage(source_path=None, force_recreate=False, report_path=None):
    source = load_source(source_path)
    report = {
        "source_path": source_path or config.IMPORT_SOURCE,
        "source_materials": len(source.get("materials") or []),
        "source_formulas": len(source.get("formulas") or []),
        "source_expenses": len(source.get("expenses") or []),
        "skipped_formulas": [],
        "skipped_materials": [],
        "duplicates": [],
        "conflicts": [],
        "data_loss": [],
        "synthetic_neo_imported": False,
        "photo_formulas_source": "html_seed_definitions.py",
        "monthly_field_note": (
            "localStorage materials.monthly is NOT used in cost calculation "
            "(formula.monthlyRate is used). Not migrated to DB."
        ),
    }

    if force_recreate:
        backup_db()
        init_db(force=True)
    else:
        init_db(force=False)

    now = _now()
    with db_transaction() as conn:
        db_count_before = conn.execute("SELECT COUNT(*) AS c FROM materials").fetchone()["c"]

        for m in source.get("materials") or []:
            mid = m.get("id")
            code = str(m.get("code") or "").strip()
            if not mid or not code:
                report["skipped_materials"].append(m)
                continue
            existing = conn.execute(
                "SELECT id FROM materials WHERE id = ?", (mid,)
            ).fetchone()
            if existing:
                report["duplicates"].append({"type": "material", "id": mid})
                continue
            try:
                conn.execute(
                    """INSERT INTO materials
                       (id, code, name, category, cash_price, version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                    (
                        mid,
                        code,
                        m.get("name") or code,
                        m.get("category") or "Katkı",
                        float(m.get("cash") or 0),
                        now,
                        now,
                    ),
                )
            except Exception as exc:
                report["conflicts"].append({"type": "material", "id": mid, "error": str(exc)})

        _ensure_seed_materials(conn, now, report)

        settings_exists = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if settings_exists:
            conn.execute(
                """UPDATE settings SET monthly_production_kg=?, usd_try_rate=?, updated_at=?
                   WHERE id=1""",
                (
                    float(source.get("productionKg") or 420000),
                    float(source.get("usdTry") or 42.45),
                    now,
                ),
            )
        exp_before = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
        if exp_before == 0:
            for i, e in enumerate(source.get("expenses") or []):
                conn.execute(
                    """INSERT INTO expenses
                       (name, monthly_amount_try, production_rate, sort_order, version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (
                        e.get("name") or f"Gider {i+1}",
                        float(e.get("amount") or 0),
                        float(e.get("rate") or 100),
                        i,
                        now,
                        now,
                    ),
                )

        for f in source.get("formulas") or []:
            fid = f.get("id")
            if fid not in REAL_USER_FORMULA_IDS:
                continue
            if conn.execute("SELECT id FROM formulas WHERE id=?", (fid,)).fetchone():
                report["duplicates"].append({"type": "formula", "id": fid})
                continue
            cid = _company_id(fid)
            company_name = f.get("company") or fid.upper()
            conn.execute(
                """INSERT OR IGNORE INTO companies (id, name, version, created_at, updated_at)
                   VALUES (?, ?, 1, ?, ?)""",
                (cid, company_name, now, now),
            )
            conn.execute(
                """INSERT INTO formulas
                   (id, company_id, name, months, monthly_rate, profit_rate, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    fid,
                    cid,
                    f.get("name") or "Formül",
                    float(f.get("months") or 0),
                    float(f.get("monthlyRate") or 0),
                    float(f.get("profit") or 0),
                    now,
                    now,
                ),
            )
            for i, line in enumerate(f.get("lines") or []):
                mid = line.get("materialId")
                if not mid:
                    code = line.get("code")
                    mid = _material_id_for_code(conn, code) if code else None
                if not mid:
                    report["data_loss"].append({"formula": fid, "line": i})
                    continue
                conn.execute(
                    """INSERT INTO formula_lines
                       (formula_id, material_id, quantity_kg, sort_order, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fid, mid, float(line.get("kg") or 0), i, now, now),
                )

        for pf in PHOTO_FORMULAS:
            _import_formula(conn, pf, now, report, "html")

        _ensure_page_saves(conn, now)

        conn.execute(
            """UPDATE settings SET active_formula_id =
               COALESCE(NULLIF(active_formula_id,''), 'wanderfull') WHERE id = 1"""
        )

        report["materials_db_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM materials"
        ).fetchone()["c"]
        report["companies_db_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM companies"
        ).fetchone()["c"]
        report["formulas_db_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM formulas"
        ).fetchone()["c"]
        report["formula_lines_db_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM formula_lines"
        ).fetchone()["c"]
        report["expenses_db_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses"
        ).fetchone()["c"]
        report["materials_imported_new"] = report["materials_db_count"] - db_count_before

        aym_kg = conn.execute(
            """SELECT SUM(fl.quantity_kg) FROM formula_lines fl
               WHERE fl.formula_id = 'aym'"""
        ).fetchone()[0]
        report["aym_total_kg"] = aym_kg
        eva = conn.execute(
            """SELECT m.cash_price, fl.quantity_kg FROM formula_lines fl
               JOIN materials m ON m.id = fl.material_id
               WHERE fl.formula_id = 'aym' AND m.code = 'EVA-18'"""
        ).fetchone()
        if eva:
            report["aym_eva18_price"] = eva["cash_price"]
            report["aym_eva18_kg"] = eva["quantity_kg"]
            report["aym_eva18_line_cost"] = eva["cash_price"] * eva["quantity_kg"]

        _wanderfull_report(conn, report)

        conn.execute(
            """INSERT INTO audit_log (entity_type, entity_id, action, before_json, after_json, changed_at, changed_by)
               VALUES ('import', 'v2', 'migrate', NULL, ?, ?, ?)""",
            (json.dumps({"source": report["source_path"]}, ensure_ascii=False), now, config.CHANGED_BY),
        )

    from db.migrate_neo_overhead import migrate_neo_overhead

    with db_transaction() as conn:
        report["neo_migration"] = migrate_neo_overhead(conn)

    if report_path:
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


if __name__ == "__main__":
    rp = os.path.join(config.DATA_DIR, "import_report_v2.json")
    r = import_localstorage(force_recreate=False, report_path=rp)
    print(json.dumps(r, ensure_ascii=False, indent=2))
