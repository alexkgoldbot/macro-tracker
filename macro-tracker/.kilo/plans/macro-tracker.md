# Macro tracking system — full system spec

_v6 · April 2026_

## Overview

A personal macro tracking system built on three layers:

```
User chat
    │
    ▼
OpenClaw agent  (AGENTS.md — behavioral rules, conversation)
    │
    ▼
Skills          (skills/add-ingredient/, skills/add-recipe/, skills/log-food/, skills/suggest-meal/)
    │  each skill is a SKILL.md that instructs the agent to run Python via the exec tool
    │
    ├── usda.py    (external HTTP — USDA FoodData Central API)
    ├── store.py   (local — all SQLite reads and writes)
    ├── check.py   (local — macro budget queries and what-if projections)
    └── models.py  (Pydantic models — shared data types)
    │
    ▼
SQLite database (local file)
```

The agent handles conversation. Skills are `SKILL.md` files that instruct the agent to invoke Python modules via the `exec` tool. Python modules handle data access, external API calls, and computation. SQLite is the source of truth.

Everything runs locally — there is no HTTP server.

> Dietary restrictions are enforced at the skill layer. The data layer is macro-agnostic.

---

## Layer 1 — Agent (AGENTS.md)

The OpenClaw agent is the user-facing interface. It converses naturally, interprets intent, and delegates to skills. The agent does not call Python directly or manipulate data outside of skills.

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
- All USDA API responses and label scan data go through the `add-ingredient` skill — the agent never performs normalization directly.

**Dietary restrictions**: Read from `USER.md` at the project root. Apply all restrictions listed there when suggesting or logging food.

---

## Layer 2 — Skills

Skills live under `skills/<skill-name>/SKILL.md` in the workspace root. Each `SKILL.md` contains YAML frontmatter (`name`, `description`) and Markdown instructions that tell the agent:

- When to invoke the skill
- Which Python script to run via the `exec` tool
- How to interpret the output and respond to the user

The agent invokes Python via `exec`: e.g. `python usda.py search "chicken breast"`. Scripts print JSON to stdout; the agent reads, interprets, and continues the conversation.

### add-ingredient

**File**: `skills/add-ingredient/SKILL.md`

**Purpose**: Store a new ingredient from a USDA search or a nutrition label image.

**Trigger examples**: "Add chicken breast", "scan this label", "I want to add oat milk to my ingredients"

**Two pathways**:

**Path A — Label scan** (user provides a nutrition label image):
1. The agent reads the label image using its vision capability and extracts: name, serving size, and macro values (protein, carbs, fat, fiber) per serving
2. The agent converts extracted values to per-100g and constructs a label JSON payload
3. Run `python store.py create_ingredient_raw --source label --payload '<json>'`
4. Confirm success to the user

**Path B — USDA keyword search** (no label):
1. Run `python usda.py search "<ingredient name>"` — returns a list of candidates with fdcId, name, and food type
2. Pick the best match or show the top options and ask the user to confirm
3. Run `python usda.py get_food <fdcId>` — returns full nutrient detail
4. Run `python store.py create_ingredient_raw --source usda --payload '<json>'`
5. Confirm success to the user

**Behavioral rules**:
- For label scans, if the image is ambiguous or key values are missing, ask the user to clarify before storing.
- For USDA searches, branded foods and Foundation foods may structure nutrient data differently — the normalization in `store.py` handles both; the skill just passes the raw response.
- If multiple USDA candidates look equally plausible, present the top 3 with name and food type and ask the user to pick.

---

### add-recipe

**File**: `skills/add-recipe/SKILL.md`

**Purpose**: Create a new recipe from a list of ingredients with quantities.

**Trigger examples**: "Save this as a recipe", "create a recipe called chicken soup with these ingredients"

**Flow**:

1. For each ingredient: run `python store.py list_ingredients --name "<name>"`. If not found, run `add-ingredient` first.
2. Check for a duplicate recipe name: run `python store.py list_recipes --name "<name>"`. If a match exists, confirm with the user before proceeding.
3. Run `python store.py create_recipe --name "<name>" --ingredients '<json array of {ingredient_id, quantity_g}>'`

**Behavioral rules**:
- If the user provides weights in non-gram units, convert to grams before submission.

