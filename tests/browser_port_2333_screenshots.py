# -*- coding: utf-8 -*-
"""KAPI 6 browser screenshots on port 2333."""
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
SHOT = os.path.join(ROOT, "screenshots_port_2333")
CDP_PORT = 9233
PROFILE = os.path.join(os.environ.get("TEMP", "."), "nexgen-port2333-shots")


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
    report = {"base": BASE, "port": config.PORT}
    try:
        paths.append(cdp.shot("01_login_2333.png"))
        cdp.eval(browser_login_eval_script())
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx && window.__nx.loadState==='ready'"):
                break
        report["materials"] = cdp.eval("window.__nx.committed.materials.length")
        report["formulas"] = cdp.eval("window.__nx.committed.formulas.length")
        paths.append(cdp.shot("02_after_login_db_loaded.png"))
        cdp.eval("document.querySelector('nav button[data-page=\"formulas\"]').click()")
        time.sleep(0.8)
        paths.append(cdp.shot("03_five_formula_cards.png", 1920, 1080))
        cdp.eval("document.querySelector('nav button[data-page=\"calc\"]').click()")
        time.sleep(0.5)
        pick_formula(cdp, "neo-taban")
        report["neo_lines"] = cdp.eval("window.__nx.committed.formulas.find(f=>f.id==='neo-taban').lines.length")
        report["neo_expansion"] = cdp.eval("window.__nx.committed.formulas.find(f=>f.id==='neo-taban').baseExpansionMeasure")
        paths.append(cdp.shot("04_neo_taban.png"))
        paths.append(cdp.shot("05_neo_patlatma_145.png"))
        report["neo_total_kg"] = cdp.eval("window.__nx.calcFormulaForResult(window.__nx.committed.formulas.find(f=>f.id==='neo-taban'), window.__nx.committed).totalKg")
        paths.append(cdp.shot("06_neo_cost_calc.png"))
        report["monthly_kg"] = cdp.eval("window.__nx.committed.meta.monthlyProductionKg")
        report["overhead_per_kg"] = cdp.eval("window.__nx.committed.meta.overheadPerKgUsd")
        paths.append(cdp.shot("07_overhead_100k_kg.png"))
        pick_formula(cdp, "dakirs")
        report["dakirs_banner"] = cdp.eval("document.getElementById('calcError').innerText")
        paths.append(cdp.shot("08_dakirs_warnings_only.png"))
        pick_formula(cdp, "wanderfull")
        report["wanderfull_banner"] = cdp.eval("document.getElementById('calcError').innerText")
        paths.append(cdp.shot("09_wanderfull_warnings_only.png"))
        cdp.eval("(async()=>{const csrf=window.__nx.csrfToken;await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}});location.href='/login'})()")
        time.sleep(1.2)
        cdp.eval(browser_login_eval_script())
        for _ in range(40):
            time.sleep(0.25)
            if cdp.eval("!!window.__nx && window.__nx.loadState==='ready'"):
                break
        report["relogin_materials"] = cdp.eval("window.__nx.committed.materials.length")
        paths.append(cdp.shot("10_logout_relogin_loaded.png"))
    finally:
        cdp.close()
        edge.terminate()

    health = json.load(urllib.request.urlopen(BASE + "/api/health"))
    report["health"] = health
    with open(os.path.join(SHOT, "11_health_2333.json"), "w", encoding="utf-8") as f:
        json.dump(health, f, indent=2, ensure_ascii=False)

    report["screenshots"] = paths
    with open(os.path.join(SHOT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
