# -*- coding: utf-8 -*-
"""Extract CSS and HTML body from Phase 1 source HTML."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "NEXGEN_Maliyet_Merkezi_ONAYLI_OZET.html"
CSS_OUT = ROOT / "static" / "css" / "app.css"
TPL_OUT = ROOT / "templates" / "index.html"

html = SRC.read_text(encoding="utf-8")
css_match = re.search(r"<style>(.*?)</style>", html, re.S)
css = css_match.group(1) if css_match else ""
CSS_OUT.parent.mkdir(parents=True, exist_ok=True)
CSS_OUT.write_text(css.strip() + "\n", encoding="utf-8")

body_match = re.search(r"<body>(.*)</body>", html, re.S)
body = body_match.group(1) if body_match else ""
# Remove duplicate modals (keep first only)
body = re.sub(
    r'(<div id="unsavedModal".*?</div></div>)\s*(?=<div id="unsavedModal")',
    "",
    body,
    flags=re.S,
)
body = re.sub(r"<script>.*?</script>", "", body, flags=re.S)

template = f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXGEN Maliyet Merkezi · Yerel DB Sürümü</title>
<link rel="stylesheet" href="{{{{ url_for('static', filename='css/app.css') }}}}">
</head>
<body>
{body.strip()}
<script src="{{{{ url_for('static', filename='js/app.js') }}}}"></script>
</body>
</html>
"""
TPL_OUT.parent.mkdir(parents=True, exist_ok=True)
TPL_OUT.write_text(template, encoding="utf-8")
print("CSS ->", CSS_OUT)
print("TPL ->", TPL_OUT)
