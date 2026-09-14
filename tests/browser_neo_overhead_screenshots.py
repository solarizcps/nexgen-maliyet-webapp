# -*- coding: utf-8 -*-
import base64, json, os, subprocess, sys, time, urllib.request
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
SHOT = os.path.join(ROOT, "screenshots_neo_overhead")
CDP_PORT = 9230
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-neo-shots")


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
    edge = subprocess.Popen([EDGE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*", f"--user-data-dir={PROFILE}", BASE + "/login"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    cdp = CDP()
    try:
        cdp.eval(browser_login_eval_script())
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx"):
                break
        cdp.eval("document.getElementById('calcFormula').value='neo-taban';document.getElementById('calcFormula').dispatchEvent(new Event('change'))")
        time.sleep(2)
        paths.append(cdp.shot("01_neo_formula_selected.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"formulas\"]').click()")
        time.sleep(1)
        cdp.eval("document.querySelector('#formulaList button[data-f=\"neo-taban\"]')?.click()")
        time.sleep(0.8)
        paths.append(cdp.shot("02_neo_formulas_12_lines.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        time.sleep(1.2)
        paths.append(cdp.shot("03_neo_cost_summary.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"expenses\"]').click()")
        time.sleep(0.8)
        paths.append(cdp.shot("04_overhead_detail.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click();document.getElementById('calcFormula').value='aym';document.getElementById('calcFormula').dispatchEvent(new Event('change'))")
        time.sleep(1.2)
        paths.append(cdp.shot("05_aym_valid_regression.png"))
    finally:
        cdp.close()
        edge.terminate()
    with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"screenshots": paths}, f, indent=2)
    print(json.dumps({"screenshots": paths}, indent=2))


if __name__ == "__main__":
    main()
