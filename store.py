"""
store.py — All SQLite reads and writes for the macro tracker.

Usage:
  python store.py <command> [args]

Commands:
  create_ingredient_raw --source <usda|label> --payload '<json>'
  list_ingredients [--name <substr>]
  get_ingredient --id <id>

  create_recipe --name <name> --ingredients '<json>'
  list_recipes [--name <substr>] [--all]
  get_recipe --id <id>
  get_recipe_serving --id <id> --grams <g>
  set_recipe_available --id <id> --available <true|false>
  delete_recipe --id <id>

  create_daily_log --source_type <type> --source_id <id> --quantity_g <g> --meal <meal> [--notes '<text>']
  list_daily_logs --date <YYYY-MM-DD>
  delete_daily_log --id <id>

  get_targets
  upsert_targets --protein_g <g> --carbs_g <g> --fat_g <g> --fiber_g <g>
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import db
from models import (
    DailyLog,
    DailyLogsForDay,
    Ingredient,
    IngredientRaw,
    MacroTargets,
    Recipe,
    RecipeDetail,
    RecipeIngredientDetail,
    RecipeServing,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def print_json(obj: Any) -> None:
    if hasattr(obj, "model_dump"):
        print(json.dumps(obj.model_dump()))
    else:
        print(json.dumps(obj))


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

NUTRIENT_IDS = {
    "protein": 1003,
    "fat": 1004,
    "carbs": 1005,
    "fiber": 1079,
}


def _normalize_usda(payload: Dict[str, Any]) -> Dict[str, float]:
    """Extract per-100g macros from a USDA food payload."""
    nutrients: Dict[str, float] = {
        "protein": 0.0,
        "fat": 0.0,
        "carbs": 0.0,
        "fiber": 0.0,
    }

    food_nutrients = payload.get("foodNutrients", [])
    for fn in food_nutrients:
        nid = fn.get("nutrientId") or (fn.get("nutrient") or {}).get("id")
        value = fn.get("value") or fn.get("amount") or 0.0
        for macro, target_id in NUTRIENT_IDS.items():
            if nid == target_id:
                nutrients[macro] = float(value)

    # Fallback to labelNutrients for branded foods where foodNutrients may be sparse
    label_nutrients = payload.get("labelNutrients", {})
    if label_nutrients:
        serving_size_g = float(payload.get("servingSize", 100) or 100)
        if serving_size_g == 0:
            serving_size_g = 100

        mapping = {
            "protein": "protein",
            "fat": "fat",
            "carbs": "carbohydrates",
            "fiber": "fiber",
        }
        for macro, label_key in mapping.items():
            if nutrients[macro] == 0.0 and label_key in label_nutrients:
                per_serving = float(label_nutrients[label_key].get("value", 0) or 0)
                nutrients[macro] = (per_serving / serving_size_g) * 100

    return nutrients


def _normalize_label(payload: Dict[str, Any]) -> Dict[str, float]:
    """Extract per-100g macros from a label scan payload (already normalized by agent)."""
    return {
        "protein": float(payload.get("protein_per_100g", 0) or 0),
        "fat": float(payload.get("fat_per_100g", 0) or 0),
        "carbs": float(payload.get("carbs_per_100g", 0) or 0),
        "fiber": float(payload.get("fiber_per_100g", 0) or 0),
    }


def _get_ingredient_name(payload: Dict[str, Any], source: str) -> str:
    if source == "label":
        return payload.get("name", "Unknown")
    # USDA
    return (
        payload.get("description") or payload.get("lowercaseDescription") or "Unknown"
    )


# ---------------------------------------------------------------------------
# Ingredient commands
# ---------------------------------------------------------------------------


def create_ingredient_raw(source: str, payload_str: str) -> None:
    payload = json.loads(payload_str)
    raw_id = str(uuid.uuid4())
    ing_id = str(uuid.uuid4())
    ts = now_iso()

    if source == "usda":
        macros = _normalize_usda(payload)
    else:
        macros = _normalize_label(payload)

    name = _get_ingredient_name(payload, source)

    conn = db.get_connection()
    with conn:
        conn.execute(
            "INSERT INTO ingredients_raw (id, source, raw_payload, created_at) VALUES (?, ?, ?, ?)",
            (raw_id, source, json.dumps(payload), ts),
        )
        conn.execute(
            """INSERT INTO ingredients
               (id, raw_id, name, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ing_id,
                raw_id,
                name,
                macros["protein"],
                macros["carbs"],
                macros["fat"],
                macros["fiber"],
                ts,
            ),
        )
    row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ing_id,)).fetchone()
    conn.close()
    print_json(Ingredient.model_validate(dict(row)))


