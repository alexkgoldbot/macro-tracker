---
name: add_ingredient
description: Look up an ingredient via USDA search or nutrition label scan and store it
metadata: {"openclaw": {"requires": {"env": ["USDA_API_KEY"]}}}
---

# add-ingredient skill

## When to invoke

Invoke this skill when the user wants to add a new ingredient, mentions scanning a nutrition label, or references a food item that does not yet exist in the database.

Trigger examples: "Add chicken breast", "scan this label", "I want to add oat milk to my ingredients"

## Two pathways

### Path A — Label scan (user provides a nutrition label image)

1. Use your vision capability to read the label image and extract:
   - Product name
   - Serving size in grams
   - Macro values per serving: protein, carbs, fat, fiber

2. Convert each macro to per-100g:
   `value_per_100g = (value_per_serving / serving_size_g) * 100`

3. Construct the canonical label payload and run:
   ```
   python store.py create_ingredient_raw --source label --payload '<json>'
   ```
   The payload must have exactly this shape:
   ```json
   {
     "name": "Product name from label",
     "serving_size_g": 40,
     "protein_per_100g": 12.5,
     "carbs_per_100g": 55.0,
     "fat_per_100g": 8.0,
     "fiber_per_100g": 3.0
   }
   ```

4. Confirm success to the user, including the stored per-100g macro values.

If the label image is ambiguous or key values are missing, ask the user to clarify before storing.

### Path B — USDA keyword search (no label provided)

1. Run:
   ```
   python usda.py search "<ingredient name>"
   ```
   Returns a JSON array of candidates, each with fdcId, description, and food type.

2. Pick the best match. If multiple candidates look equally plausible, present the top 3 (name and food type) and ask the user to pick.

3. Run:
   ```
   python usda.py get_food <fdcId>
   ```
   Returns full nutrient detail.

4. Run:
   ```
   python store.py create_ingredient_raw --source usda --payload '<json>'
   ```
   Pass the full raw response from step 3 as the payload. Do not transform it.

5. Confirm success to the user, including the stored name and per-100g macro values.

Note: branded foods and Foundation foods may structure nutrient data differently — normalization is handled by store.py. Just pass the raw response.

## Output interpretation

`store.py create_ingredient_raw` returns the normalized `Ingredient` record as JSON:
```json
{
  "id": "<uuid>",
  "raw_id": "<uuid>",
  "name": "Chicken Breast",
  "protein_per_100g": 31.0,
  "carbs_per_100g": 0.0,
  "fat_per_100g": 3.6,
  "fiber_per_100g": 0.0,
  "created_at": "..."
}
```

Tell the user the ingredient was saved and show the key macro values per 100g.
