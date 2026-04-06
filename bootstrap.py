"""
bootstrap.py — First-run setup check for the macro tracker.

Run this on agent startup:
  python bootstrap.py

Initializes the database (safe to run any time — all DDL is idempotent).
Returns a JSON status object indicating whether onboarding is needed.

Exit codes:
  0 — DB initialized; status JSON printed to stdout
"""

import json
import os
from pathlib import Path

# Importing db triggers CREATE TABLE IF NOT EXISTS and default targets row
import db


def main() -> None:
    workspace = Path(__file__).parent

    # Check if macro targets have been set (all-zero means never configured)
    conn = db.get_connection()
    row = conn.execute(
        "SELECT protein_g, carbs_g, fat_g, fiber_g FROM macro_targets WHERE id = 1"
    ).fetchone()
    targets_set = row and any(
        row[k] > 0 for k in ("protein_g", "carbs_g", "fat_g", "fiber_g")
    )

    # Check if USER.md has dietary restriction content beyond the template
    user_md = workspace / "USER.md"
    user_md_populated = False
    if user_md.exists():
        content = user_md.read_text().strip()
        # Consider it populated if it has more than just the header line
        user_md_populated = len(content.splitlines()) > 1

    # Check if any ingredients exist
    ingredient_count = conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
    conn.close()

    needs_onboarding = not targets_set

    status = {
        "db_initialized": True,
        "db_path": str(db.DB_PATH),
        "targets_set": bool(targets_set),
        "user_md_exists": user_md.exists(),
        "user_md_populated": user_md_populated,
        "ingredient_count": ingredient_count,
        "needs_onboarding": needs_onboarding,
    }

    print(json.dumps(status))


if __name__ == "__main__":
    main()
