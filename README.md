# macro-tracker

A personal macro tracking assistant built on KiloClaw. The agent converses naturally, logs food, manages recipes, and suggests meals based on your remaining daily macro budget.

## What it tracks

Protein, carbs, fat, and fiber — all in grams. Fiber is treated as a first-class macro alongside the traditional three.

## Architecture

```
User chat
    │
    ▼
OpenClaw agent  (AGENTS.md)
    │
    ▼
Skills          (add-ingredient, add-recipe, log-food, suggest-meal)
    │
    ▼
Python modules  (models.py, client.py, usda.py, suggest.py)
    │
    ▼
SQLite database (local file)
```

See [`.kilo/plans/macro-tracker.md`](.kilo/plans/macro-tracker.md) for the full system spec.

## Setup

1. **API key** — get a free USDA FoodData Central API key at [https://fdc.nal.usda.gov/api-key-signup](https://fdc.nal.usda.gov/api-key-signup)
2. **Environment** — copy `.env.example` to `.env` and add your key:
   ```
   USDA_API_KEY=your_key_here
   ```
3. **User preferences** — copy `USER.md.example` to `USER.md` and set your dietary restrictions

## Skills

| Skill            | Trigger examples                                       |
|------------------|--------------------------------------------------------|
| `add-ingredient` | "Add chicken breast", "scan this label"                |
| `add-recipe`     | "Save this as a recipe called chicken soup"            |
| `log-food`       | "I just had 200g of oatmeal for breakfast"             |
| `suggest-meal`   | "What should I eat?", "what fits my remaining macros?" |
