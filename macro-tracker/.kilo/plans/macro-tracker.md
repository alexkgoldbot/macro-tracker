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
    ├── usda.py     (external HTTP — USDA FoodData Central API)
    ├── store.py    (local — all SQLite reads and writes)
    ├── suggest.py  (pure computation — no I/O)
    └── models.py   (Pydantic models — shared data types)
    │
    ▼
SQLite database (local file)
```

The agent handles conversation. Skills handle discrete tasks. Python modules handle data access, external API calls, and computation. SQLite is the source of truth.

Everything runs locally — there is no HTTP server. Skills call Python functions directly.

> Dietary restrictions are enforced at the skill layer. The data layer is macro-agnostic.

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
3. Call `usda.get_food(fdc_id)` to fetch the full nutrient detail for the chosen item
4. Call `store.create_ingredient_raw()` with the raw response — no transformation; normalization runs immediately
5. Poll `store.get_ingredient()` until `status = ready`

**Behavioral rules**:
- If search returns multiple plausible matches, show the top options and ask the user to confirm.
- If a label scan image is ambiguous, ask the user to clarify before proceeding.

---

### add-recipe

**Purpose**: Create a new recipe from a list of ingredients with quantities.

**Trigger examples**: "Save this as a recipe", "create a recipe called chicken soup with these ingredients"

**Flow**:

1. For each ingredient: check via `store.list_ingredients(name=...)`. If not found, run `add-ingredient` first.
2. Check for a duplicate recipe name via `store.list_recipes(name=...)`. If a match exists, confirm with the user before proceeding.
3. Call `store.create_recipe()` with ingredient IDs and quantities.

**Behavioral rules**:
- Wait for all ingredients to be `ready` before creating the recipe.
- If the user provides weights in non-gram units, convert to grams before submission.

---

### log-food

**Purpose**: Log what the user ate for the day.

**Trigger examples**: "I just ate a bowl of oatmeal", "log 200g of chicken breast for lunch", "I had some pasta"

**Flow**:

1. Parse the user's input to identify food item, quantity, and meal slot.
2. Resolve to an existing ingredient (`store.list_ingredients(name=...)`) or recipe (`store.list_recipes(name=...)`).
3. If not found, run `add-ingredient` first.
4. Determine quantity in grams — ask the user if unclear, or estimate from vague descriptions.
5. Call `store.create_daily_log()` with `source_type`, `source_id`, `quantity_g`, and `meal`.
6. If quantity was estimated, record assumptions in the `notes` field.

**Behavioral rules**:
- Vague quantities ("a handful", "a plate") require estimation with a logged assumption.
- If the input could match either a recipe or a standalone ingredient, resolve to whichever matches first; ask the user if ambiguous.

---

### suggest-meal

**Purpose**: Suggest what to eat next based on remaining macro budget and available recipes.

**Trigger examples**: "What should I eat?", "suggest something for dinner", "what fits my remaining macros?"

**Flow**:

1. Call `store.get_daily_log_summary(date=today)` to retrieve the remaining macro budget.
2. Call `store.list_recipes()` to get all available recipes.
3. Call `store.get_recipe(id)` for each recipe to retrieve its full macro breakdown.
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

| Module       | Purpose                                                                                                                                                                                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `models.py`  | Pydantic models mirroring the data model: `IngredientRaw`, `Ingredient`, `Recipe`, `RecipeIngredient`, `DailyLog`, `DailyLogSummary`, `MacroTargets`. Shared contract between skills and the data layer.             |
| `store.py`   | All SQLite reads and writes. One typed function per logical operation (e.g. `create_ingredient_raw`, `get_recipe`, `list_ingredients`, `create_daily_log`). Accepts and returns Pydantic models. No HTTP involved.   |
| `usda.py`    | Wraps the USDA FoodData Central API. Reads `USDA_API_KEY` from env. Exposes two calls: `search(query)` → list of candidates, and `get_food(fdc_id)` → full nutrient detail. Returns raw response dict, untransformed. |
| `suggest.py` | Preference-agnostic suggestion engine. Given a remaining macro budget and a list of recipes, computes optimal portion sizes and ranks results. Does not apply dietary restrictions — that happens at the skill layer. |

**Design notes**:

- `store.py` replaces both the HTTP server and HTTP client from a traditional client-server design. Since everything is local, there is no network boundary to cross.
- `store.py` handles normalization inline when writing to `ingredients_raw` — it immediately parses the payload and inserts the normalized record into `ingredients`.
- `suggest.py` is purely computational. All dietary restriction filtering happens in the `suggest-meal` skill before recipes are passed here.
- `models.py` is the shared contract between skills and the data layer — field names and types match the database schema exactly.

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

### `store.py` interface

All data access goes through `store.py`. Functions are grouped by domain.

#### Ingredients

| Function                              | Notes                                                                              |
| ------------------------------------- | ---------------------------------------------------------------------------------- |
| `create_ingredient_raw(req) -> Ingredient` | Writes raw payload, runs normalization inline, returns the normalized `Ingredient` |
| `list_ingredients(name=None) -> list[Ingredient]` | Returns `status=ready` records. Optional name substring filter.       |
| `get_ingredient(id) -> Ingredient`    | Returns ingredient by ID including status.                                         |

#### Recipes

| Function                                        | Notes                                                                      |
| ----------------------------------------------- | -------------------------------------------------------------------------- |
| `create_recipe(req) -> Recipe`                  | Creates recipe with ingredient list (ingredient_id + quantity_g each)      |
| `list_recipes(name=None) -> list[Recipe]`       | All recipes, sorted by created_at desc. Optional name substring filter.    |
| `get_recipe(id) -> RecipeDetail`                | Recipe with full ingredient breakdown and computed total macros.            |
| `get_recipe_serving(id, grams) -> RecipeServing` | Macro breakdown scaled to a given gram amount.                             |
| `delete_recipe(id) -> None`                     |                                                                            |

#### Daily logs

| Function                                            | Notes                                                             |
| --------------------------------------------------- | ----------------------------------------------------------------- |
| `create_daily_log(req) -> DailyLog`                 | Computes and stores macros at write time.                         |
| `list_daily_logs(date) -> DailyLogsForDay`          | All entries for a day plus running totals.                        |
| `get_daily_log_summary(date) -> DailyLogSummary`    | Totals vs. targets and remaining macro budget per macro.          |
| `delete_daily_log(id) -> None`                      |                                                                   |

#### Macro targets

| Function                                  | Notes                          |
| ----------------------------------------- | ------------------------------ |
| `get_targets() -> MacroTargets`           |                                |
| `upsert_targets(req) -> MacroTargets`     | Single record, updated in place |

---

## Implementation plan

Build in dependency order: each step is a stable foundation for the next.

### Step 1 — Database (`db.py`)

Use SQLite via the standard `sqlite3` module. On startup, run `CREATE TABLE IF NOT EXISTS` for all six tables in schema order (respecting foreign key dependencies):

1. `macro_targets`
2. `ingredients_raw`
3. `ingredients`
4. `recipes`
5. `recipe_ingredients`
6. `daily_logs`

Enable `PRAGMA foreign_keys = ON`. Expose a `get_connection()` helper that all other modules import.

### Step 2 — Pydantic models (`models.py`)

Define models mirroring every table and API surface. Group into three categories:

**Row models** (match table columns 1:1, used for reading from DB):
- `IngredientRaw`, `Ingredient`, `Recipe`, `RecipeIngredient`, `DailyLog`, `MacroTargets`

**Request models** (used for writing — omit server-set fields like `id`, `created_at`):
- `CreateIngredientRawRequest`, `CreateRecipeRequest`, `CreateDailyLogRequest`, `UpsertTargetsRequest`

**Response models** (shaped for API responses, may include computed fields):
- `RecipeDetail` (recipe + ingredients + computed total macros)
- `RecipeServing` (macro breakdown for a given gram amount)
- `DailyLogSummary` (totals vs. targets, remaining budget per macro)
- `DailyLogsForDay` (list of entries + running totals)

All macro fields are `float`. All IDs are `str` (UUID). Timestamps are `datetime`. Use `model_config = ConfigDict(from_attributes=True)` so models can be built from DB row dicts.

### Step 3 — Data store (`store.py`)

Implement all functions from the `store.py` interface table above. Import `db.py` for connections and `models.py` for types.

Normalization runs inline inside `create_ingredient_raw`:
1. Parse `raw_payload` based on `source` (`usda` or `label`)
2. Extract `name` and per-100g values for protein, carbs, fat, fiber
3. For USDA payloads: locate nutrients by `nutrientId` (protein=1003, fat=1004, carbs=1005, fiber=1079)
4. Insert into `ingredients` with `status = ready` and return the normalized `Ingredient`

Macro calculations in `create_daily_log`: multiply the ingredient's per-100g values by `quantity_g / 100` and store the results on the log record.

### Step 4 — Python modules

**`usda.py`**:
- Reads `USDA_API_KEY` from env (raise a clear error if missing)
- `search(query: str) -> list[dict]` — calls `GET /foods/search`, returns the `foods` array
- `get_food(fdc_id: int) -> dict` — calls `GET /food/{fdcId}`, returns the full response

**`suggest.py`**:
- `suggest(budget: MacroTargets, recipes: list[RecipeDetail]) -> list[dict]`
- For each recipe, compute the portion size in grams that best fits the remaining budget
- Rank by how well the optimal portion hits the budget: prioritize protein first, then fiber, then balance carbs and fat
- Return ranked list of `{recipe, portion_g, projected_macros}`
- Pure computation — no I/O, no dietary filtering

### Step 5 — Skills

Create one Markdown file per skill under `.kilo/command/`. Each describes the skill to the agent: purpose, trigger examples, flow steps, and behavioral rules. Extract directly from the Layer 2 section of this spec:

- `.kilo/command/add-ingredient.md`
- `.kilo/command/add-recipe.md`
- `.kilo/command/log-food.md`
- `.kilo/command/suggest-meal.md`

### Step 6 — AGENTS.md

Create `AGENTS.md` at the project root. Extract content from the "AGENTS.md content for this user" section in Layer 1 of this spec. The dietary restrictions line should read: *"See `USER.md` for this user's dietary restrictions."*

### Step 7 — USER.md

Copy `USER.md.example` to `USER.md` and fill in personal restrictions. `USER.md` is gitignored and stays local.