---

### log-food

**File**: `skills/log-food/SKILL.md`

**Purpose**: Log what the user ate for the day.

**Trigger examples**: "I just ate a bowl of oatmeal", "log 200g of chicken breast for lunch", "I had some pasta"

**Flow**:

1. Parse the user's input to identify food item, quantity, and meal slot.
2. Resolve to an existing ingredient (`python store.py list_ingredients --name "..."`) or recipe (`python store.py list_recipes --name "..."`).
3. If not found, run `add-ingredient` first.
4. Determine quantity in grams — ask the user if unclear, or estimate from vague descriptions.
5. Run `python store.py create_daily_log --source_type <ingredient|recipe> --source_id <id> --quantity_g <g> --meal <meal> --notes "<notes>"`
6. Run `python check.py summary --date today` and show the updated macro totals.

**Behavioral rules**:
- Vague quantities ("a handful", "a plate") require estimation with a logged assumption in `notes`.
- If the input could match either a recipe or a standalone ingredient, resolve to whichever matches first; ask the user if ambiguous.

---

### suggest-meal

**File**: `skills/suggest-meal/SKILL.md`

**Purpose**: Help the user decide what to eat next based on their remaining macro budget.

**Trigger examples**: "What should I eat?", "suggest something for dinner", "what fits my remaining macros?", "what would happen if I ate the chicken soup recipe?"

**Flow**:

1. Run `python check.py summary --date today` to get the remaining macro budget.
2. If the user has a specific food or recipe in mind, run `python check.py simulate --source_type <ingredient|recipe> --source_id <id> --quantity_g <g>` to show what macros would remain after eating it.
3. If the user wants a suggestion, retrieve available recipes with `python store.py list_recipes`, then run simulate on the most promising candidates.
4. Filter candidates by the user's dietary restrictions (from `USER.md`) before presenting options.
5. Present suggestions with: proposed portion size, macro contribution, and projected remaining budget after eating.

**Behavioral rules**:
- If no recipes are available, prompt the user to add some.
- If all remaining macros are already met, say so rather than suggesting more food.
- If all candidates are filtered out by dietary restrictions, say so and offer to suggest standalone ingredients instead.
- Always show the projected remaining budget after a suggestion so the user can make an informed decision.

---

## Layer 3 — Python modules

Python modules live at the workspace root alongside the `skills/` directory. Skills invoke them via `exec` (`python <module>.py <command> <args>`). All modules use Pydantic models internally and print JSON to stdout.

| Module      | Purpose                                                                                                                                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `models.py` | Pydantic models mirroring the data model: `IngredientRaw`, `Ingredient`, `Recipe`, `RecipeIngredient`, `DailyLog`, `DailyLogSummary`, `MacroTargets`. Shared contract between skills and the data layer. |
| `store.py`  | All SQLite reads and writes. Invoked as a CLI (`python store.py <command> <args>`). Accepts args, validates with Pydantic, prints JSON result. Handles normalization inline on ingredient_raw writes. |
| `usda.py`   | Wraps the USDA FoodData Central API. Reads `USDA_API_KEY` from env. CLI: `search <query>` and `get_food <fdc_id>`. Prints raw response JSON — no transformation.                                    |
| `check.py`  | Macro budget queries and what-if projections. No writes. CLI: `summary --date <date>` and `simulate --source_type --source_id --quantity_g`.                                                        |

**Design notes**:

- All modules are invoked as CLI scripts via `exec`. Each command prints a JSON result to stdout. The agent reads and interprets the output.
- `store.py` handles normalization inline when writing to `ingredients_raw` — it immediately parses the payload and inserts the normalized record into `ingredients`.
- `check.py` is read-only. `simulate` computes what macros would remain after a hypothetical log entry without writing anything to the database.
- `models.py` is the shared contract — field names and types match the database schema exactly.

---

## Layer 4 — SQLite database

Single local file. No server. No auth. All access is local within the OpenClaw workspace.

### Tracked macros

Four values: `protein`, `carbs`, `fat`, `fiber`. All weights in grams.

Fiber is not a traditional macro, but it is tracked here as a first-class value because it is nutritionally important and easy to neglect. It is treated the same as protein, carbs, and fat throughout the system — stored on every log entry, included in daily targets, and surfaced in summaries.

