# Macro tracking system — full system spec

_v5 · April 2026_

## Overview

A personal macro tracking system built on three layers:

```
User chat
    │
    ▼
OpenClaw agent  (AGENTS.md — behavioral rules, conversation)
    │
    ▼
Skills          (add-ingredient, add-recipe, log-food, suggest-meal)
    │
    ▼
Python modules  (models.py, client.py, usda.py, suggest.py)
    │
    ▼
SQLite database (local file, no server)
```

The agent handles conversation. Skills handle discrete tasks. Python modules handle API calls, data validation, and computation. SQLite is the source of truth.

> Dietary restrictions are enforced at the skill layer — not the backend. The backend is macro-agnostic.

---

## Layer 1 — Agent (AGENTS.md)

The OpenClaw agent is the user-facing interface. It converses naturally, interprets intent, and delegates to skills. The agent does not call the API directly or manipulate data — it orchestrates skills.

`AGENTS.md` is the file the agent reads on startup. It should contain:

1. **Role** — what the agent is
2. **Behavioral rules** — how the agent should act in conversation and when delegating to skills
3. **Dietary restrictions** — user-specific food restrictions the agent must respect when suggesting meals or logging food

### AGENTS.md content for this user

**Role**: Personal macro tracking assistant.

**Behavioral rules**:

- Stay conversational. Only invoke a skill when the user's intent clearly maps to one.
- Treat fiber as equally important as protein, carbs, and fat. Fiber is not a traditional macro, but it is tracked here intentionally — proactively surface fiber intake and remaining fiber budget the same way you would for any other macro.
- When logging vague inputs ("a bowl of soup", "some chicken"), estimate reasonable quantities and record assumptions in the daily log `notes` field.
- Before creating a recipe, confirm with the user if a matching recipe name already exists.
- When an ingredient's `status` is `pending`, wait/poll before using it in recipes or logs.
- All USDA API responses and label scan data go through the `add-ingredient` skill — the agent never performs normalization directly.

**Dietary restrictions**: Read from `USER.md` at the project root. Apply all restrictions listed there when suggesting or logging food.

---

## Layer 2 — Skills

Skills are discrete, callable units of agent behavior. Each maps to a specific user intent and orchestrates one or more Python module calls.

### add-ingredient

**Purpose**: Look up a single ingredient via the USDA FoodData Central API or from a label scan image, and store it.

**Trigger examples**: "Add chicken breast", "scan this label", "I want to add oat milk to my ingredients"

**Flow**:

1. Call `usda.search(query)` to get a list of candidates (or parse label scan image)
2. Pick the best match from the results, or present the top candidates to the user if the best fit is unclear
3. Call `usda.get_food(fdcId)` to fetch the full nutrient detail for the chosen item
4. Call `client.post_ingredient_raw()` with the raw response — no transformation
5. Poll `client.get_ingredient()` until `status = ready`

**Behavioral rules**:
- If search returns multiple plausible matches, show the top options and ask the user to confirm.
- If a label scan image is ambiguous, ask the user to clarify before proceeding.

---

### add-recipe

**Purpose**: Create a new recipe from a list of ingredients with quantities.

**Trigger examples**: "Save this as a recipe", "create a recipe called chicken soup with these ingredients"

**Flow**:

1. For each ingredient: check via `client.list_ingredients(name=...)`. If not found, run `add-ingredient` first.
2. Check for a duplicate recipe name via `client.list_recipes(name=...)`. If a match exists, confirm with the user before proceeding.
3. Call `client.create_recipe()` with ingredient IDs and quantities.

**Behavioral rules**:
- Wait for all ingredients to be `ready` before creating the recipe.
- If the user provides weights in non-gram units, convert to grams before submission.

---

### log-food

**Purpose**: Log what the user ate for the day.

**Trigger examples**: "I just ate a bowl of oatmeal", "log 200g of chicken breast for lunch", "I had some pasta"

**Flow**:

1. Parse the user's input to identify food item, quantity, and meal slot.
2. Resolve to an existing ingredient (`client.list_ingredients(name=...)`) or recipe (`client.list_recipes(name=...)`).
3. If not found, run `add-ingredient` first.
4. Determine quantity in grams — ask the user if unclear, or estimate from vague descriptions.
5. Call `client.create_daily_log()` with `source_type`, `source_id`, `quantity_g`, and `meal`.
6. If quantity was estimated, record assumptions in the `notes` field.

