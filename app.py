# -*- coding: utf-8 -*-
import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

import config
from db.connection import init_db
from services.auth_service import (
    authenticate,
    ensure_csrf_token,
    logout_user,
    normalize_username,
    rotate_csrf,
    validate_csrf,
)
from services.calc_engine import calculate
from services.import_data import import_localstorage
from services.repository import (
    delete_material,
    fetch_all_data,
    integrity_check,
    save_calc,
    save_expenses,
    save_formulas,
    save_materials,
)
from services.overhead_detail import overhead_breakdown
from services.weekly_review_service import (
    complete_updated,
    confirm_unchanged,
    get_status,
)


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = config.load_secret_key()
    app.config["PERMANENT_SESSION_LIFETIME"] = config.SESSION_LIFETIME
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = config.COOKIE_SAMESITE
    app.config["SESSION_COOKIE_SECURE"] = config.COOKIE_SECURE
    if test_config:
        app.config.update(test_config)

    @app.context_processor
    def inject_app_version():
        return {"app_version": config.APP_VERSION}

    PUBLIC_PATHS = {
        ("GET", "/login"),
        ("GET", "/api/auth/csrf"),
        ("POST", "/api/auth/login"),
    }

    WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    def is_authenticated():
        return bool(session.get("user_id"))

    def login_required_api(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_authenticated():
                return jsonify({"ok": False, "error": "Oturum gerekli"}), 401
            return fn(*args, **kwargs)

        return wrapper

    @app.before_request
    def security_gate():
        path = request.path
        method = request.method

        if path.startswith("/static/"):
            return None

        if (method, path) in PUBLIC_PATHS:
            return None

        if path == "/api/health":
            return None

        if not is_authenticated():
            if path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Oturum gerekli"}), 401
            return redirect(url_for("login_page", next=path))

        if method in WRITE_METHODS and path.startswith("/api/"):
            if path == "/api/auth/logout":
                pass
            elif not validate_csrf(session, request.headers.get("X-CSRF-Token")):
                return jsonify({"ok": False, "error": "CSRF doğrulaması başarısız"}), 403

        g.user_id = session.get("user_id")
        g.username = session.get("username")
        g.display_name = session.get("display_name")
        return None

    @app.after_request
    def no_cache_auth(response):
        if request.path in ("/", "/login") or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        return response

    @app.errorhandler(HTTPException)
    def api_http_errors(exc):
        if not request.path.startswith("/api/"):
            return exc
        return jsonify({"ok": False, "error": exc.description or exc.name}), exc.code

    @app.errorhandler(Exception)
    def api_json_errors(exc):
        if not request.path.startswith("/api/"):
            raise exc
        app.logger.exception("API error on %s", request.path)
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "Sunucu hatası",
                },
            }
        ), 500

    @app.route("/login")
    def login_page():
        if is_authenticated():
            return redirect(url_for("index"))
        csrf = ensure_csrf_token(session)
        return render_template("login.html", csrf_token=csrf)

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            display_name=session.get("display_name", ""),
            username=session.get("username", ""),
        )

    @app.route("/api/auth/csrf")
    def api_csrf():
        return jsonify({"ok": True, "csrfToken": ensure_csrf_token(session)})

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        if not validate_csrf(session, request.headers.get("X-CSRF-Token")):
            return jsonify({"ok": False, "error": "CSRF doğrulaması başarısız"}), 403
        body = request.get_json(force=True) or {}
        username = body.get("username") or ""
        password = body.get("password") or ""
        ip = request.remote_addr or "unknown"
        user, err, code = authenticate(username, password, ip)
        if err:
            return jsonify({"ok": False, "error": err}), code
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["display_name"] = user["display_name"]
        rotate_csrf(session)
        return jsonify(
            {
                "ok": True,
                "redirect": url_for("index"),
                "displayName": user["display_name"],
                "csrfToken": session["csrf_token"],
            }
        )

    @app.route("/api/auth/logout", methods=["POST"])
    @login_required_api
    def api_logout():
        logout_user(session, session.get("username"))
        session.clear()
        return jsonify({"ok": True, "redirect": url_for("login_page")})

    @app.route("/api/auth/me")
    @login_required_api
    def api_me():
        return jsonify(
            {
                "ok": True,
                "username": session.get("username"),
                "displayName": session.get("display_name"),
            }
        )

    @app.route("/api/health")
    def health():
        from db.connection import get_connection

        db_connected = False
        db_error = None
        try:
            conn = get_connection()
            try:
                conn.execute("SELECT 1").fetchone()
                db_connected = True
            finally:
                conn.close()
        except Exception as exc:
            db_error = str(exc)

        return jsonify(
            {
                "status": "ok" if db_connected else "degraded",
                "app": "NEXGEN Maliyet Merkezi",
                "version": config.APP_VERSION,
                "environment": config.NEXGEN_ENV,
                "wsgi_server": config.WSGI_SERVER,
                "debug": bool(app.debug),
                "db_connected": db_connected,
                "db_error": db_error,
                "db_path": config.DB_PATH,
                "db_label": "nexgen_local.db",
                "source": "sqlite",
                "host": config.HOST,
                "port": config.PORT,
                "authenticated": is_authenticated(),
                "server_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                )[:-3]
                + "Z",
            }
        )

    @app.route("/api/data")
    @login_required_api
    def api_data():
        data = fetch_all_data()
        data["weeklyReview"] = get_status()
        data["user"] = {
            "username": session.get("username"),
            "displayName": session.get("display_name"),
        }
        return jsonify(data)

    @app.route("/api/overhead/breakdown")
    @login_required_api
    def api_overhead_breakdown():
        return jsonify({"ok": True, **overhead_breakdown(fetch_all_data())})

    @app.route("/api/weekly-review/status")
    @login_required_api
    def api_weekly_status():
        return jsonify({"ok": True, **get_status()})

    @app.route("/api/weekly-review/unchanged", methods=["POST"])
    @login_required_api
    def api_weekly_unchanged():
        result, code, err = confirm_unchanged(g.user_id)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/weekly-review/complete", methods=["POST"])
    @login_required_api
    def api_weekly_complete():
        result, code, err = complete_updated(g.user_id)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/materials", methods=["PUT"])
    @login_required_api
    def api_save_materials():
        body = request.get_json(force=True)
        result, code, err = save_materials(
            body, user_id=g.user_id, changed_by=g.username
        )
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/expenses", methods=["PUT"])
    @login_required_api
    def api_save_expenses():
        body = request.get_json(force=True)
        result, code, err = save_expenses(body)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/formulas", methods=["PUT"])
    @login_required_api
    def api_save_formulas():
        body = request.get_json(force=True)
        result, code, err = save_formulas(body)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/calc", methods=["PUT"])
    @login_required_api
    def api_save_calc():
        body = request.get_json(force=True)
        result, code, err = save_calc(body)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/materials/<material_id>", methods=["DELETE"])
    @login_required_api
    def api_delete_material(material_id):
        confirmed = request.args.get("confirmed") == "1"
        result, code, err = delete_material(material_id, confirmed=confirmed)
        if err:
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, **result}), 200, {"Content-Type": "application/json"}

    @app.route("/api/calculate/<formula_id>")
    @login_required_api
    def api_calculate(formula_id):
        data = fetch_all_data()
        formula = next((f for f in data["formulas"] if f["id"] == formula_id), None)
        if not formula:
            return jsonify({"ok": False, "error": "Formül bulunamadı"}), 404
        result = calculate(data, formula)
        result["formulaId"] = formula_id
        return jsonify({"ok": result["valid"], "valid": result["valid"], "result": result})

    @app.route("/api/meta", methods=["PUT"])
    @login_required_api
    def api_meta():
        body = request.get_json(force=True) or {}
        active = body.get("activeFormulaId")
        from db.connection import db_transaction

        with db_transaction() as conn:
            conn.execute(
                "UPDATE settings SET active_formula_id = ? WHERE id = 1",
                (active,),
            )
        return jsonify({"ok": True, "activeFormulaId": active})

    @app.route("/api/integrity")
    @login_required_api
    def api_integrity():
        return jsonify(integrity_check())

    @app.route("/api/admin/import", methods=["POST"])
    @login_required_api
    def api_import():
        force = request.args.get("force") == "1"
        report = import_localstorage(force_recreate=force)
        return jsonify({"ok": True, "report": report})

    if os.environ.get("NEXGEN_SIMULATE_DB_ERROR") == "1":

        @app.before_request
        def simulate_db_error():
            if request.path.startswith("/api/") and request.method == "PUT":
                return jsonify({"ok": False, "error": "Simüle DB hatası"}), 500

    return app


def bootstrap():
    init_db(force=False)
    report_path = os.path.join(config.DATA_DIR, "import_report.json")
    if not os.path.exists(config.DB_PATH) or os.path.getsize(config.DB_PATH) < 4096:
        import_localstorage(force_recreate=True, report_path=report_path)
    else:
        with __import__("sqlite3").connect(config.DB_PATH) as c:
            mc = c.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            if mc == 0:
                import_localstorage(force_recreate=False, report_path=report_path)
    from db.connection import db_transaction
    from db.migrate_neo_overhead import migrate_neo_overhead

    with db_transaction() as conn:
        migrate_neo_overhead(conn)


app = create_app()

if __name__ == "__main__":
    bootstrap()
    app.run(host=config.HOST, port=config.PORT, debug=False)
