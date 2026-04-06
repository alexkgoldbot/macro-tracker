"""
check.py — Macro budget queries and what-if projections. Read-only.

Usage:
  python check.py summary --date <YYYY-MM-DD|today>
  python check.py simulate --source_type <ingredient|recipe> --source_id <id> --quantity_g <g>
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone

import db
from models import DailyLogSummary, MacroBudget
from store import _compute_macros_for_source, _compute_recipe_detail


def resolve_date(date_str: str) -> str:
    if date_str.lower() == "today":
        return datetime.now(timezone.utc).date().isoformat()
    return date_str


def summary(date_str: str) -> None:
    resolved = resolve_date(date_str)
    conn = db.get_connection()

    rows = conn.execute(
        "SELECT protein, carbs, fat, fiber FROM daily_logs WHERE date = ?",
        (resolved,),
    ).fetchall()
    targets_row = conn.execute("SELECT * FROM macro_targets WHERE id = 1").fetchone()
    conn.close()

    consumed_protein = sum(r["protein"] for r in rows)
    consumed_carbs = sum(r["carbs"] for r in rows)
    consumed_fat = sum(r["fat"] for r in rows)
    consumed_fiber = sum(r["fiber"] for r in rows)

    t_protein = targets_row["protein_g"] if targets_row else 0.0
    t_carbs = targets_row["carbs_g"] if targets_row else 0.0
    t_fat = targets_row["fat_g"] if targets_row else 0.0
    t_fiber = targets_row["fiber_g"] if targets_row else 0.0

    result = DailyLogSummary(
        date=resolved,
        protein=MacroBudget(
            consumed=consumed_protein,
            target=t_protein,
            remaining=t_protein - consumed_protein,
        ),
        carbs=MacroBudget(
            consumed=consumed_carbs, target=t_carbs, remaining=t_carbs - consumed_carbs
        ),
        fat=MacroBudget(
            consumed=consumed_fat, target=t_fat, remaining=t_fat - consumed_fat
        ),
        fiber=MacroBudget(
            consumed=consumed_fiber, target=t_fiber, remaining=t_fiber - consumed_fiber
        ),
    )
    print(json.dumps(result.model_dump()))


def simulate(source_type: str, source_id: str, quantity_g: float) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    conn = db.get_connection()

    # Get today's actual totals
    rows = conn.execute(
        "SELECT protein, carbs, fat, fiber FROM daily_logs WHERE date = ?",
        (today,),
    ).fetchall()
    targets_row = conn.execute("SELECT * FROM macro_targets WHERE id = 1").fetchone()

    consumed_protein = sum(r["protein"] for r in rows)
    consumed_carbs = sum(r["carbs"] for r in rows)
    consumed_fat = sum(r["fat"] for r in rows)
    consumed_fiber = sum(r["fiber"] for r in rows)

    try:
        macros = _compute_macros_for_source(conn, source_type, source_id, quantity_g)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    finally:
        conn.close()

    t_protein = targets_row["protein_g"] if targets_row else 0.0
    t_carbs = targets_row["carbs_g"] if targets_row else 0.0
    t_fat = targets_row["fat_g"] if targets_row else 0.0
    t_fiber = targets_row["fiber_g"] if targets_row else 0.0

    new_protein = consumed_protein + macros["protein"]
    new_carbs = consumed_carbs + macros["carbs"]
    new_fat = consumed_fat + macros["fat"]
    new_fiber = consumed_fiber + macros["fiber"]

    result = {
        "date": today,
        "source_type": source_type,
        "source_id": source_id,
        "quantity_g": quantity_g,
        "macros_added": {
            "protein": macros["protein"],
            "carbs": macros["carbs"],
            "fat": macros["fat"],
            "fiber": macros["fiber"],
        },
        "projected": DailyLogSummary(
            date=today,
            protein=MacroBudget(
                consumed=new_protein,
                target=t_protein,
                remaining=t_protein - new_protein,
            ),
            carbs=MacroBudget(
                consumed=new_carbs, target=t_carbs, remaining=t_carbs - new_carbs
            ),
            fat=MacroBudget(consumed=new_fat, target=t_fat, remaining=t_fat - new_fat),
            fiber=MacroBudget(
                consumed=new_fiber, target=t_fiber, remaining=t_fiber - new_fiber
            ),
        ).model_dump(),
    }
    print(json.dumps(result))


def main() -> None:
    parser = argparse.ArgumentParser(description="Macro budget queries")
    parser.add_argument("command", help="summary or simulate")
    parser.add_argument("--date", help="Date or 'today'")
    parser.add_argument("--source_type", help="ingredient or recipe")
    parser.add_argument("--source_id", help="ID of ingredient or recipe")
    parser.add_argument("--quantity_g", type=float, help="Quantity in grams")
    args = parser.parse_args()

    if args.command == "summary":
        if not args.date:
            print(json.dumps({"error": "--date is required"}))
            sys.exit(1)
        summary(args.date)
    elif args.command == "simulate":
        if not all([args.source_type, args.source_id, args.quantity_g]):
            print(
                json.dumps(
                    {
                        "error": "--source_type, --source_id, --quantity_g are all required"
                    }
                )
            )
            sys.exit(1)
        simulate(args.source_type, args.source_id, args.quantity_g)
    else:
        print(json.dumps({"error": f"Unknown command: {args.command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
