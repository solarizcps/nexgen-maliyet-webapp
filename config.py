import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.environ.get("NEXGEN_DB_PATH") or os.path.join(DATA_DIR, "nexgen_local.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")
_FIXTURE_IMPORT = os.path.join(BASE_DIR, "tests", "fixtures", "localstorage_seed.json")
_LEGACY_IMPORT = os.path.join(BASE_DIR, "..", "backup", "localstorage_real_user.json")
IMPORT_SOURCE = os.environ.get("NEXGEN_IMPORT_SOURCE") or (
    _LEGACY_IMPORT if os.path.exists(_LEGACY_IMPORT) else _FIXTURE_IMPORT
)
BACKUP_DIR = os.path.join(BASE_DIR, "backup")
SECRET_KEY_FILE = os.environ.get("NEXGEN_SECRET_FILE") or os.path.join(
    DATA_DIR, ".nexgen_secret"
)
NEXGEN_ENV = os.environ.get("NEXGEN_ENV", "development")
WSGI_SERVER = os.environ.get("NEXGEN_WSGI", "flask")

# Port 8080 is occupied by Solariz CPS — do not kill.
# NEXGEN canonical local port is 2333.
PORT = int(os.environ.get("NEXGEN_PORT", "2333"))
HOST = os.environ.get("NEXGEN_HOST", "127.0.0.1")
CHANGED_BY = "local-admin"
APP_VERSION = "3.0.3-kg-save"
TIMEZONE = "Europe/Istanbul"
SESSION_LIFETIME = timedelta(hours=int(os.environ.get("NEXGEN_SESSION_HOURS", "8")))
MAX_LOGIN_ATTEMPTS = int(os.environ.get("NEXGEN_MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("NEXGEN_LOGIN_WINDOW", "900"))
COOKIE_SECURE = os.environ.get("NEXGEN_COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.environ.get("NEXGEN_COOKIE_SAMESITE", "Lax")


def load_secret_key():
    env_key = os.environ.get("NEXGEN_SECRET_KEY")
    if env_key:
        return env_key
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    return key
