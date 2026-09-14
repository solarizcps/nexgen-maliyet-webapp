import json
from datetime import datetime, timezone

import config
from db.connection import db_transaction


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_quantity_kg(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace(",", ".")
    if s in ("", "-"):
        return 0.0
    return float(s)


class ApiSaveError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def _audit(conn, entity_type, entity_id, action, before, after, changed_by=None):
    conn.execute(
        """INSERT INTO audit_log
           (entity_type, entity_id, action, before_json, after_json, changed_at, changed_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_type,
            entity_id,
            action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            _now(),
            changed_by or config.CHANGED_BY,
        ),
    )


def get_meta_version(conn, key):
    row = conn.execute(
        "SELECT version FROM meta_versions WHERE key = ?", (key,)
    ).fetchone()
    return row["version"] if row else 1


def bump_meta_version(conn, key):
    now = _now()
    ver = get_meta_version(conn, key) + 1
    conn.execute(
        """INSERT INTO meta_versions (key, version, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at""",
        (key, ver, now),
    )
    return ver


def fetch_all_data():
    with db_transaction() as conn:
        materials = [
            {
                "id": r["id"],
                "code": r["code"],
                "name": r["name"],
                "category": r["category"],
                "cash": r["cash_price"],
                "version": r["version"],
            }
            for r in conn.execute(
                "SELECT * FROM materials ORDER BY code"
            ).fetchall()
        ]
        expenses = [
            {
                "id": r["id"],
                "name": r["name"],
                "amount": r["monthly_amount_try"],
                "rate": r["production_rate"],
            }
            for r in conn.execute(
                "SELECT * FROM expenses ORDER BY sort_order, id"
            ).fetchall()
        ]
        settings = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        formulas = []
        for f in conn.execute(
            """SELECT f.*, c.name AS company_name FROM formulas f
               JOIN companies c ON c.id = f.company_id ORDER BY f.id"""
        ).fetchall():
            lines = [
                {
                    "materialId": l["material_id"],
                    "kg": l["quantity_kg"],
                    "code": conn.execute(
                        "SELECT code FROM materials WHERE id = ?", (l["material_id"],)
                    ).fetchone()["code"],
                }
                for l in conn.execute(
                    """SELECT * FROM formula_lines WHERE formula_id = ?
                       ORDER BY sort_order, id""",
                    (f["id"],),
                ).fetchall()
            ]
            formulas.append(
                {
                    "id": f["id"],
                    "company": f["company_name"],
                    "companyId": f["company_id"],
                    "name": f["name"],
                    "months": f["months"],
                    "monthlyRate": f["monthly_rate"],
                    "profit": f["profit_rate"],
                    "version": f["version"],
                    "colorName": f["color_name"] if "color_name" in f.keys() else None,
                    "colorCode": f["color_code"] if "color_code" in f.keys() else None,
                    "formulaDate": f["formula_date"] if "formula_date" in f.keys() else None,
                    "baseExpansionMeasure": (
                        f["base_expansion_measure"]
                        if "base_expansion_measure" in f.keys()
                        else None
                    ),
                    "lines": lines,
                }
            )
        saved_at = {
            r["page"]: r["saved_at"]
            for r in conn.execute("SELECT page, saved_at FROM page_saves").fetchall()
        }
        versions = {
            r["key"]: r["version"]
            for r in conn.execute("SELECT key, version FROM meta_versions").fetchall()
        }
        return {
            "productionKg": settings["monthly_production_kg"],
            "usdTry": settings["usd_try_rate"],
            "materials": materials,
            "expenses": expenses,
            "formulas": formulas,
            "savedAt": saved_at,
            "versions": versions,
            "settingsVersion": settings["version"],
            "meta": {
                "activeFormulaId": settings["active_formula_id"],
                "source": "sqlite",
                "dbPath": config.DB_PATH,
            },
        }


def save_materials(payload, user_id=None, changed_by=None):
    materials = payload.get("materials") or []
    expected = payload.get("version")
    actor = changed_by or config.CHANGED_BY
    with db_transaction() as conn:
        current = get_meta_version(conn, "materials")
        if expected is not None and int(expected) != current:
            return None, 409, f"Versiyon uyuşmazlığı: beklenen {expected}, mevcut {current}"
        now = _now()
        existing_ids = {
            r["id"]
            for r in conn.execute("SELECT id FROM materials").fetchall()
        }
        incoming_ids = {m["id"] for m in materials if m.get("id")}
        for eid in existing_ids - incoming_ids:
            refs = conn.execute(
                "SELECT COUNT(*) AS c FROM formula_lines WHERE material_id = ?", (eid,)
            ).fetchone()["c"]
            if refs:
                return None, 400, "Referanslı malzeme silinemez"
        seen_codes = set()
        for m in materials:
            code = str(m.get("code") or "").strip()
            if not code or code in seen_codes:
                return None, 400, f"Geçersiz veya yinelenen malzeme kodu: {code!r}"
            seen_codes.add(code)
        price_changes = 0
        for m in materials:
            code = str(m.get("code") or "").strip()
            new_price = float(m.get("cash") or 0)
            existing = conn.execute(
                "SELECT created_at, cash_price FROM materials WHERE id = ?", (m["id"],)
            ).fetchone()
            created = existing["created_at"] if existing else now
            old_price = float(existing["cash_price"]) if existing else new_price
            if existing and user_id and abs(old_price - new_price) > 1e-9:
                conn.execute(
                    """INSERT INTO material_price_history
                       (material_id, old_price, new_price, changed_by_user_id,
                        changed_at, weekly_review_id, source, created_at)
                       VALUES (?, ?, ?, ?, ?, NULL, 'materials_save', ?)""",
                    (m["id"], old_price, new_price, user_id, now, now),
                )
                _audit(
                    conn,
                    "material",
                    m["id"],
                    "price_change",
                    {"code": code, "cash_price": old_price},
                    {"code": code, "cash_price": new_price},
                    actor,
                )
                price_changes += 1
            conn.execute(
                """INSERT INTO materials
                   (id, code, name, category, cash_price, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     code=excluded.code, name=excluded.name, category=excluded.category,
                     cash_price=excluded.cash_price, version=excluded.version, updated_at=excluded.updated_at""",
                (
                    m["id"],
                    code,
                    m.get("name") or code,
                    m.get("category") or "Katkı",
                    new_price,
                    current + 1,
                    created,
                    now,
                ),
            )
        for eid in existing_ids - incoming_ids:
            conn.execute("DELETE FROM materials WHERE id = ?", (eid,))
        ver = bump_meta_version(conn, "materials")
        conn.execute(
            """INSERT INTO page_saves (page, saved_at, version) VALUES ('materials', ?, ?)
               ON CONFLICT(page) DO UPDATE SET saved_at=excluded.saved_at, version=excluded.version""",
            (now, ver),
        )
        after = {"materials_count": len(materials), "version": ver, "priceChanges": price_changes}
        _audit(conn, "materials", "batch", "update", None, after, actor)
        return {"savedAt": now, "version": ver, "priceChanges": price_changes}, 200, None


def save_expenses(payload):
    expected = payload.get("version")
    with db_transaction() as conn:
        current = get_meta_version(conn, "expenses")
        if expected is not None and int(expected) != current:
            return None, 409, f"Versiyon uyuşmazlığı: beklenen {expected}, mevcut {current}"
        now = _now()
        conn.execute(
            """UPDATE settings SET monthly_production_kg=?, usd_try_rate=?,
               version=version+1, updated_at=? WHERE id=1""",
            (
                float(payload.get("productionKg") or 0),
                float(payload.get("usdTry") or 0),
                now,
            ),
        )
        conn.execute("DELETE FROM expenses")
        for i, e in enumerate(payload.get("expenses") or []):
            conn.execute(
                """INSERT INTO expenses
                   (name, monthly_amount_try, production_rate, sort_order, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.get("name") or f"Gider {i+1}",
                    float(e.get("amount") or 0),
                    float(e.get("rate") or 100),
                    i,
                    current + 1,
                    now,
                    now,
                ),
            )
        ver = bump_meta_version(conn, "expenses")
        conn.execute(
            """INSERT INTO page_saves (page, saved_at, version) VALUES ('expenses', ?, ?)
               ON CONFLICT(page) DO UPDATE SET saved_at=excluded.saved_at, version=excluded.version""",
            (now, ver),
        )
        _audit(conn, "expenses", "batch", "update", None, {"version": ver})
        return {"savedAt": now, "version": ver}, 200, None


def save_formulas(payload):
    formulas = payload.get("formulas") or []
    expected = payload.get("version")
    try:
        with db_transaction() as conn:
            current = get_meta_version(conn, "formulas")
            if expected is not None and int(expected) != current:
                raise ApiSaveError(
                    409,
                    f"Versiyon uyuşmazlığı: beklenen {expected}, mevcut {current}",
                )
            now = _now()
            conn.execute("DELETE FROM formula_lines")
            conn.execute("DELETE FROM formulas")
            for f in formulas:
                cid = f.get("companyId") or f"co-{f['id']}"
                conn.execute(
                    """INSERT OR REPLACE INTO companies (id, name, version, created_at, updated_at)
                       VALUES (?, ?, ?, COALESCE((SELECT created_at FROM companies WHERE id=?), ?), ?)""",
                    (cid, f.get("company") or "FİRMA", current + 1, cid, now, now),
                )
                conn.execute(
                    """INSERT INTO formulas
                       (id, company_id, name, months, monthly_rate, profit_rate, version,
                        color_name, color_code, formula_date, base_expansion_measure,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f["id"],
                        cid,
                        f.get("name") or "Formül",
                        float(f.get("months") or 0),
                        float(f.get("monthlyRate") or 0),
                        float(f.get("profit") or 0),
                        current + 1,
                        f.get("colorName") or None,
                        f.get("colorCode") or None,
                        f.get("formulaDate") or None,
                        float(f["baseExpansionMeasure"])
                        if f.get("baseExpansionMeasure") not in (None, "")
                        else None,
                        now,
                        now,
                    ),
                )
                for i, line in enumerate(f.get("lines") or []):
                    mid = line.get("materialId")
                    if not mid:
                        raise ApiSaveError(400, "Formül satırında materialId zorunlu")
                    mat = conn.execute(
                        "SELECT id FROM materials WHERE id = ?", (mid,)
                    ).fetchone()
                    if not mat:
                        raise ApiSaveError(400, f"Geçersiz material_id: {mid}")
                    conn.execute(
                        """INSERT INTO formula_lines
                           (formula_id, material_id, quantity_kg, sort_order, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (f["id"], mid, _parse_quantity_kg(line.get("kg")), i, now, now),
                    )
            ver = bump_meta_version(conn, "formulas")
            conn.execute(
                """INSERT INTO page_saves (page, saved_at, version) VALUES ('formulas', ?, ?)
                   ON CONFLICT(page) DO UPDATE SET saved_at=excluded.saved_at, version=excluded.version""",
                (now, ver),
            )
            _audit(
                conn,
                "formulas",
                "batch",
                "update",
                None,
                {"count": len(formulas), "version": ver},
            )
            return {"savedAt": now, "version": ver}, 200, None
    except ApiSaveError as exc:
        return None, exc.code, exc.message


def save_calc(payload):
    formula_id = payload.get("formulaId")
    expected = payload.get("version")
    with db_transaction() as conn:
        current = get_meta_version(conn, "calc")
        if expected is not None and int(expected) != current:
            return None, 409, f"Versiyon uyuşmazlığı: beklenen {expected}, mevcut {current}"
        f = conn.execute(
            "SELECT id, version FROM formulas WHERE id = ?", (formula_id,)
        ).fetchone()
        if not f:
            return None, 404, "Formül bulunamadı"
        now = _now()
        conn.execute(
            """UPDATE formulas SET months=?, monthly_rate=?, profit_rate=?,
               version=version+1, updated_at=? WHERE id=?""",
            (
                float(payload.get("months") or 0),
                float(payload.get("monthlyRate") or 0),
                float(payload.get("profit") or 0),
                now,
                formula_id,
            ),
        )
        conn.execute(
            "UPDATE settings SET active_formula_id=?, updated_at=? WHERE id=1",
            (formula_id, now),
        )
        ver = bump_meta_version(conn, "calc")
        conn.execute(
            """INSERT INTO page_saves (page, saved_at, version) VALUES ('calc', ?, ?)
               ON CONFLICT(page) DO UPDATE SET saved_at=excluded.saved_at, version=excluded.version""",
            (now, ver),
        )
        _audit(conn, "formula", formula_id, "update_calc", None, payload)
        return {"savedAt": now, "version": ver}, 200, None


def delete_material(material_id, confirmed=False):
    with db_transaction() as conn:
        refs = conn.execute(
            "SELECT COUNT(*) AS c FROM formula_lines WHERE material_id = ?", (material_id,)
        ).fetchone()["c"]
        if refs:
            return None, 400, "Malzeme formül satırlarında kullanılıyor"
        if not confirmed:
            return None, 428, "Silme işlemi için onay gerekli"
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        _audit(conn, "material", material_id, "delete", None, None)
        return {"deleted": material_id}, 200, None


def integrity_check():
    with db_transaction() as conn:
        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        orphans = conn.execute(
            """SELECT fl.id FROM formula_lines fl
               LEFT JOIN materials m ON m.id = fl.material_id WHERE m.id IS NULL"""
        ).fetchall()
        dup_codes = conn.execute(
            """SELECT code, COUNT(*) AS c FROM materials GROUP BY code HAVING c > 1"""
        ).fetchall()
        return {
            "foreign_keys_enabled": bool(fk_on),
            "orphan_formula_lines": len(orphans),
            "duplicate_material_codes": len(dup_codes),
        }