def list_ingredients(name_filter: Optional[str] = None) -> None:
    conn = db.get_connection()
    if name_filter:
        rows = conn.execute(
            "SELECT * FROM ingredients WHERE LOWER(name) LIKE ? ORDER BY created_at DESC",
            (f"%{name_filter.lower()}%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ingredients ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    print_json([Ingredient.model_validate(dict(r)).model_dump() for r in rows])


def get_ingredient(ing_id: str) -> None:
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM ingredients WHERE id = ?", (ing_id,)).fetchone()
    conn.close()
    if not row:
        print(json.dumps({"error": f"Ingredient {ing_id} not found"}))
        sys.exit(1)
    print_json(Ingredient.model_validate(dict(row)))


# ---------------------------------------------------------------------------
# Recipe commands
# ---------------------------------------------------------------------------


def _compute_recipe_detail(conn, recipe_id: str) -> RecipeDetail:
    recipe_row = conn.execute(
        "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
    ).fetchone()
    if not recipe_row:
        raise ValueError(f"Recipe {recipe_id} not found")

    ri_rows = conn.execute(
        """SELECT ri.ingredient_id, ri.quantity_g,
                  i.name, i.protein_per_100g, i.carbs_per_100g, i.fat_per_100g, i.fiber_per_100g
           FROM recipe_ingredients ri
           JOIN ingredients i ON i.id = ri.ingredient_id
           WHERE ri.recipe_id = ?""",
        (recipe_id,),
    ).fetchall()

    ingredients = []
    total_protein = total_carbs = total_fat = total_fiber = total_grams = 0.0
    for r in ri_rows:
        q = r["quantity_g"]
        factor = q / 100
        p = r["protein_per_100g"] * factor
        c = r["carbs_per_100g"] * factor
        f = r["fat_per_100g"] * factor
        fi = r["fiber_per_100g"] * factor
        ingredients.append(
            RecipeIngredientDetail(
                ingredient_id=r["ingredient_id"],
                name=r["name"],
                quantity_g=q,
                protein=p,
                carbs=c,
                fat=f,
                fiber=fi,
            )
        )
        total_protein += p
        total_carbs += c
        total_fat += f
        total_fiber += fi
        total_grams += q

    return RecipeDetail(
        id=recipe_row["id"],
        name=recipe_row["name"],
        notes=recipe_row["notes"],
        available=bool(recipe_row["available"]),
        created_at=recipe_row["created_at"],
        ingredients=ingredients,
        total_protein=total_protein,
        total_carbs=total_carbs,
        total_fat=total_fat,
        total_fiber=total_fiber,
        total_grams=total_grams,
    )


def create_recipe(
    name: str, ingredients_json: str, notes: Optional[str] = None
) -> None:
    ingredients = json.loads(ingredients_json)
    recipe_id = str(uuid.uuid4())
    ts = now_iso()

    conn = db.get_connection()
    with conn:
        conn.execute(
            "INSERT INTO recipes (id, name, notes, available, created_at) VALUES (?, ?, ?, 0, ?)",
            (recipe_id, name, notes, ts),
        )
        for item in ingredients:
            conn.execute(
                "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity_g) VALUES (?, ?, ?)",
                (recipe_id, item["ingredient_id"], item["quantity_g"]),
            )
    detail = _compute_recipe_detail(conn, recipe_id)
    conn.close()
    print_json(detail)


def list_recipes(name_filter: Optional[str] = None, include_all: bool = False) -> None:
    conn = db.get_connection()
    query = "SELECT * FROM recipes"
    params = []
    conditions = []
    if not include_all:
        conditions.append("available = 1")
    if name_filter:
        conditions.append("LOWER(name) LIKE ?")
        params.append(f"%{name_filter.lower()}%")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append(
            Recipe(
                id=r["id"],
                name=r["name"],
                notes=r["notes"],
                available=bool(r["available"]),
                created_at=r["created_at"],
            ).model_dump()
        )
    print_json(result)


def get_recipe(recipe_id: str) -> None:
    conn = db.get_connection()
    try:
        detail = _compute_recipe_detail(conn, recipe_id)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()
    print_json(detail)


def get_recipe_serving(recipe_id: str, grams: float) -> None:
    conn = db.get_connection()
    try:
        detail = _compute_recipe_detail(conn, recipe_id)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()

    if detail.total_grams == 0:
        factor = 0.0
    else:
        factor = grams / detail.total_grams

    serving = RecipeServing(
        recipe_id=recipe_id,
        grams=grams,
        protein=detail.total_protein * factor,
        carbs=detail.total_carbs * factor,
        fat=detail.total_fat * factor,
        fiber=detail.total_fiber * factor,
    )
    print_json(serving)


def set_recipe_available(recipe_id: str, available: bool) -> None:
    conn = db.get_connection()
    with conn:
        conn.execute(
            "UPDATE recipes SET available = ? WHERE id = ?",
            (1 if available else 0, recipe_id),
        )
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.close()
    if not row:
        print(json.dumps({"error": f"Recipe {recipe_id} not found"}))
        sys.exit(1)
    print_json(
        Recipe(
            id=row["id"],
            name=row["name"],
            notes=row["notes"],
            available=bool(row["available"]),
            created_at=row["created_at"],
        )
    )


def delete_recipe(recipe_id: str) -> None:
    conn = db.get_connection()
    with conn:
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.close()
    print_json({"deleted": recipe_id})


# ---------------------------------------------------------------------------
# Daily log commands
# ---------------------------------------------------------------------------


def _compute_macros_for_source(
    conn, source_type: str, source_id: str, quantity_g: float
) -> Dict[str, float]:
    if source_type == "ingredient":
        row = conn.execute(
            "SELECT * FROM ingredients WHERE id = ?", (source_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Ingredient {source_id} not found")
        factor = quantity_g / 100
        return {
            "protein": row["protein_per_100g"] * factor,
            "carbs": row["carbs_per_100g"] * factor,
            "fat": row["fat_per_100g"] * factor,
            "fiber": row["fiber_per_100g"] * factor,
        }
    else:  # recipe
        detail = _compute_recipe_detail(conn, source_id)
        if detail.total_grams == 0:
            factor = 0.0
        else:
            factor = quantity_g / detail.total_grams
        return {
            "protein": detail.total_protein * factor,
            "carbs": detail.total_carbs * factor,
            "fat": detail.total_fat * factor,
            "fiber": detail.total_fiber * factor,
        }


def create_daily_log(
    source_type: str,
    source_id: str,
    quantity_g: float,
    meal: str,
    notes: Optional[str] = None,
) -> None:
    log_id = str(uuid.uuid4())
    ts = now_iso()
    log_date = today_iso()

    conn = db.get_connection()
    try:
        macros = _compute_macros_for_source(conn, source_type, source_id, quantity_g)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    with conn:
        conn.execute(
            """INSERT INTO daily_logs
               (id, date, source_type, source_id, quantity_g, protein, carbs, fat, fiber, meal, notes, logged_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                log_id,
                log_date,
                source_type,
                source_id,
                quantity_g,
                macros["protein"],
                macros["carbs"],
                macros["fat"],
                macros["fiber"],
                meal,
                notes,
                ts,
            ),
        )
    row = conn.execute("SELECT * FROM daily_logs WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    print_json(DailyLog.model_validate(dict(row)))


def list_daily_logs(date_str: str) -> None:
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_logs WHERE date = ? ORDER BY logged_at ASC",
        (date_str,),
    ).fetchall()
    conn.close()

    entries = [DailyLog.model_validate(dict(r)) for r in rows]
    total_protein = sum(e.protein for e in entries)
    total_carbs = sum(e.carbs for e in entries)
    total_fat = sum(e.fat for e in entries)
    total_fiber = sum(e.fiber for e in entries)

    result = DailyLogsForDay(
        date=date_str,
        entries=entries,
        total_protein=total_protein,
        total_carbs=total_carbs,
        total_fat=total_fat,
        total_fiber=total_fiber,
    )
    print_json(result)


def delete_daily_log(log_id: str) -> None:
    conn = db.get_connection()
    with conn:
        conn.execute("DELETE FROM daily_logs WHERE id = ?", (log_id,))
    conn.close()
    print_json({"deleted": log_id})


# ---------------------------------------------------------------------------
# Macro targets
# ---------------------------------------------------------------------------


def get_targets() -> None:
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM macro_targets WHERE id = 1").fetchone()
    conn.close()
    print_json(MacroTargets.model_validate(dict(row)))


def upsert_targets(
    protein_g: float, carbs_g: float, fat_g: float, fiber_g: float
) -> None:
    conn = db.get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO macro_targets (id, protein_g, carbs_g, fat_g, fiber_g) VALUES (1, ?, ?, ?, ?)",
            (protein_g, carbs_g, fat_g, fiber_g),
        )
    row = conn.execute("SELECT * FROM macro_targets WHERE id = 1").fetchone()
    conn.close()
    print_json(MacroTargets.model_validate(dict(row)))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Macro tracker data store")
    parser.add_argument("command", help="Command to run")

    # Ingredient args
    parser.add_argument("--source", help="usda or label")
    parser.add_argument("--payload", help="JSON payload string")
    parser.add_argument("--name", help="Name filter or recipe name")

    # Generic ID / flags
    parser.add_argument("--id", help="Record ID")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="Include unavailable recipes",
    )

    # Recipe args
    parser.add_argument(
        "--ingredients", help="JSON array of {ingredient_id, quantity_g}"
    )
    parser.add_argument("--notes", help="Optional notes")
    parser.add_argument("--grams", type=float, help="Gram amount for serving calc")
    parser.add_argument("--available", help="true or false")

    # Daily log args
    parser.add_argument("--source_type", help="ingredient or recipe")
    parser.add_argument("--source_id", help="ID of ingredient or recipe")
    parser.add_argument("--quantity_g", type=float, help="Quantity in grams")
    parser.add_argument("--meal", help="breakfast, lunch, dinner, or snack")
    parser.add_argument("--date", help="Date YYYY-MM-DD")

    # Targets args
    parser.add_argument("--protein_g", type=float)
    parser.add_argument("--carbs_g", type=float)
    parser.add_argument("--fat_g", type=float)
    parser.add_argument("--fiber_g", type=float)

    args = parser.parse_args()
    cmd = args.command

    if cmd == "create_ingredient_raw":
        create_ingredient_raw(args.source, args.payload)
    elif cmd == "list_ingredients":
        list_ingredients(args.name)
    elif cmd == "get_ingredient":
        get_ingredient(args.id)

    elif cmd == "create_recipe":
        create_recipe(args.name, args.ingredients, args.notes)
    elif cmd == "list_recipes":
        list_recipes(args.name, args.include_all)
    elif cmd == "get_recipe":
        get_recipe(args.id)
    elif cmd == "get_recipe_serving":
        get_recipe_serving(args.id, args.grams)
    elif cmd == "set_recipe_available":
        avail = args.available.lower() == "true"
        set_recipe_available(args.id, avail)
    elif cmd == "delete_recipe":
        delete_recipe(args.id)

    elif cmd == "create_daily_log":
        create_daily_log(
            args.source_type, args.source_id, args.quantity_g, args.meal, args.notes
        )
    elif cmd == "list_daily_logs":
        list_daily_logs(args.date)
    elif cmd == "delete_daily_log":
        delete_daily_log(args.id)

    elif cmd == "get_targets":
        get_targets()
    elif cmd == "upsert_targets":
        upsert_targets(args.protein_g, args.carbs_g, args.fat_g, args.fiber_g)

    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
