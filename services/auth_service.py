# -*- coding: utf-8 -*-
"""Authentication, session helpers, rate limiting."""
import json
import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash

import config
from db.connection import db_transaction


def normalize_username(username):
    return (username or "").strip().lower()


def ensure_csrf_token(session):
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf(session, header_token):
    expected = session.get("csrf_token")
    if not expected or not header_token:
        return False
    return secrets.compare_digest(expected, header_token)


def rotate_csrf(session):
    session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _audit(conn, action, user_id, before, after, changed_by):
    conn.execute(
        """INSERT INTO audit_log
           (entity_type, entity_id, action, before_json, after_json, changed_at, changed_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "auth",
            str(user_id) if user_id else None,
            action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            _now(),
            changed_by or "system",
        ),
    )


def count_recent_failed_attempts(ip_address, window_seconds=None):
    window = window_seconds or config.LOGIN_WINDOW_SECONDS
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=window)
    ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    with db_transaction() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM login_attempts
               WHERE ip_address = ? AND success = 0 AND attempted_at >= ?""",
            (ip_address, cutoff),
        ).fetchone()
        return row["c"]


def is_rate_limited(ip_address):
    return count_recent_failed_attempts(ip_address) >= config.MAX_LOGIN_ATTEMPTS


def record_login_attempt(ip_address, username_normalized, success):
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO login_attempts (ip_address, username_normalized, attempted_at, success)
               VALUES (?, ?, ?, ?)""",
            (ip_address, username_normalized, _now(), 1 if success else 0),
        )


def find_user(username_normalized):
    with db_transaction() as conn:
        return conn.execute(
            """SELECT id, username, display_name, password_hash, is_active,
                      must_change_password, failed_login_count, locked_until
               FROM users WHERE username = ? COLLATE NOCASE""",
            (username_normalized,),
        ).fetchone()


def authenticate(username, password, ip_address):
    if is_rate_limited(ip_address):
        return None, "Çok fazla başarısız deneme. Lütfen bir süre sonra tekrar deneyin.", 429

    uname = normalize_username(username)
    user = find_user(uname)
    generic = "Kullanıcı adı veya şifre hatalı."

    if not user or not user["is_active"]:
        record_login_attempt(ip_address, uname, False)
        return None, generic, 401

    if user["locked_until"]:
        locked = user["locked_until"]
        if locked > _now():
            record_login_attempt(ip_address, uname, False)
            return None, generic, 401

    if not check_password_hash(user["password_hash"], password):
        with db_transaction() as conn:
            failed = (user["failed_login_count"] or 0) + 1
            locked_until = None
            if failed >= config.MAX_LOGIN_ATTEMPTS:
                locked_until = (
                    datetime.now(timezone.utc) + timedelta(seconds=config.LOGIN_WINDOW_SECONDS)
                ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            conn.execute(
                """UPDATE users SET failed_login_count = ?, locked_until = ?, updated_at = ?
                   WHERE id = ?""",
                (failed, locked_until, _now(), user["id"]),
            )
        record_login_attempt(ip_address, uname, False)
        return None, generic, 401

    now = _now()
    with db_transaction() as conn:
        conn.execute(
            """UPDATE users SET failed_login_count = 0, locked_until = NULL,
               last_login_at = ?, updated_at = ? WHERE id = ?""",
            (now, now, user["id"]),
        )
        _audit(
            conn,
            "login",
            user["id"],
            None,
            {"username": user["username"], "ip": ip_address},
            user["username"],
        )
    record_login_attempt(ip_address, uname, True)
    return user, None, 200


def logout_user(session, user_label=""):
    user_id = session.get("user_id")
    if user_id:
        with db_transaction() as conn:
            _audit(
                conn,
                "logout",
                user_id,
                None,
                {"username": session.get("username")},
                user_label or session.get("username") or "user",
            )
    session.clear()


def get_user_by_id(user_id):
    with db_transaction() as conn:
        return conn.execute(
            "SELECT id, username, display_name, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