### Food data source

Use the **USDA FoodData Central API** for macro lookups. Requires a `USDA_API_KEY` from [https://fdc.nal.usda.gov/api-key-signup](https://fdc.nal.usda.gov/api-key-signup). Free with no usage cost; rate limit is 1,000 requests/hour.

Two ingestion paths:

- **Label scan** — the agent reads the nutrition label image directly using its vision capability, extracts macro values, and constructs a structured JSON payload to pass to `store.py`. No external API call needed.
- **Keyword search** — `usda.py search` returns candidates; the agent picks one and calls `usda.py get_food` to fetch full nutrient detail. The raw response is passed to `store.py` untransformed.

In both cases, raw data is written to `ingredients_raw`. Normalization runs inline in `store.py` and writes the per-100g record to `ingredients`.

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

Normalized, per-100g record derived from `ingredients_raw` by the normalization step in `store.py`.

| Field            | Type      | Notes                            |
| ---------------- | --------- | -------------------------------- |
| id               | uuid      |                                  |
| raw_id           | uuid      | FK → ingredients_raw             |
| name             | string    |                                  |
| protein_per_100g | float     |                                  |
| carbs_per_100g   | float     |                                  |
| fat_per_100g     | float     |                                  |
| fiber_per_100g   | float     |                                  |
| created_at       | timestamp |                                  |

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

### `store.py` CLI interface

All data writes and reads go through `store.py`. Each command prints a JSON result to stdout.

#### Ingredients

| Command                                                                 | Output                                                                             |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `store.py create_ingredient_raw --source <usda\|label> --payload '<json>'` | Writes raw payload, runs normalization inline, returns the normalized `Ingredient` |
| `store.py list_ingredients [--name <substr>]`                           | Returns `ready` ingredient records. Optional name substring filter.                |
| `store.py get_ingredient --id <id>`                                     | Returns ingredient by ID.                                                          |

#### Recipes

| Command                                                                              | Output                                                              |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `store.py create_recipe --name <name> --ingredients '<json>'`                        | Creates recipe; ingredients JSON is array of `{ingredient_id, quantity_g}` |
| `store.py list_recipes [--name <substr>]`                                            | All recipes, sorted by created_at desc. Optional name filter.       |
| `store.py get_recipe --id <id>`                                                      | Recipe with full ingredient breakdown and computed total macros.    |
| `store.py get_recipe_serving --id <id> --grams <g>`                                 | Macro breakdown scaled to a given gram amount.                      |
| `store.py delete_recipe --id <id>`                                                   |                                                                     |

#### Daily logs

| Command                                                                                              | Output                                                   |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `store.py create_daily_log --source_type <type> --source_id <id> --quantity_g <g> --meal <meal> [--notes '<text>']` | Computes and stores macros at write time. |
| `store.py list_daily_logs --date <YYYY-MM-DD>`                                                       | All entries for a day plus running totals.               |
| `store.py delete_daily_log --id <id>`                                                                |                                                          |

#### Macro targets

| Command                                                              | Notes                           |
| -------------------------------------------------------------------- | ------------------------------- |
| `store.py get_targets`                                               |                                 |
| `store.py upsert_targets --protein_g <g> --carbs_g <g> --fat_g <g> --fiber_g <g>` | Single record, updated in place |

### `check.py` CLI interface

Read-only. No writes to the database.

| Command                                                                                      | Output                                                                                     |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `check.py summary --date <YYYY-MM-DD\|today>`                                                | Totals consumed, targets, and remaining budget per macro for the day.                      |
| `check.py simulate --source_type <ingredient\|recipe> --source_id <id> --quantity_g <g>`   | What macros would remain after eating this, without writing anything. |

---

## Implementation plan

Build in dependency order: each step is a stable foundation for the next.

### Step 1 — Database (`db.py`)

Use SQLite via the standard `sqlite3` module. On startup, run `CREATE TABLE IF NOT EXISTS` for all tables in schema order (respecting foreign key dependencies):

1. `macro_targets`
2. `ingredients_raw`
3. `ingredients`
4. `recipes`
5. `recipe_ingredients`
6. `daily_logs`

Enable `PRAGMA foreign_keys = ON`. Set `row_factory = sqlite3.Row` on every connection so rows support attribute access. Expose a `get_connection()` helper that all other modules import.

### Step 2 — Pydantic models (`models.py`)

Define models mirroring every table and CLI surface. Group into three categories:

**Row models** (match table columns 1:1, used for reading from DB):
- `IngredientRaw`, `Ingredient`, `Recipe`, `RecipeIngredient`, `DailyLog`, `MacroTargets`

**Request models** (used for writing — omit server-set fields like `id`, `created_at`):
- `CreateIngredientRawRequest`, `CreateRecipeRequest`, `CreateDailyLogRequest`, `UpsertTargetsRequest`

**Response models** (may include computed fields):
- `RecipeDetail` (recipe + ingredients + computed total macros)
- `RecipeServing` (macro breakdown for a given gram amount)
- `DailyLogSummary` (totals vs. targets, remaining budget per macro)
- `DailyLogsForDay` (list of entries + running totals)

All macro fields are `float`. All IDs are `str` (UUID). Timestamps are `datetime`. Use `model_config = ConfigDict(from_attributes=True)` — works because `db.py` sets `row_factory = sqlite3.Row`.

### Step 3 — Data store (`store.py`)

Implement all commands from the `store.py` CLI interface above. Use `argparse` (or `click`) for the CLI layer. Import `db.py` for connections and `models.py` for types. Each command validates input with Pydantic and prints a JSON result to stdout.

Normalization runs inline inside `create_ingredient_raw`:
1. Parse `raw_payload` based on `source` (`usda` or `label`)
2. Extract `name` and per-100g values for protein, carbs, fat, fiber
3. For USDA payloads: check `foodNutrients` array for nutrientId values (protein=1003, fat=1004, carbs=1005, fiber=1079). For Branded foods, also check `labelNutrients` as a fallback if `foodNutrients` is sparse.
4. For label payloads: expect keys `name`, `protein_per_100g`, `carbs_per_100g`, `fat_per_100g`, `fiber_per_100g` (the agent normalizes to per-100g before passing)
5. Insert into `ingredients` and return the normalized record

Macro calculations in `create_daily_log`: look up the source ingredient or recipe, multiply per-100g values by `quantity_g / 100`, and store on the log record.

### Step 4 — USDA module (`usda.py`)

- Reads `USDA_API_KEY` from env; raises a clear error if missing
- CLI: `python usda.py search "<query>"` — calls `GET /foods/search`, prints `foods` array as JSON
- CLI: `python usda.py get_food <fdc_id>` — calls `GET /food/{fdcId}`, prints full response as JSON

### Step 5 — Check module (`check.py`)

- CLI: `python check.py summary --date <YYYY-MM-DD|today>` — reads `daily_logs` and `macro_targets`, computes totals and remaining budget, prints `DailyLogSummary` as JSON
- CLI: `python check.py simulate --source_type <type> --source_id <id> --quantity_g <g>` — fetches the ingredient or recipe macros, computes what would be logged, adds to today's actual totals, returns projected remaining budget. No writes.

### Step 6 — Skills

Create one directory per skill under `skills/`. Each contains a `SKILL.md` with YAML frontmatter and instructions extracted from the Layer 2 section of this spec:

```
skills/
  add-ingredient/SKILL.md
  add-recipe/SKILL.md
  log-food/SKILL.md
  suggest-meal/SKILL.md
```

Each `SKILL.md` frontmatter:
```yaml
---
name: add_ingredient
description: Look up an ingredient via USDA search or nutrition label scan and store it
metadata: {"openclaw": {"requires": {"env": ["USDA_API_KEY"]}}}
---
```

Instructions in the body tell the agent exactly which `exec` commands to run and in what order, matching the flows in Layer 2.

### Step 7 — AGENTS.md

Create `AGENTS.md` at the project root. Extract content from the "AGENTS.md content for this user" section in Layer 1 of this spec. The dietary restrictions line should read: *"See `USER.md` for this user's dietary restrictions."*

### Step 8 — USER.md

Copy `USER.md.example` to `USER.md` and fill in personal restrictions. `USER.md` is gitignored and stays local.