**Behavioral rules**:
- Vague quantities ("a handful", "a plate") require estimation with a logged assumption.
- If the input could match either a recipe or a standalone ingredient, resolve to whichever matches first; ask the user if ambiguous.

---

### suggest-meal

**Purpose**: Suggest what to eat next based on remaining macro budget and available recipes.

**Trigger examples**: "What should I eat?", "suggest something for dinner", "what fits my remaining macros?"

**Flow**:

1. Call `client.get_daily_log_summary(date=today)` to retrieve the remaining macro budget.
2. Call `client.list_recipes()` to get all available recipes.
3. Call `client.get_recipe(id)` for each recipe to retrieve its full macro breakdown.
4. Filter candidates by the user's dietary restrictions (defined in AGENTS.md) — **this filtering happens here, before calling `suggest.py`**.
5. Pass filtered recipes and remaining macro budget to `suggest.py`.
6. Present top suggestions with portion sizes and their resulting macro contribution.

**Behavioral rules**:
- If no recipes are available, prompt the user to add some.
- If all remaining macros are already met, inform the user rather than suggesting more food.
- If all candidate recipes are filtered out by dietary restrictions, say so and offer to suggest ingredients instead.

---

## Layer 3 — Python modules

Python modules that skills invoke directly as Python functions — no subprocess or shell wrappers. Pydantic models validate all data flowing between the skill layer and the API.

| Module           | Purpose                                                                                                                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `models.py`      | Pydantic models mirroring the data model: `IngredientRaw`, `Ingredient`, `Recipe`, `RecipeIngredient`, `DailyLog`, `DailyLogSummary`, `MacroTargets`. Validates all API request/response data. |
| `client.py`      | `MacroTrackerClient` class with typed methods for every API endpoint. Accepts and returns Pydantic models. Raises typed exceptions on HTTP errors.                                             |
| `usda.py`        | Wraps the USDA FoodData Central API. Reads `USDA_API_KEY` from env. Exposes two calls: `search(query)` → list of candidates, and `get_food(fdcId)` → full nutrient detail. Returns the raw response dict, passed untransformed into `ingredients_raw`. |
| `suggest.py`     | Preference-agnostic suggestion engine. Given a remaining macro budget and a list of recipes, computes optimal portion sizes and ranks results. Does not apply dietary restrictions — that happens at the skill layer. |

**Design notes**:

- `client.py` methods map 1:1 to API endpoints; method signatures use Pydantic models for input and output.
- `suggest.py` is purely computational. All dietary restriction filtering happens in the `suggest-meal` skill before recipes are passed here.
- `models.py` is the shared contract between agent layer and backend — field names and types match the database schema exactly.

---

## Layer 4 — SQLite database

Single local file. No server. No auth. All access is local within the OpenClaw workspace.

### Tracked macros

Four values: `protein`, `carbs`, `fat`, `fiber`. All weights in grams.

Fiber is not a traditional macro, but it is tracked here as a first-class value because it is nutritionally important and easy to neglect. It is treated the same as protein, carbs, and fat throughout the system — stored on every log entry, included in daily targets, and surfaced in summaries.

### Food data source

