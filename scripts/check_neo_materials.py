# -*- coding: utf-8 -*-
import os, sqlite3, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config

NEO_LINES = [
    ("EVA-28", 37.0), ("EVA-18", 17.0), ("POE-565", 7.0), ("TPE-8201", 3.0),
    ("CACO3", 13.0), ("ZNO", 0.85), ("ZNST", 0.65), ("STEARIC", 0.4),
    ("TAIC", 0.15), ("PEWAX", 0.8), ("DCP99", 0.7), ("PROFOR", 1.28),
]

with sqlite3.connect(config.DB_PATH) as c:
    c.row_factory = sqlite3.Row
    total = 0
    missing_price = []
    for code, kg in NEO_LINES:
        r = c.execute("SELECT id,code,name,cash_price FROM materials WHERE code=?", (code,)).fetchone()
        total += kg
        if not r:
            print("MISSING MATERIAL", code)
        else:
            ok = r["cash_price"] > 0
            print(code, r["id"], r["name"], "price", r["cash_price"], "ok" if ok else "ZERO/MISSING")
            if not ok:
                missing_price.append(code)
    print("TOTAL_KG", round(total, 3))
    profor = c.execute("SELECT * FROM materials WHERE code='PROFOR'").fetchone()
    print("PROFOR_DETAIL", dict(profor) if profor else None)
    print("MISSING_PRICES", missing_price)
