PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Katkı',
    cash_price REAL NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formulas (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    months REAL NOT NULL DEFAULT 0,
    monthly_rate REAL NOT NULL DEFAULT 0,
    profit_rate REAL NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formula_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    formula_id TEXT NOT NULL REFERENCES formulas(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE RESTRICT,
    quantity_kg REAL NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(formula_id, material_id, sort_order)
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    monthly_amount_try REAL NOT NULL,
    production_rate REAL NOT NULL DEFAULT 100,
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    monthly_production_kg REAL NOT NULL,
    usd_try_rate REAL NOT NULL,
    active_formula_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS page_saves (
    page TEXT PRIMARY KEY,
    saved_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS meta_versions (
    key TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'local-admin'
);

CREATE INDEX IF NOT EXISTS idx_formula_lines_formula ON formula_lines(formula_id);
CREATE INDEX IF NOT EXISTS idx_formula_lines_material ON formula_lines(material_id);
