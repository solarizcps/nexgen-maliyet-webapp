# -*- coding: utf-8 -*-
"""Phase 3 browser screenshots — backup/restore real DB if weekly review written."""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config

from tests.test_helpers import (
    browser_login_eval_script_check_ok,
    browser_login_eval_script_csrf_api,
)

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = f"http://{config.HOST}:{config.PORT}"
SHOT = os.path.join(ROOT, "screenshots_phase3")
CDP_PORT = 9228
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-phase3-shots")
DB_BACKUP = os.path.join(ROOT, "backup", "phase3_screenshot_pre.db")


class CDP:
    def __init__(self):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list"))
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        self.ws = websocket.create_connection(url, timeout=60)
        self._id = 0

    def send(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                return msg.get("result", {})

    def eval(self, expr):
        return self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}).get(
            "result", {}
        ).get("value")

    def shot(self, name):
        data = self.send("Page.captureScreenshot", {"format": "png"})["data"]
        path = os.path.join(SHOT, name)
        os.makedirs(SHOT, exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        return path

    def close(self):
        self.ws.close()


def wait_js(cdp, expr, timeout=30):
    for _ in range(int(timeout / 0.25)):
        if cdp.eval(expr):
            return True
        time.sleep(0.25)
    return False


def api_status(path):
    try:
        req = urllib.request.Request(BASE + path)
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    os.makedirs(SHOT, exist_ok=True)
    os.makedirs(os.path.dirname(DB_BACKUP), exist_ok=True)
    shutil.copy2(config.DB_PATH, DB_BACKUP)
    paths = []

    edge = subprocess.Popen(
        [EDGE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*", f"--user-data-dir={PROFILE}", BASE + "/login"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    cdp = CDP()
    try:
        paths.append(cdp.shot("01_login.png"))
        cdp.eval(browser_login_eval_script_check_ok())
        wait_js(cdp, "!!window.__nx && window.__nx.committed.formulas.length>=4")
        time.sleep(0.8)
        paths.append(cdp.shot("02_home_after_login.png"))
        wait_js(cdp, "!document.getElementById('weeklyReviewModal').hidden")
        paths.append(cdp.shot("03_weekly_review_modal.png"))
        cdp.eval("document.getElementById('weeklyGoMaterials').click()")
        time.sleep(0.6)
        paths.append(cdp.shot("04_materials_weekly_pending.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        wait_js(cdp, "!document.getElementById('weeklyReviewModal').hidden")
        cdp.eval("document.getElementById('weeklyUnchanged').click()")
        wait_js(cdp, "document.getElementById('weeklyReviewModal').hidden", timeout=45)
        time.sleep(1.2)
        paths.append(cdp.shot("05_weekly_unchanged_confirmed.png"))
        wait_js(cdp, "!!document.getElementById('reviewLastLine').textContent")
        paths.append(cdp.shot("06_last_review_banner.png"))
        paths.append(cdp.shot("07_logout_button_visible.png"))
        cdp.eval("window.__nx.logout()")
        time.sleep(1.2)
        paths.append(cdp.shot("08_after_logout_login.png"))
        api401 = api_status("/api/data")
        cdp.eval(f"document.title='API_DATA_STATUS_{api401}'")
        paths.append(cdp.shot("09_api_401_proof.png"))
        cdp.eval(browser_login_eval_script_csrf_api())
        wait_js(cdp, "!!window.__nx")
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        time.sleep(0.6)
        paths.append(cdp.shot("10_calc_eva18_row.png"))
    finally:
        cdp.close()
        edge.terminate()

    shutil.copy2(DB_BACKUP, config.DB_PATH)
    report = {"screenshots": paths, "api_unauth_status": api_status("/api/data"), "db_restored": True}
    with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
