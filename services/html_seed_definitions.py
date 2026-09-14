# -*- coding: utf-8 -*-
"""Canonical HTML photo-formula definitions (Phase 1 source, not runtime)."""

# Extra boya materials required by WANDERFULL / DAKIRS (cash=0 until user enters)
SEED_MATERIALS = [
    ("PBLUE154", "Pigment Blue 15/4", "Boya", 0.0),
    ("BROWN600", "Demir Oksit Kahve 600", "Boya", 0.0),
    ("BROWN660", "Demir Oksit Kahve 660", "Boya", 0.0),
    ("PYELLOW13", "Pigment Yellow 13", "Boya", 0.0),
    ("YELLOW313", "Demir Oksit Sarı 313", "Boya", 0.0),
]


def _seed_mat_id(code: str) -> str:
    return "mat-seed-" + code.lower().replace("-", "")


SEED_MATERIAL_IDS = {code: _seed_mat_id(code) for code, *_ in SEED_MATERIALS}

PHOTO_FORMULAS = [
    {
        "id": "wanderfull",
        "company": "WANDERFULL",
        "name": "Buz Gri · L",
        "months": 6,
        "monthlyRate": 0,
        "profit": 20,
        "lines": [
            ("EVA-28", 18),
            ("EVA-18", 35),
            ("POE-565", 6),
            ("TPE-8201", 3),
            ("CACO3", 16),
            ("ZNO", 0.85),
            ("ZNST", 0.65),
            ("STEARIC", 0.4),
            ("TAIC", 0.15),
            ("PEWAX", 0.8),
            ("DCP99", 0.7),
            ("PROFOR", 1.6),
            ("TIO2", 2.7),
            ("PBLUE154", 0.004),
            ("BROWN600", 0.008),
            ("BLK550", 0.047),
            ("YELLOW313", 0.0665),
        ],
    },
    {
        "id": "dakirs",
        "company": "DAKIRS",
        "name": "Taban · L",
        "months": 6,
        "monthlyRate": 0,
        "profit": 20,
        "lines": [
            ("EVA-28", 18),
            ("EVA-18", 35),
            ("POE-565", 6),
            ("TPE-8201", 3),
            ("CACO3", 16),
            ("ZNO", 0.85),
            ("ZNST", 0.65),
            ("STEARIC", 0.4),
            ("TAIC", 0.15),
            ("PEWAX", 0.8),
            ("DCP99", 0.7),
            ("PROFOR", 1.6),
            ("TIO2", 2.4),
            ("BROWN600", 0.09),
            ("BROWN660", 0.037),
            ("BLK550", 0.02),
            ("PR122", 0.006),
            ("PYELLOW13", 0.002),
            ("YELLOW313", 0.155),
        ],
    },
]

SYNTHETIC_SKIP_IDS = {"neo-ekru"}
