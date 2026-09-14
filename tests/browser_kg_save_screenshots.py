# -*- coding: utf-8 -*-
"""Browser screenshots for kg save fix (local server required)."""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_helpers import TEST_PASSWORD, TEST_USERNAME

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

PORT = int(os.environ.get("NEXGEN_TEST_PORT", "2345"))
BASE = f"http://127.0.0.1:{PORT}"
SHOT = os.path.join(ROOT, "screenshots_kg_save_fix")
CDP_PORT = 9234
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-kg-save-shots")


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
    edge = subprocess.Popen(
        [EDGE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*", f"--user-data-dir={PROFILE}", BASE + "/login"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    cdp = CDP()
    paths = []
    try:
        login_js = (
            "(async()=>{const csrf=window.__LOGIN_CSRF;"
            f"await fetch('/api/auth/login',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},"
            f"body:JSON.stringify({{username:{json.dumps(TEST_USERNAME)},password:{json.dumps(TEST_PASSWORD)}}})}});"
            "location.href='/'})()"
        )
        cdp.eval(login_js)
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx && window.__nx.loadState==='ready'"):
                break
        cdp.eval("document.querySelector('nav button[data-page=\"formulas\"]').click()")
        time.sleep(0.8)
        paths.append(cdp.shot("01_neo_profor_start.png"))
        cdp.eval("(()=>{const f=window.__nx.draft.formulas.find(x=>x.id==='neo-taban');const m=window.__nx.draft.materials.find(x=>x.code==='PROFOR');const l=f.lines.find(x=>x.materialId===m.id);l.kg='2';window.__nx.dirty.formulas=true;window.__nx.renderFormulas();window.__nx.renderCalc()})()")
        time.sleep(0.5)
        paths.append(cdp.shot("02_profor_2_dirty_preview.png"))
        cdp.eval("window.__nx.savePage('formulas')")
        time.sleep(2)
        paths.append(cdp.shot("03_save_success_timestamp.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        time.sleep(1.5)
        paths.append(cdp.shot("04_calc_new_total.png"))
        report = {
            "total_kg": cdp.eval("window.__nx.formulaTotalKg(window.__nx.committed.formulas.find(f=>f.id==='neo-taban'))"),
            "screenshots": paths,
        }
        with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
    finally:
        cdp.close()
        edge.terminate()


if __name__ == "__main__":
    main()
