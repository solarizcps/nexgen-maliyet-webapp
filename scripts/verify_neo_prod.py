# -*- coding: utf-8 -*-
import json, os, sqlite3, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config
from services.calc_engine import calculate, formula_total_kg
from services.repository import fetch_all_data
from services.overhead_detail import overhead_breakdown

with sqlite3.connect(config.DB_PATH) as c:
    c.row_factory = sqlite3.Row
    rep = {
        "integrity": c.execute("PRAGMA integrity_check").fetchone()[0],
        "formulas": c.execute("SELECT COUNT(*) FROM formulas").fetchone()[0],
        "formula_lines": c.execute("SELECT COUNT(*) FROM formula_lines").fetchone()[0],
    }

data = fetch_all_data()
f = next(x for x in data["formulas"] if x["id"] == "neo-taban")
calc = calculate(data, f)
bd = overhead_breakdown(data)
rep.update({
    "neo": {
        "company": f["company"],
        "name": f["name"],
        "colorName": f["colorName"],
        "colorCode": f["colorCode"],
        "formulaDate": f["formulaDate"],
        "baseExpansionMeasure": f["baseExpansionMeasure"],
        "lines": len(f["lines"]),
        "recipeKg": formula_total_kg(f),
        "valid": calc["valid"],
        "cashRawKg": calc["cashRawKg"],
        "overhead": calc["overhead"],
        "cashCost": calc["cashCost"],
        "profit": f["profit"],
        "cashSale": calc["cashSale"],
    },
    "overhead_usd_per_kg": bd["engineUsdPerKg"],
})
print(json.dumps(rep, indent=2, ensure_ascii=False))
