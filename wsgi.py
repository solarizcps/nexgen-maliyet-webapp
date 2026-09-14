# -*- coding: utf-8 -*-
"""Production WSGI entry (Waitress)."""
import os
import sys
import traceback
from datetime import datetime, timezone

from waitress import serve

from app import app, bootstrap
import config


def _lifecycle(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[nexgen-wsgi] {ts} pid={os.getpid()} {msg}", flush=True)


if __name__ == "__main__":
    bootstrap()
    _lifecycle(
        f"start host={config.HOST} port={config.PORT} env={config.NEXGEN_ENV} db={config.DB_PATH}"
    )
    try:
        serve(app, host=config.HOST, port=config.PORT, threads=8, channel_timeout=120)
        _lifecycle("exit code=0")
    except Exception:
        _lifecycle("fatal\n" + traceback.format_exc())
        sys.exit(1)
