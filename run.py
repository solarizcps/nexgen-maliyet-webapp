# -*- coding: utf-8 -*-
"""Start NEXGEN local web app (single process, no debug reloader)."""
from app import app, bootstrap
import config

if __name__ == "__main__":
    bootstrap()
    url = f"http://{config.HOST}:{config.PORT}/"
    print(f"NEXGEN Maliyet Merkezi -> {url}", flush=True)
    print(f"SQLite DB: {config.DB_PATH}", flush=True)
    print(f"Version: {config.APP_VERSION}", flush=True)
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
