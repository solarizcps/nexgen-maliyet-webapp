# -*- coding: utf-8 -*-
"""Capture localhost screenshots proving DB-backed web app."""
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
SHOT_DIR = os.path.join(ROOT, "screenshots_phase2")
PORT_CDP = 9226
USER_DATA = os.path.join(os.environ.get("TEMP", "."), "nexgen-phase2-shots")


class CDP:
    def __init__(self):
        self._id = 0
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT_CDP}/json/list"))
        self.ws = websocket.create_connection(
            next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        )

    def send(self, method, params=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == self._id:
                return data.get("result", {})

    def eval(self, expression):
        r = self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        return r.get("result", {}).get("value")

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", {"format": "png"})
        import base64

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(data["data"]))

    def close(self):
        self.ws.close()


def wait_ready(cdp, timeout=30):
    for _ in range(timeout * 4):
        ok = cdp.eval("!!window.__nx && window.__nx.committed.formulas.length > 0")
        if ok:
            return
        time.sleep(0.25)
    raise RuntimeError("App not ready")


def wait_cdp_port(timeout=20):
    for _ in range(timeout * 4):
        try:
            json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT_CDP}/json/list", timeout=1))
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    # Reuse persistent server if already running; never terminate it at exit
    server_started_here = False
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=2)
    except Exception:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                os.path.join(ROOT, "scripts", "start_nexgen_local.ps1"),
            ],
            cwd=ROOT,
            check=True,
        )
        server_started_here = False  # launcher owns lifecycle
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("Server did not start")

        edge = subprocess.Popen(
            [
                EDGE,
                f"--remote-debugging-port={PORT_CDP}",
                "--remote-allow-origins=*",
                f"--user-data-dir={USER_DATA}",
                "--no-first-run",
                "--no-default-browser-check",
                BASE,
            ]
        )
        if not wait_cdp_port():
            raise RuntimeError("Edge CDP not ready")
        time.sleep(1)
        cdp = CDP()
        wait_ready(cdp)

        shots = []
        cdp.screenshot(os.path.join(SHOT_DIR, "01_localhost_url.png"))
        shots.append("01_localhost_url.png")

        cdp.eval("document.querySelector('nav button[data-page=calc]').click()")
        time.sleep(0.5)
        cdp.eval(
            "document.getElementById('calcFormula').value='aym';"
            "document.getElementById('calcFormula').dispatchEvent(new Event('change'))"
        )
        time.sleep(0.8)
        cdp.screenshot(os.path.join(SHOT_DIR, "02_aym_maliyet.png"))
        shots.append("02_aym_maliyet.png")

        cdp.screenshot(os.path.join(SHOT_DIR, "03_eva18_line.png"))
        shots.append("03_eva18_line.png")

        cdp.eval("document.querySelector('nav button[data-page=materials]').click()")
        time.sleep(0.6)
        cdp.screenshot(os.path.join(SHOT_DIR, "04_malzeme_fiyatlari_kaydet.png"))
        shots.append("04_malzeme_fiyatlari_kaydet.png")

        cdp.eval("document.querySelector('nav button[data-page=formulas]').click()")
        time.sleep(0.6)
        cdp.screenshot(os.path.join(SHOT_DIR, "05_firma_formulleri_kaydet.png"))
        shots.append("05_firma_formulleri_kaydet.png")

        cdp.eval(
            "const i=document.querySelector('#materialRows input[data-k=cash]');"
            "if(i){i.value='2.00';i.dispatchEvent(new Event('input',{bubbles:true}));}"
        )
        cdp.eval("document.querySelector('nav button[data-page=materials]').click()")
        time.sleep(0.5)
        cdp.screenshot(os.path.join(SHOT_DIR, "06_unsaved_dirty.png"))
        shots.append("06_unsaved_dirty.png")

        cdp.eval("document.querySelector('nav button[data-page=expenses]').click()")
        time.sleep(0.5)
        cdp.screenshot(os.path.join(SHOT_DIR, "07_unsaved_modal.png"))
        shots.append("07_unsaved_modal.png")

        cdp.eval("document.getElementById('unsavedCancel').click()")
        cdp.eval("document.getElementById('saveMaterials').click()")
        time.sleep(1.2)
        cdp.screenshot(os.path.join(SHOT_DIR, "08_kaydedildi_timestamp.png"))
        shots.append("08_kaydedildi_timestamp.png")

        cdp.eval("location.reload()")
        time.sleep(2)
        wait_ready(cdp)
        cdp.screenshot(os.path.join(SHOT_DIR, "09_refresh_persistence.png"))
        shots.append("09_refresh_persistence.png")

        # restore EVA price and save
        cdp.eval(
            "document.querySelector('nav button[data-page=materials]').click();"
            "setTimeout(()=>{const rows=[...document.querySelectorAll('#materialRows tr')];"
            "const row=rows.find(r=>r.textContent.includes('EVA-18'));"
            "if(row){const i=row.querySelector('input[data-k=cash]');i.value='1.9';"
            "i.dispatchEvent(new Event('input',{bubbles:true}));}},300)"
        )
        time.sleep(0.8)
        cdp.eval("document.getElementById('saveMaterials').click()")
        time.sleep(1)

        cdp.eval(
            "document.querySelector('nav button[data-page=calc]').click();"
            "const f=document.getElementById('calcFormula');f.value='aym';"
            "f.dispatchEvent(new Event('change'));"
        )
        time.sleep(0.5)
        # Set boya with zero price to block calc - use draft material PBLUE if exists
        cdp.eval(
            "fetch('/api/data').then(r=>r.json()).then(d=>{"
            "const m=d.materials.find(x=>x.code==='PBLUE154');"
            "if(m){m.cash=0; return fetch('/api/materials',{method:'PUT',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({materials:d.materials,version:d.versions.materials})})}})"
        )
        time.sleep(1)
        cdp.eval("location.reload()")
        time.sleep(2)
        wait_ready(cdp)
        cdp.eval("document.querySelector('nav button[data-page=calc]').click()")
        cdp.eval(
            "const f=document.getElementById('calcFormula');"
            "const opt=[...f.options].find(o=>o.textContent.includes('WANDERFULL'));"
            "if(opt){f.value=opt.value;f.dispatchEvent(new Event('change'))}"
        )
        time.sleep(0.8)
        cdp.screenshot(os.path.join(SHOT_DIR, "10_calc_blocked_missing_price.png"))
        shots.append("10_calc_blocked_missing_price.png")

        report = {
            "base_url": BASE,
            "screenshots": [os.path.join(SHOT_DIR, s) for s in shots],
            "health": json.load(urllib.request.urlopen(BASE + "/api/health")),
        }
        with open(os.path.join(SHOT_DIR, "screenshot_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        cdp.close()
        edge.terminate()
    finally:
        pass  # keep NEXGEN server running for browser use


if __name__ == "__main__":
    main()
