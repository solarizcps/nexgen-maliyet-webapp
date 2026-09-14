# -*- coding: utf-8 -*-
"""Independent general expense (overhead) breakdown for forensic/UI."""
from services.calc_engine import overhead


def overhead_breakdown(source):
    rows = []
    allocated = 0.0
    for e in source.get("expenses") or []:
        amount = float(e.get("amount") or 0)
        rate = float(e.get("rate") or 0)
        contrib = amount * rate / 100.0
        allocated += contrib
        rows.append(
            {
                "name": e.get("name") or "",
                "monthlyTry": amount,
                "productionRatePct": rate,
                "allocatedTry": round(contrib, 2),
            }
        )
    prod = float(source.get("productionKg") or 0)
    usd = float(source.get("usdTry") or 0)
    tl_per_kg = allocated / prod if prod > 0 else None
    usd_per_kg = tl_per_kg / usd if tl_per_kg is not None and usd > 0 else None
    engine = overhead(source)
    return {
        "rows": rows,
        "monthlyAllocatedExpenseTry": round(allocated, 2),
        "monthlyProductionKg": prod,
        "usdTryRate": usd,
        "tlPerKg": round(tl_per_kg, 6) if tl_per_kg is not None else None,
        "usdPerKg": round(usd_per_kg, 6) if usd_per_kg is not None else None,
        "engineUsdPerKg": round(engine, 6),
        "formula": "Σ(aylık_TL × üretim_%) ÷ aylık_üretim_kg ÷ USD_TL",
        "note": "Genel gider her satış senaryosuna bir kez eklenir.",
    }
