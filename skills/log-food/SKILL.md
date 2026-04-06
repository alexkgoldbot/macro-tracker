---
name: log_food
description: Log what the user ate, resolving to a stored ingredient or recipe and recording macros
metadata: {}
---

# log-food skill

## When to invoke

Invoke this skill when the user reports eating something or asks to log food.

Trigger examples: "I just ate a bowl of oatmeal", "log 200g of chicken breast for lunch", "I had some pasta"

## Flow

1. **Parse the input** — identify:
   - Food item name
   - Quantity (grams if stated, otherwise estimate from description)
   - Meal slot: `breakfast`, `lunch`, `dinner`, or `snack`

2. **Resolve to a stored record** — try to find a matching ingredient:
   ```
   python store.py list_ingredients --name "<food name>"
   ```
   If not found as an ingredient, check recipes (use `--all` since availability doesn't matter for logging):
   ```
   python store.py list_recipes --name "<food name>" --all
   ```

3. **If not found in either** — invoke the `add-ingredient` skill to store it first, then proceed.

4. **Determine quantity in grams** — if the quantity is unclear or vague ("a handful", "a bowl"), estimate a reasonable quantity in grams and record your assumption. If the quantity is genuinely uncertain, ask the user to confirm.

5. **Log the entry** — run:
   ```
   python store.py create_daily_log --source_type <ingredient|recipe> --source_id <id> --quantity_g <g> --meal <meal> --notes "<notes>"
   ```
   Use `--notes` to record any estimation assumptions (e.g. "Estimated 150g from 'a bowl' description").

6. **Show updated totals** — run:
   ```
   python check.py summary --date today
   ```
   Present the updated macro totals and remaining budget for the day to the user.

## Behavioral rules

- If the input could match both a recipe and a standalone ingredient, resolve to whichever matches first; ask the user if ambiguous.
- Vague quantities ("a handful", "a plate") require estimation with a logged assumption in `notes`.
- Always show the updated daily summary after logging so the user can track their progress.

## Output interpretation

`create_daily_log` returns the log entry with calculated macros. `check.py summary` returns the daily totals vs. targets. Present both: confirm what was logged and show remaining macro budget.
