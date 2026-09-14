# -*- coding: utf-8 -*-
"""Weekly hammadde price review (Europe/Istanbul, Monday week start)."""
from datetime import datetime, timedelta, timezone

from services.clock import IST, get_clock


def week_start_for(dt_local):
    """Monday local date as YYYY-MM-DD."""
    monday = dt_local.date() - timedelta(days=dt_local.weekday())
    return monday.isoformat()


def week_start_utc_iso(clock=None):
    clock = clock or get_clock()
    dt = clock.now_local()
    monday = dt.date() - timedelta(days=dt.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=IST)
    return start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def current_week_start(clock=None):
    clock = clock or get_clock()
    return week_start_for(clock.now_local())


def get_review_for_week(week_start):
    from db.connection import db_transaction

    with db_transaction() as conn:
        return conn.execute(
            """SELECT w.*, u.display_name AS reviewer_name
               FROM weekly_price_reviews w
               JOIN users u ON u.id = w.reviewed_by_user_id
               WHERE w.week_start_date = ?""",
            (week_start,),
        ).fetchone()


def get_last_review():
    from db.connection import db_transaction

    with db_transaction() as conn:
        return conn.execute(
            """SELECT w.*, u.display_name AS reviewer_name
               FROM weekly_price_reviews w
               JOIN users u ON u.id = w.reviewed_by_user_id
               ORDER BY w.reviewed_at DESC LIMIT 1"""
        ).fetchone()


def is_review_due(clock=None):
    clock = clock or get_clock()
    ws = current_week_start(clock)
    return get_review_for_week(ws) is None


def format_review_datetime(iso_utc):
    if not iso_utc:
        return ""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(IST)
    return dt.strftime("%d.%m.%Y %H:%M")


def get_status(clock=None):
    clock = clock or get_clock()
    ws = current_week_start(clock)
    current = get_review_for_week(ws)
    last = get_last_review()
    due = current is None
    badge = "pending" if due else "ok"
    badge_text = "Haftalık fiyat kontrolü bekliyor" if due else "Bu hafta kontrol edildi"
    last_line = ""
    if last:
        last_line = (
            f"Fiyatlar en son {last['reviewer_name']} tarafından "
            f"{format_review_datetime(last['reviewed_at'])} tarihinde kontrol edildi."
        )
    pending_changes = count_unlinked_changes(clock=clock) if due else 0
    return {
        "due": due,
        "weekStart": ws,
        "timezone": "Europe/Istanbul",
        "status": current["status"] if current else None,
        "badge": badge,
        "badgeText": badge_text,
        "lastReviewLine": last_line,
        "lastReviewAt": last["reviewed_at"] if last else None,
        "lastReviewer": last["reviewer_name"] if last else None,
        "pendingMaterialChanges": pending_changes,
        "canCompleteUpdated": due and pending_changes > 0,
    }


def count_unlinked_changes(week_start=None, clock=None):
    from db.connection import db_transaction

    cutoff = week_start_utc_iso(clock) if week_start is None else week_start
    with db_transaction() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM material_price_history
               WHERE weekly_review_id IS NULL AND changed_at >= ?""",
            (cutoff,),
        ).fetchone()
        return row["c"]


def _now(clock):
    return clock.now_utc().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def confirm_unchanged(user_id, clock=None):
    clock = clock or get_clock()
    ws = current_week_start(clock)
    if get_review_for_week(ws):
        return None, 409, "Bu hafta için kontrol zaten tamamlandı."

    from db.connection import db_transaction

    now = _now(clock)
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO weekly_price_reviews
               (week_start_date, status, reviewed_by_user_id, reviewed_at,
                material_changes_count, note, created_at)
               VALUES (?, 'unchanged', ?, ?, 0, NULL, ?)""",
            (ws, user_id, now, now),
        )
        review_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        import json

        conn.execute(
            """INSERT INTO audit_log
               (entity_type, entity_id, action, before_json, after_json, changed_at, changed_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "weekly_price_review",
                str(review_id),
                "confirm_unchanged",
                None,
                json.dumps({"week_start": ws, "status": "unchanged"}, ensure_ascii=False),
                now,
                "user",
            ),
        )
    return {"weekStart": ws, "status": "unchanged", "reviewedAt": now}, 200, None


def complete_updated(user_id, clock=None):
    clock = clock or get_clock()
    ws = current_week_start(clock)
    if get_review_for_week(ws):
        return None, 409, "Bu hafta için kontrol zaten tamamlandı."

    changes = count_unlinked_changes(clock=clock)
    if changes <= 0:
        return None, 400, "Fiyat değişikliği kaydedilmeden haftalık kontrol tamamlanamaz."

    from db.connection import db_transaction

    cutoff = week_start_utc_iso(clock)
    now = _now(clock)
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO weekly_price_reviews
               (week_start_date, status, reviewed_by_user_id, reviewed_at,
                material_changes_count, note, created_at)
               VALUES (?, 'updated', ?, ?, ?, NULL, ?)""",
            (ws, user_id, now, changes, now),
        )
        review_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """UPDATE material_price_history SET weekly_review_id = ?
               WHERE weekly_review_id IS NULL AND changed_at >= ?""",
            (review_id, cutoff),
        )
        import json

        conn.execute(
            """INSERT INTO audit_log
               (entity_type, entity_id, action, before_json, after_json, changed_at, changed_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "weekly_price_review",
                str(review_id),
                "confirm_updated",
                None,
                json.dumps(
                    {"week_start": ws, "status": "updated", "changes": changes},
                    ensure_ascii=False,
                ),
                now,
                "user",
            ),
        )
    return {
        "weekStart": ws,
        "status": "updated",
        "materialChangesCount": changes,
        "reviewedAt": now,
    }, 200, None
