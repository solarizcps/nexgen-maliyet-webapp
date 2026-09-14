# -*- coding: utf-8 -*-
"""Real browser checks for formula UI fix — Edge CDP."""
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

from tests.test_helpers import browser_login_eval_script

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = f"http://{config.HOST}:{config.PORT}"
SHOT = os.path.join(ROOT, "screenshots_formula_ui")
CDP_PORT = 9231
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-formula-ui-shots")


class CDP:
    def __init__(self):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list"))
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        self.ws = websocket.create_connection(url, timeout=60)

    def eval(self, expr):
        self.ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
                }
            )
        )
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == 1:
                return msg.get("result", {}).get("result", {}).get("value")

    def shot(self, name, w=1366, h=768):
        self.ws.send(json.dumps({"id": 3, "method": "Emulation.setDeviceMetricsOverride", "params": {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False}}))
        time.sleep(0.2)
        self.ws.send(json.dumps({"id": 2, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == 2:
                path = os.path.join(SHOT, name)
                os.makedirs(SHOT, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(base64.b64decode(msg["result"]["data"]))
                return path

    def close(self):
        self.ws.close()


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
        cdp.eval(browser_login_eval_script())
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx && window.__nx.loadState==='ready'"):
                break
        state = {
            "loadState": cdp.eval("window.__nx.loadState"),
            "retryHidden": cdp.eval("document.getElementById('btnRetryLoad').hidden"),
            "stackHidden": cdp.eval("document.getElementById('bannerStack').hidden"),
        }
        paths.append(cdp.shot("01_ready_no_retry_1366.png", 1366, 768))
        paths.append(cdp.shot("02_ready_no_retry_1920.png", 1920, 1080))
        cdp.eval("document.querySelector('nav button[data-page=\"formulas\"]').click()")
        time.sleep(0.8)
        paths.append(cdp.shot("03_formula_cards.png", 1366, 768))
        cdp.eval("document.querySelector('#formulaList button[data-f=\"neo-taban\"]').click()")
        time.sleep(0.5)
        neo_exp = cdp.eval("document.getElementById('fBaseExpansion').value")
        paths.append(cdp.shot("04_neo_expansion.png", 1366, 768))
        cdp.eval("document.querySelector('#formulaList button[data-f=\"aym\"]').click()")
        time.sleep(0.5)
        aym_exp = cdp.eval("document.getElementById('fBaseExpansion').value")
        paths.append(cdp.shot("05_aym_empty_expansion.png", 1366, 768))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        time.sleep(0.8)
        cdp.eval("document.getElementById('calcFormula').value='neo-taban';document.getElementById('calcFormula').dispatchEvent(new Event('change'))")
        time.sleep(1.2)
        paths.append(cdp.shot("06_neo_calc.png", 1366, 768))
        report = {"screenshots": paths, "state": state, "neo_expansion_field": neo_exp, "aym_expansion_field": aym_exp}
        with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        cdp.close()
        edge.terminate()


if __name__ == "__main__":
    main()
