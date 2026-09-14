# -*- coding: utf-8 -*-
"""Browser screenshots for calc invalid-state fix — no real DB price changes."""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config

from tests.test_helpers import browser_login_eval_script_check_ok

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = f"http://{config.HOST}:{config.PORT}"
SHOT = os.path.join(ROOT, "screenshots_calc_fix")
CDP_PORT = 9229
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-calc-fix-shots")


class CDP:
    def __init__(self):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list"))
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        self.ws = websocket.create_connection(url, timeout=60)

    def eval(self, expr):
        self.ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == 1:
                return msg.get("result", {}).get("result", {}).get("value")

    def shot(self, name):
        self.ws.send(json.dumps({"id": 2, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == 2:
                data = msg["result"]["data"]
                path = os.path.join(SHOT, name)
                os.makedirs(SHOT, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(base64.b64decode(data))
                return path

    def close(self):
        self.ws.close()


def login(cdp):
    cdp.eval(browser_login_eval_script_check_ok())
    for _ in range(40):
        time.sleep(0.25)
        if cdp.eval("!!window.__nx"):
            return
    raise RuntimeError("login timeout")


def wait_calc(cdp):
    for _ in range(40):
        time.sleep(0.25)
        if cdp.eval("!!window.__nx && !window.__nx.dirty.calc"):
            return
    time.sleep(1)


def select_formula(cdp, fid):
    cdp.eval(f"window.__nx && document.getElementById('calcFormula').value='{fid}' && document.getElementById('calcFormula').dispatchEvent(new Event('change'))")
    wait_calc(cdp)


def main():
    os.makedirs(SHOT, exist_ok=True)
    paths = []
    edge = subprocess.Popen(
        [EDGE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*", f"--user-data-dir={PROFILE}", BASE + "/login"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    cdp = CDP()
    try:
        login(cdp)
        wait_calc(cdp)
        select_formula(cdp, "aym")
        time.sleep(1)
        paths.append(cdp.shot("01_aym_valid.png"))
        select_formula(cdp, "dakirs")
        time.sleep(1.2)
        paths.append(cdp.shot("02_dakirs_invalid_dashes.png"))
        paths.append(cdp.shot("03_dakirs_summary_note.png"))
        cdp.eval("document.getElementById('btnFixPrices')?.click()")
        time.sleep(0.8)
        paths.append(cdp.shot("04_missing_prices_materials.png"))
        select_formula(cdp, "wanderfull")
        time.sleep(1)
        paths.append(cdp.shot("05_wanderfull_invalid.png"))
        select_formula(cdp, "aym")
        time.sleep(1)
        paths.append(cdp.shot("06_dakirs_to_aym_no_stale.png"))
        cdp.eval("window.__nx.logout()")
        time.sleep(1)
        paths.append(cdp.shot("07_logout_regression.png"))
    finally:
        cdp.close()
        edge.terminate()
    report = {"screenshots": paths}
    with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
