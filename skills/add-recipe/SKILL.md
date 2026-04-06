---
name: add_recipe
description: Create a new recipe from a list of ingredients with quantities
metadata: {}
---

# add-recipe skill

## When to invoke

Invoke this skill when the user wants to save a meal as a recipe or create a named recipe from a list of ingredients.

Trigger examples: "Save this as a recipe", "create a recipe called chicken soup with these ingredients"

## Flow

1. **Resolve ingredients** — for each ingredient in the recipe, run:
   ```
   python store.py list_ingredients --name "<name>"
   ```
   Returns a JSON array of matching ingredients. If none found, invoke the `add-ingredient` skill first to store the ingredient, then continue.

2. **Check for duplicate recipe name** — run:
   ```
   python store.py list_recipes --name "<name>" --all
   ```
   If a match exists, confirm with the user before proceeding (they may want to update the existing recipe or use a different name).

3. **Create the recipe** — run:
   ```
   python store.py create_recipe --name "<name>" --ingredients '<json array>'
   ```
   The ingredients JSON must be an array of objects with `ingredient_id` and `quantity_g`:
   ```json
   [
     {"ingredient_id": "<uuid>", "quantity_g": 200},
     {"ingredient_id": "<uuid>", "quantity_g": 150}
   ]
   ```
   If the user provides weights in non-gram units (oz, cups, etc.), convert to grams before submitting.

4. **Ask about availability** — ask the user: "Is this recipe currently on hand (e.g. you've just made it and it's ready to eat)?" If yes, run:
   ```
   python store.py set_recipe_available --id <id> --available true
   ```

## Behavioral rules

- New recipes default to `available=false`. Always ask after creating.
- If the user provides non-gram weights, convert to grams before submission.

## Output interpretation

`create_recipe` returns a `RecipeDetail` JSON object with the recipe's id, name, total macros, and ingredient breakdown. Confirm success to the user and show the total macros for the full recipe.
