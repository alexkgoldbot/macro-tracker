"""
models.py — Pydantic models for the macro tracker system.

Three groups:
  - Row models: mirror table columns 1:1, used when reading from DB
  - Request models: used for writes (omit server-set fields like id, created_at)
  - Response models: may include computed fields
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Row models
# ---------------------------------------------------------------------------


class IngredientRaw(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str  # 'usda' | 'label'
    raw_payload: str  # JSON string
    created_at: str


class Ingredient(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    raw_id: str
    name: str
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    fiber_per_100g: float
    created_at: str


class Recipe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    notes: Optional[str] = None
    available: bool
    created_at: str


class RecipeIngredient(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipe_id: str
    ingredient_id: str
    quantity_g: float


class DailyLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: str
    source_type: str  # 'ingredient' | 'recipe'
    source_id: str
    quantity_g: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    meal: str  # 'breakfast' | 'lunch' | 'dinner' | 'snack'
    notes: Optional[str] = None
    logged_at: str


class MacroTargets(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateIngredientRawRequest(BaseModel):
    source: str  # 'usda' | 'label'
    payload: str  # raw JSON string


class IngredientRef(BaseModel):
    ingredient_id: str
    quantity_g: float


class CreateRecipeRequest(BaseModel):
    name: str
    ingredients: List[IngredientRef]
    notes: Optional[str] = None


class CreateDailyLogRequest(BaseModel):
    source_type: str
    source_id: str
    quantity_g: float
    meal: str
    notes: Optional[str] = None


class UpsertTargetsRequest(BaseModel):
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RecipeIngredientDetail(BaseModel):
    ingredient_id: str
    name: str
    quantity_g: float
    protein: float
    carbs: float
    fat: float
    fiber: float


class RecipeDetail(BaseModel):
    id: str
    name: str
    notes: Optional[str] = None
    available: bool
    created_at: str
    ingredients: List[RecipeIngredientDetail]
    total_protein: float
    total_carbs: float
    total_fat: float
    total_fiber: float
    total_grams: float


class RecipeServing(BaseModel):
    recipe_id: str
    grams: float
    protein: float
    carbs: float
    fat: float
    fiber: float


class MacroBudget(BaseModel):
    consumed: float
    target: float
    remaining: float


class DailyLogSummary(BaseModel):
    date: str
    protein: MacroBudget
    carbs: MacroBudget
    fat: MacroBudget
    fiber: MacroBudget


class DailyLogsForDay(BaseModel):
    date: str
    entries: List[DailyLog]
    total_protein: float
    total_carbs: float
    total_fat: float
    total_fiber: float
