"""
db.py — SQLite connection and schema initialization.

All other modules import get_connection() from here.
The database file is macro_tracker.db at the workspace root.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "macro_tracker.db"

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS macro_targets (
    id         INTEGER PRIMARY KEY,
    protein_g  REAL NOT NULL DEFAULT 0,
    carbs_g    REAL NOT NULL DEFAULT 0,
    fat_g      REAL NOT NULL DEFAULT 0,
    fiber_g    REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingredients_raw (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL CHECK(source IN ('usda', 'label')),
    raw_payload TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingredients (
    id               TEXT PRIMARY KEY,
    raw_id           TEXT NOT NULL REFERENCES ingredients_raw(id),
    name             TEXT NOT NULL,
    protein_per_100g REAL NOT NULL DEFAULT 0,
    carbs_per_100g   REAL NOT NULL DEFAULT 0,
    fat_per_100g     REAL NOT NULL DEFAULT 0,
    fiber_per_100g   REAL NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    notes      TEXT,
    available  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id     TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
    quantity_g    REAL NOT NULL,
    PRIMARY KEY (recipe_id, ingredient_id)
);

CREATE TABLE IF NOT EXISTS daily_logs (
    id          TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('ingredient', 'recipe')),
    source_id   TEXT NOT NULL,
    quantity_g  REAL NOT NULL,
    protein     REAL NOT NULL DEFAULT 0,
    carbs       REAL NOT NULL DEFAULT 0,
    fat         REAL NOT NULL DEFAULT 0,
    fiber       REAL NOT NULL DEFAULT 0,
    meal        TEXT NOT NULL CHECK(meal IN ('breakfast', 'lunch', 'dinner', 'snack')),
    notes       TEXT,
    logged_at   TEXT NOT NULL
);
"""

DEFAULT_TARGETS = """
INSERT OR IGNORE INTO macro_targets (id, protein_g, carbs_g, fat_g, fiber_g)
VALUES (1, 0, 0, 0, 0);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript(DDL)
        conn.execute(DEFAULT_TARGETS)
    conn.close()


# Auto-initialize on import
init_db()
