from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared leaf types
# ---------------------------------------------------------------------------


class ValueUnit(BaseModel):
    value: float | None = None
    unit: str | None = None


# ---------------------------------------------------------------------------
# Product info
# ---------------------------------------------------------------------------


class ProductInfo(BaseModel):
    brand: str | None = None
    product_name: str | None = None
    packaging_type: Literal[
        "fresh", "packaged", "frozen", "canned", "bulk", "unknown"
    ] = "unknown"
    preparation_state: Literal[
        "raw", "cooked", "ready_to_eat", "unknown"
    ] = "unknown"
    net_weight: ValueUnit = Field(default_factory=ValueUnit)


# ---------------------------------------------------------------------------
# Nutrition facts
# ---------------------------------------------------------------------------


class PerServing(BaseModel):
    calories: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    total_carbohydrate_g: float | None = None
    dietary_fiber_g: float | None = None
    total_sugars_g: float | None = None
    added_sugars_g: float | None = None
    protein_g: float | None = None


class NutritionFacts(BaseModel):
    serving_size: ValueUnit = Field(default_factory=ValueUnit)
    servings_per_container: float | None = None
    per_serving: PerServing = Field(default_factory=PerServing)


# ---------------------------------------------------------------------------
# Ingredients
# ---------------------------------------------------------------------------


class IngredientItem(BaseModel):
    name: str
    is_sub_ingredient_of: str | None = None


class Ingredients(BaseModel):
    raw_text: str | None = None
    items: list[IngredientItem] | None = None
    contains_allergens: list[str] | None = None
    may_contain_allergens: list[str] | None = None


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class AnalysisResponse(BaseModel):
    product_info: ProductInfo = Field(default_factory=ProductInfo)
    nutrition_facts: NutritionFacts = Field(default_factory=NutritionFacts)
    ingredients: Ingredients = Field(default_factory=Ingredients)


# ---------------------------------------------------------------------------
# Utility responses
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str
