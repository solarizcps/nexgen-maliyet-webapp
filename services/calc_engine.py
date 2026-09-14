"""Cost calculation engine — mirrors Phase 1 JavaScript rules."""

import math


def parse_num(value):
    if value is None:
        return float("nan")
    s = str(value).strip().replace(" ", "").replace(",", ".")
    if s in ("", "-"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def overhead(source):
    expenses = source.get("expenses") or []
    production = max(parse_num(source.get("productionKg")), 1)
    usd = max(parse_num(source.get("usdTry")), 1)
    total = sum(
        parse_num(x.get("amount")) * parse_num(x.get("rate")) / 100
        for x in expenses
        if parse_num(x.get("amount")) == parse_num(x.get("amount"))
    )
    return total / production / usd


def material_by_id(materials, material_id):
    for m in materials:
        if m.get("id") == material_id:
            return m
    return None


def line_issues(line, materials, row_index):
    issues = []
    kg = parse_num(line.get("kg"))
    mid = line.get("materialId")
    m = material_by_id(materials, mid) if mid else None
    if not mid or not m:
        issues.append(f"Satır {row_index + 1}: malzeme bağlantısı yok")
    else:
        if not str(m.get("code") or "").strip():
            issues.append(f"Satır {row_index + 1} ({m.get('name')}): malzeme kodu boş")
        cash = parse_num(m.get("cash"))
        if not (cash == cash and cash > 0):
            code = m.get("code") or m.get("name")
            issues.append(
                f"Satır {row_index + 1} ({code}): peşin fiyat girilmemiş veya geçersiz"
            )
    if kg == kg and kg < 0:
        issues.append(f"Satır {row_index + 1}: kullanım miktarı negatif olamaz")
    if kg == kg and kg > 0 and (not mid or not m):
        issues.append(f"Satır {row_index + 1}: geçerli kg var fakat malzeme seçilmedi")
    if mid and kg != kg:
        issues.append(f"Satır {row_index + 1}: kullanım miktarı sayı değil")
    return issues


def formula_total_kg(formula):
    total = 0.0
    for line in formula.get("lines") or []:
        kg = parse_num(line.get("kg"))
        if kg == kg and kg > 0:
            total += kg
    return total


def _is_finite(n):
    return n == n and math.isfinite(n)


def _null_if_invalid(n, valid):
    return n if valid and _is_finite(n) else None


def calculate(source, formula):
    monthly_rate = float(formula.get("monthlyRate") or 0)
    months = float(formula.get("months") or 0)
    profit = float(formula.get("profit") or 0)
    materials = source.get("materials") or []
    errors = []
    rows = []

    for i, l in enumerate(formula.get("lines") or []):
        kg = parse_num(l.get("kg"))
        skip = kg == kg and kg == 0
        m = material_by_id(materials, l.get("materialId")) if l.get("materialId") else None
        row_issues = line_issues(l, materials, i)
        if not skip and row_issues:
            errors.extend(row_issues)
        if skip:
            continue
        cash = parse_num(m.get("cash")) if m else float("nan")
        applied = (
            cash * (1 + monthly_rate / 100 * months)
            if cash == cash
            else float("nan")
        )
        invalid = (
            bool(row_issues)
            or not m
            or not (cash == cash and cash > 0)
        )
        rows.append(
            {
                **l,
                "code": (m or {}).get("code") or l.get("code") or "",
                "name": (m or {}).get("name") or "Bulunamadı",
                "category": (m or {}).get("category") or "Katkı",
                "cash": cash,
                "monthlyRate": monthly_rate,
                "applied": applied,
                "total": applied * kg if applied == applied and kg == kg else float("nan"),
                "cashTotal": cash * kg if cash == cash and kg == kg else float("nan"),
                "kg": kg,
                "invalid": invalid,
            }
        )

    valid_rows = [r for r in rows if not r["invalid"] and r["kg"] == r["kg"] and r["kg"] > 0]
    kg_total = sum(r["kg"] for r in valid_rows)
    if not valid_rows and rows:
        errors.append("Hesaplanabilir reçete satırı yok")

    missing_materials = sorted(
        {
            r["code"]
            for r in rows
            if r.get("invalid") and r.get("kg") == r.get("kg") and r["kg"] > 0 and r.get("code")
        }
    )
    missing_price_count = len(missing_materials)

    raw = sum(r["total"] for r in valid_rows if r["total"] == r["total"])
    cash_raw = sum(r["cashTotal"] for r in valid_rows if r["cashTotal"] == r["cashTotal"])
    oh = overhead(source)
    cash_raw_kg = cash_raw / kg_total if kg_total > 0 else float("nan")
    raw_kg = raw / kg_total if kg_total > 0 else float("nan")
    cash_cost = cash_raw_kg + oh if cash_raw_kg == cash_raw_kg else float("nan")
    cash_profit = cash_cost * profit / 100 if cash_cost == cash_cost else float("nan")
    cash_sale = (
        cash_cost + cash_profit
        if cash_cost == cash_cost and cash_profit == cash_profit
        else float("nan")
    )
    cost = raw_kg + oh if raw_kg == raw_kg else float("nan")
    profit_amt = cost * profit / 100 if cost == cost else float("nan")
    sale = cost + profit_amt if cost == cost and profit_amt == profit_amt else float("nan")

    all_non_zero_rows_valid = len([r for r in rows if not r["invalid"]]) == len(rows)
    valid = (
        not errors
        and bool(valid_rows)
        and all_non_zero_rows_valid
        and _is_finite(cash_sale)
    )

    cash_calculation = None
    term_calculation = None
    if valid:
        cash_calculation = {
            "rawKg": cash_raw_kg,
            "overhead": oh,
            "cost": cash_cost,
            "profit": cash_profit,
            "sale": cash_sale,
        }
        if months > 0:
            if monthly_rate > 0:
                term_calculation = {
                    "rawKg": raw_kg,
                    "overhead": oh,
                    "cost": cost,
                    "profit": profit_amt,
                    "sale": sale,
                    "months": months,
                    "monthlyRate": monthly_rate,
                }
            else:
                term_calculation = {
                    "rawKg": cash_raw_kg,
                    "overhead": oh,
                    "cost": cash_cost,
                    "profit": cash_profit,
                    "sale": cash_sale,
                    "months": months,
                    "monthlyRate": monthly_rate,
                    "sameAsCash": True,
                }

    return {
        "rows": rows,
        "allRows": rows,
        "kg": kg_total,
        "recipeKg": formula_total_kg(formula),
        "recipe_total_kg": formula_total_kg(formula),
        "cashRawKg": _null_if_invalid(cash_raw_kg, valid),
        "rawKg": _null_if_invalid(raw_kg, valid),
        "cashCost": _null_if_invalid(cash_cost, valid),
        "cashProfit": _null_if_invalid(cash_profit, valid),
        "cashSale": _null_if_invalid(cash_sale, valid),
        "cost": _null_if_invalid(cost, valid),
        "profit": _null_if_invalid(profit_amt, valid),
        "sale": _null_if_invalid(sale, valid),
        "errors": errors,
        "ok": valid,
        "valid": valid,
        "missing_price_count": missing_price_count,
        "missing_materials": missing_materials,
        "cash_calculation": cash_calculation,
        "term_calculation": term_calculation,
        "overhead": oh if valid else None,
        "formulaId": formula.get("id"),
    }
