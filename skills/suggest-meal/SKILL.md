---
name: suggest_meal
description: Suggest what to eat next based on remaining macro budget, or simulate eating a specific food
metadata: {}
---

# suggest-meal skill

## When to invoke

Invoke this skill when the user asks for meal suggestions, wants to know what fits their remaining macros, or asks what would happen if they ate a specific food.

Trigger examples: "What should I eat?", "suggest something for dinner", "what fits my remaining macros?", "what would happen if I ate the chicken soup recipe?"

## Flow

### Step 1 — Get remaining budget

Always start by running:
```
python check.py summary --date today
```
This returns the current macro totals, targets, and remaining budget.

If all remaining macros are already at or below zero, tell the user their targets are met and do not suggest more food.

### Step 2 — Simulate a specific food (if user has one in mind)

If the user mentions a specific food or recipe they're considering, resolve it:
- Check ingredients: `python store.py list_ingredients --name "<name>"`
- Check recipes: `python store.py list_recipes --name "<name>" --all`

Then run:
```
python check.py simulate --source_type <ingredient|recipe> --source_id <id> --quantity_g <g>
```

Present to the user:
- Macros that would be added
- Projected remaining budget after eating it

### Step 3 — Suggest from available recipes (if user wants a general suggestion)

1. Get available recipes:
   ```
   python store.py list_recipes
   ```
   (Returns only `available=true` recipes by default.)

2. For each candidate recipe, estimate a reasonable portion size using caloric density:
   - First get the full recipe: `python store.py get_recipe --id <id>`
   - Caloric density (kcal/g) = `(total_protein × 4 + total_carbs × 4 + total_fat × 9) / total_grams`
   - Target calories remaining = `(protein_remaining × 4 + carbs_remaining × 4 + fat_remaining × 9)`
   - Estimated portion = `target_calories_remaining / caloric_density` (in grams)

3. For each candidate, simulate the estimated portion:
   ```
   python check.py simulate --source_type recipe --source_id <id> --quantity_g <estimated_g>
   ```

4. **Filter by dietary restrictions** — before presenting, check `USER.md` at the project root and exclude any options that conflict with the user's restrictions.

5. Present the top suggestions (up to 3) with:
   - Recipe name and proposed portion size
   - Macro contribution (protein, carbs, fat, fiber)
   - Projected remaining budget after eating

### Step 4 — Fallback when no recipes fit

If no available recipes fit the budget or all are filtered by dietary restrictions:
- Use your food knowledge to suggest whole foods or ingredients that would complement the remaining macros.
- Present these as suggestions, not stored records — remind the user they can add them as ingredients if they want to log them.
- Remind the user they can add new recipes with the add-recipe skill.

## Behavioral rules

- Always show the projected remaining budget after any suggestion so the user can make an informed decision.
- If no recipes are available at all, prompt the user to add some and offer general food suggestions.
- Respect all dietary restrictions from `USER.md`. Never suggest food that violates those restrictions.
- If all targets are already met or exceeded, say so explicitly rather than suggesting more food.
