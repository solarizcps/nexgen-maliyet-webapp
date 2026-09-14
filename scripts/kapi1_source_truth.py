# -*- coding: utf-8 -*-
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "nexgen_local.db"


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c = conn.cursor()
    out = {"db": str(DB)}
    out["integrity"] = c.execute("PRAGMA integrity_check").fetchone()[0]
    for t in [
        "users", "materials", "companies", "formulas", "formula_lines",
        "expenses", "weekly_price_reviews", "material_price_history", "audit_log",
    ]:
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    s = c.execute(
        "SELECT monthly_production_kg, usd_try_rate, active_formula_id FROM settings WHERE id=1"
    ).fetchone()
    out["monthly_production_kg"] = s[0]
    out["usd_try_rate"] = s[1]
    out["active_formula_id"] = s[2]
    neo = c.execute(
        "SELECT id, base_expansion_measure, profit_rate FROM formulas WHERE id='neo-taban'"
    ).fetchone()
    out["neo"] = {"id": neo[0], "expansion": neo[1], "profit_rate": neo[2]}
    lines = c.execute(
        "SELECT COUNT(*), ROUND(SUM(quantity_kg), 3) FROM formula_lines WHERE formula_id='neo-taban'"
    ).fetchone()
    out["neo_lines"] = lines[0]
    out["neo_total_kg"] = lines[1]
    eva = c.execute(
        """SELECT fl.quantity_kg FROM formula_lines fl
           JOIN materials m ON fl.material_id=m.id
           WHERE fl.formula_id='neo-taban' AND m.id='eva-18'"""
    ).fetchone()
    out["neo_eva18_kg"] = eva[0] if eva else None
    conn.close()
    print(json.dumps(out, indent=2))
    if out["neo"]["profit_rate"] is None or float(out["neo"]["profit_rate"]) <= 0:
        print("BLOCKED_NEO_PROFIT_NOT_SAVED", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
