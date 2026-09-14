# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config
from services.calc_engine import overhead
from services.repository import fetch_all_data

with sqlite3.connect(config.DB_PATH) as c:
    c.row_factory = sqlite3.Row
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    counts = {
        t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in (
            "materials", "companies", "formulas", "formula_lines", "expenses",
            "settings", "users", "weekly_price_reviews", "audit_log",
        )
    }

data = fetch_all_data()
rows = []
allocated = 0.0
for e in data["expenses"]:
    contrib = e["amount"] * e["rate"] / 100
    allocated += contrib
    rows.append({
        "name": e["name"],
        "monthly_try": e["amount"],
        "production_rate_pct": e["rate"],
        "allocated_try": contrib,
    })

prod = data["productionKg"]
usd = data["usdTry"]
tl_per_kg = allocated / prod if prod else 0
usd_per_kg = tl_per_kg / usd if usd else 0
engine = overhead(data)

report = {
    "integrity": integrity,
    "counts": counts,
    "settings": {
        "monthly_production_kg": prod,
        "usd_try_rate": usd,
        "saved_at_expenses": data["savedAt"].get("expenses"),
    },
    "expense_rows": rows,
    "monthly_allocated_expense_try": round(allocated, 2),
    "independent_tl_per_kg": round(tl_per_kg, 6),
    "independent_usd_per_kg": round(usd_per_kg, 6),
    "engine_overhead_usd_per_kg": round(engine, 6),
    "screen_expected": 0.0837,
    "match": abs(engine - 0.0837) < 0.0001,
}

print(json.dumps(report, indent=2, ensure_ascii=False))