Use the **USDA FoodData Central API** for macro lookups. Requires a `USDA_API_KEY` from [https://fdc.nal.usda.gov/api-key-signup](https://fdc.nal.usda.gov/api-key-signup). Free with no usage cost; rate limit is 1,000 requests/hour.

Two ingestion paths:

- **Keyword search** — agent calls `GET /foods/search?query=...` to get a list of candidates, picks the best match (or asks the user to confirm), then fetches full nutrient details via `GET /food/{fdcId}`. The raw detail response is passed to the backend untransformed.
- **Label scan** — agent parses a nutrition label image and passes the structured JSON.

In both cases, raw data is written to `ingredients_raw`. The backend normalization service transforms it into `ingredients`. The agent and skills never perform normalization.

### Schema

#### ingredients_raw

Stores the exact response from the USDA API or a label scan. No transformation. Audit trail and source of truth.

| Field       | Type      | Notes                                              |
| ----------- | --------- | -------------------------------------------------- |
| id          | uuid      |                                                    |
| source      | enum      | `usda` or `label`                                  |
| raw_payload | jsonb     | Exact API response or parsed label JSON, untouched |
| created_at  | timestamp |                                                    |

#### ingredients

Normalized, per-100g record derived from `ingredients_raw` by the backend normalization service.

| Field            | Type      | Notes                                                             |
| ---------------- | --------- | ----------------------------------------------------------------- |
| id               | uuid      |                                                                   |
| raw_id           | uuid      | FK → ingredients_raw                                              |
| name             | string    |                                                                   |
| protein_per_100g | float     |                                                                   |
| carbs_per_100g   | float     |                                                                   |
| fat_per_100g     | float     |                                                                   |
| fiber_per_100g   | float     |                                                                   |
| status           | enum      | `pending` or `ready` — set by normalization service on completion |
| created_at       | timestamp |                                                                   |

#### recipes

| Field      | Type      | Notes              |
| ---------- | --------- | ------------------ |
| id         | uuid      |                    |
| name       | string    |                    |
| notes      | string    | Optional free text |
| created_at | timestamp |                    |

#### recipe_ingredients

| Field         | Type  | Notes                                       |
| ------------- | ----- | ------------------------------------------- |
| recipe_id     | uuid  | FK → recipes                                |
| ingredient_id | uuid  | FK → ingredients                            |
| quantity_g    | float | Grams of this ingredient in the full recipe |

#### daily_logs

Macros are calculated at write time and stored on the record.

| Field       | Type      | Notes                                                              |
| ----------- | --------- | ------------------------------------------------------------------ |
| id          | uuid      |                                                                    |
| date        | date      |                                                                    |
| source_type | enum      | `ingredient` or `recipe`                                           |
| source_id   | uuid      | FK → ingredients or recipes                                        |
| quantity_g  | float     |                                                                    |
| protein     | float     | Calculated at log time                                             |
| carbs       | float     | Calculated at log time                                             |
| fat         | float     | Calculated at log time                                             |
| fiber       | float     | Calculated at log time                                             |
| meal        | enum      | `breakfast`, `lunch`, `dinner`, or `snack`                         |
| notes       | string    | Optional — agent stores assumptions here when logging vague inputs |
| logged_at   | timestamp |                                                                    |

#### macro_targets

Single record, updated in place.

| Field     | Type  | Notes        |
| --------- | ----- | ------------ |
| protein_g | float | Daily target |
| carbs_g   | float |              |
| fat_g     | float |              |
| fiber_g   | float |              |

### API endpoints

#### Ingredients

| Method | Path             | Notes                                                                             |
| ------ | ---------------- | --------------------------------------------------------------------------------- |
| POST   | /ingredients/raw | Write raw payload from USDA API or label scan. Triggers normalization service.    |
| GET    | /ingredients     | List/search by name. Returns only `status=ready` records by default.              |
| GET    | /ingredients/:id | Returns ingredient record including status.                                       |

#### Recipes

| Method | Path                 | Notes                                                                                   |
| ------ | -------------------- | --------------------------------------------------------------------------------------- |
| POST   | /recipes             | Create recipe with name and ingredient list (ingredient_id + quantity_g per ingredient) |
| GET    | /recipes             | List all, sorted by created_at desc. Supports name search.                              |
| GET    | /recipes/:id         | Returns recipe with full ingredient breakdown and computed total macros.                |
| GET    | /recipes/:id/serving | Query param: `?grams=100`. Returns macro breakdown for a given gram amount.             |
| DELETE | /recipes/:id         |                                                                                         |

#### Daily logs

| Method | Path                | Notes                                                                                             |
| ------ | ------------------- | ------------------------------------------------------------------------------------------------- |
| POST   | /daily-logs         | Log a food entry. Server computes and stores macros at write time.                                |
| GET    | /daily-logs         | Query param: `?date=YYYY-MM-DD`. Returns all entries for a day plus running totals.               |
| GET    | /daily-logs/summary | Query param: `?date=YYYY-MM-DD`. Returns totals vs. targets and remaining macro budget per macro. |
| DELETE | /daily-logs/:id     | Remove a single entry.                                                                            |

#### Macro targets

| Method | Path     | Notes                                   |
| ------ | -------- | --------------------------------------- |
| GET    | /targets |                                         |
| PUT    | /targets | Upsert — single record updated in place |
