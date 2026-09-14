# -*- coding: utf-8 -*-
"""Phase 3 weekly price review tests — injectable clock, isolated DB."""
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db.connection import db_transaction
from services.clock import FixedClock, IST
from services.repository import fetch_all_data, save_materials
from services.weekly_review_service import (
    complete_updated,
    confirm_unchanged,
    current_week_start,
    get_status,
    is_review_due,
)
from tests.test_helpers import auth_client, setup_test_app


def monday_utc(year, month, day, hour=8):
    dt = datetime(year, month, day, hour, 0, 0, tzinfo=IST)
    return dt.astimezone(timezone.utc)


class WeeklyReviewTests(unittest.TestCase):
    def _app_client(self, utc_dt):
        app, _ = setup_test_app("nexgen-weekly-")
        app.config["CLOCK"] = FixedClock(utc_dt)
        client, csrf = auth_client(app)
        return app, client, csrf

    def test_monday_due_when_no_record(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            self.assertTrue(is_review_due())
            st = get_status()
            self.assertTrue(st["due"])

    def test_tuesday_still_due(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 15))
        with app.app_context():
            self.assertTrue(is_review_due())

    def test_sunday_still_due(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 20))
        with app.app_context():
            self.assertTrue(is_review_due())

    def test_unchanged_clears_due(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            result, code, err = confirm_unchanged(1)
            self.assertIsNone(err, err)
            self.assertEqual(code, 200)
            self.assertFalse(is_review_due())

    def test_new_monday_due_again(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            confirm_unchanged(1)
        app.config["CLOCK"] = FixedClock(monday_utc(2026, 9, 21))
        with app.app_context():
            self.assertTrue(is_review_due())

    def test_no_duplicate_same_week(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            confirm_unchanged(1)
            _, code, err = confirm_unchanged(1)
            self.assertEqual(code, 409)

    def test_week_start_is_monday_istanbul(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            self.assertEqual(current_week_start(), "2026-09-14")
            st = get_status()
            self.assertEqual(st["weekStart"], "2026-09-14")
            self.assertEqual(st["timezone"], "Europe/Istanbul")

    def test_open_materials_page_does_not_create_review(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            with db_transaction() as conn:
                c = conn.execute("SELECT COUNT(*) AS n FROM weekly_price_reviews").fetchone()["n"]
            self.assertEqual(c, 0)

    def test_price_change_save_and_complete_updated(self):
        app, client, csrf = self._app_client(monday_utc(2026, 9, 14))
        data = fetch_all_data()
        mats = data["materials"]
        eva = next(m for m in mats if m["code"] == "EVA-18")
        old = eva["cash"]
        eva["cash"] = old + 0.01
        with app.app_context():
            result, code, err = save_materials(
                {"materials": mats, "version": data["versions"]["materials"]},
                user_id=1,
                changed_by="altan",
            )
            self.assertIsNone(err)
            self.assertEqual(result["priceChanges"], 1)
            done, code2, err2 = complete_updated(1)
            self.assertIsNone(err2, err2)
            self.assertEqual(done["status"], "updated")
            self.assertEqual(done["materialChangesCount"], 1)
            eva["cash"] = old
            save_materials(
                {"materials": mats, "version": fetch_all_data()["versions"]["materials"]},
                user_id=1,
                changed_by="altan",
            )

    def test_price_history_values(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        data = fetch_all_data()
        mats = data["materials"]
        eva = next(m for m in mats if m["code"] == "EVA-18")
        old = eva["cash"]
        eva["cash"] = old + 0.02
        with app.app_context():
            save_materials(
                {"materials": mats, "version": data["versions"]["materials"]},
                user_id=1,
                changed_by="altan",
            )
            with db_transaction() as conn:
                row = conn.execute(
                    "SELECT old_price, new_price FROM material_price_history ORDER BY id DESC LIMIT 1"
                ).fetchone()
            self.assertAlmostEqual(row["old_price"], old, places=4)
            self.assertAlmostEqual(row["new_price"], old + 0.02, places=4)
            eva["cash"] = old
            save_materials(
                {"materials": mats, "version": fetch_all_data()["versions"]["materials"]},
                user_id=1,
                changed_by="altan",
            )

    def test_no_history_for_unchanged_price(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        data = fetch_all_data()
        with app.app_context():
            with db_transaction() as conn:
                before = conn.execute(
                    "SELECT COUNT(*) AS n FROM material_price_history"
                ).fetchone()["n"]
            save_materials(
                {"materials": data["materials"], "version": data["versions"]["materials"]},
                user_id=1,
                changed_by="altan",
            )
            with db_transaction() as conn:
                after = conn.execute(
                    "SELECT COUNT(*) AS n FROM material_price_history"
                ).fetchone()["n"]
            self.assertEqual(before, after)

    def test_complete_without_save_fails(self):
        app, _, _ = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            _, code, err = complete_updated(1)
            self.assertEqual(code, 400)

    def test_status_survives_reload(self):
        app, client, csrf = self._app_client(monday_utc(2026, 9, 14))
        with app.app_context():
            confirm_unchanged(1)
        r = client.get("/api/weekly-review/status")
        self.assertFalse(r.json["due"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
