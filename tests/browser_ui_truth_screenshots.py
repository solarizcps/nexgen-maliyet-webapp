# -*- coding: utf-8 -*-
"""Real browser screenshots for UI truth gate (config.PORT, no test prices on prod DB)."""
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

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = f"http://{config.HOST}:{config.PORT}"
SHOT = os.path.join(ROOT, "screenshots_ui_truth")
CDP_PORT = 9227
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-ui-truth-shots")


class CDP:
    def __init__(self):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list"))
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        self.ws = websocket.create_connection(url, timeout=15)
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


def wait_ready(cdp):
    for _ in range(60):
        if cdp.eval("!!window.__nx && window.__nx.committed.formulas.some(f=>f.id==='wanderfull')"):
            return
        time.sleep(0.25)
    raise RuntimeError("App not ready")


def main():
    os.makedirs(SHOT, exist_ok=True)
    edge = subprocess.Popen(
        [
            EDGE,
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            f"--user-data-dir={PROFILE}",
            BASE,
        ]
    )
    time.sleep(3)
    cdp = CDP()
    paths = []
    try:
        wait_ready(cdp)
        paths.append(cdp.shot("01_wanderfull_db.png"))
        cdp.eval(
            "const f=document.getElementById('calcFormula');"
            "f.value='wanderfull';f.dispatchEvent(new Event('change'));"
        )
        time.sleep(1)
        paths.append(cdp.shot("02_missing_price_warning.png"))
        cdp.eval("document.getElementById('btnFixPrices')?.click()")
        time.sleep(0.8)
        paths.append(cdp.shot("03_materials_highlighted.png"))
        cdp.eval(
            "const i=[...document.querySelectorAll('#materialRows input[data-k=cash]')][0];"
            "if(i){i.value='2.5';i.dispatchEvent(new Event('input',{bubbles:true}))}"
        )
        time.sleep(0.5)
        paths.append(cdp.shot("04_dirty_kaydet_active.png"))
        cdp.eval("document.querySelector('nav button[data-page=calc]').click()")
        time.sleep(0.5)
        paths.append(cdp.shot("05_unsaved_modal.png"))
        cdp.eval("document.getElementById('unsavedCancel').click()")
        cdp.eval(
            "const f=document.getElementById('calcFormula');f.value='wanderfull';"
            "f.dispatchEvent(new Event('change'))"
        )
        time.sleep(0.6)
        paths.append(cdp.shot("06_term_zero_rate_note.png"))
        cdp.eval(
            "const f=document.getElementById('calcFormula');f.value='aym';"
            "f.dispatchEvent(new Event('change'))"
        )
        time.sleep(0.8)
        paths.append(cdp.shot("07_aym_calc.png"))
        paths.append(cdp.shot("08_eva18_row.png"))
        cdp.eval("location.reload()")
        time.sleep(2.5)
        wait_ready(cdp)
        paths.append(cdp.shot("09_refresh_persistence.png"))
        data = json.load(urllib.request.urlopen(BASE + "/api/data"))
        report = {
            "base_url": BASE,
            "formula_count": len(data["formulas"]),
            "material_count": len(data["materials"]),
            "savedAt": data.get("savedAt"),
            "screenshots": paths,
        }
        with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        cdp.close()
        edge.terminate()


if __name__ == "__main__":
    main()
