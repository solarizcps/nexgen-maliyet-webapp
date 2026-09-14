# NexGen Maliyet Webapp

Flask + SQLite maliyet hesaplama uygulaması (port **2333**, production’da Waitress).

## Gereksinimler

- Python 3.11+
- Windows (production scriptleri)

## Kurulum (temiz clone)

```powershell
cd nexgen-maliyet-webapp
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Runtime veritabanı ve secret **repository’de yoktur**. İlk çalıştırmada `data/` altında otomatik oluşturulur:

```powershell
$env:NEXGEN_DB_PATH = "$PWD\data\nexgen_local.db"
$env:NEXGEN_SECRET_FILE = "$PWD\data\.nexgen_secret"
python run.py
```

Boş DB için seed: `tests/fixtures/localstorage_seed.json` (veya `NEXGEN_IMPORT_SOURCE` ile özel JSON).

Health: `http://127.0.0.1:2333/api/health`

## Testler (izole temp DB)

```powershell
Remove-Item Env:NEXGEN_* -ErrorAction SilentlyContinue
python -m unittest discover -s tests -p "test_*.py"
```

Production DB veya `.nexgen_secret` dosyasını testlere kopyalamayın.

## Production (Windows sunucu)

- Kök: `C:\nexgen_maliyet`
- Port: `2333` (CPS **8080**’e dokunulmaz)
- Scriptler: `scripts/production/`
