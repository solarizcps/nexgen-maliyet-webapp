# -*- coding: utf-8 -*-
"""Browser verification for active-formula warning scope."""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_helpers import browser_login_eval_script
import config

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = f"http://{config.HOST}:{config.PORT}"
SHOT = os.path.join(ROOT, "screenshots_warning_scope")
CDP_PORT = 9232
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-warn-scope-shots")


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

    def shot(self, name, w=1366, h=768):
        self.ws.send(json.dumps({"id": 3, "method": "Emulation.setDeviceMetricsOverride", "params": {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False}}))
        time.sleep(0.15)
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


def pick_formula(cdp, fid):
    cdp.eval("document.getElementById('calcFormula').value='%s';document.getElementById('calcFormula').dispatchEvent(new Event('change'))" % fid)
    time.sleep(1.2)


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
    report = {}
    try:
        cdp.eval(browser_login_eval_script())
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx && window.__nx.loadState==='ready'"):
                break
        pick_formula(cdp, "neo-taban")
        report["neo_banner_hidden"] = cdp.eval("document.getElementById('calcError').hidden")
        report["neo_banner_text"] = cdp.eval("document.getElementById('calcError').innerText")
        report["neo_missing_count"] = cdp.eval("window.__nx.formulaMissingCount(window.__nx.committed.formulas.find(f=>f.id==='neo-taban'), window.__nx.committed)")
        paths.append(cdp.shot("01_neo_no_global_banner.png"))
        pick_formula(cdp, "dakirs")
        report["dakirs_banner"] = cdp.eval("document.getElementById('calcError').innerText")
        report["dakirs_missing_count"] = cdp.eval("window.__nx.formulaMissingCount(window.__nx.committed.formulas.find(f=>f.id==='dakirs'), window.__nx.committed)")
        paths.append(cdp.shot("02_dakirs_only_warnings.png"))
        pick_formula(cdp, "wanderfull")
        report["wanderfull_banner"] = cdp.eval("document.getElementById('calcError').innerText")
        report["wanderfull_missing_count"] = cdp.eval("window.__nx.formulaMissingCount(window.__nx.committed.formulas.find(f=>f.id==='wanderfull'), window.__nx.committed)")
        paths.append(cdp.shot("03_wanderfull_only_warnings.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"formulas\"]').click()")
        time.sleep(0.8)
        badges = cdp.eval("Array.from(document.querySelectorAll('.formula-miss-badge')).map(x=>x.textContent)")
        report["card_badges"] = badges
        paths.append(cdp.shot("04_formula_card_badges.png", 1366, 768))
        paths.append(cdp.shot("05_formula_cards_1920.png", 1920, 1080))
        report["screenshots"] = paths
        with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        cdp.close()
        edge.terminate()


if __name__ == "__main__":
    main()
