from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IngredientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: str = Field(default="", max_length=100)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, pattern="^(g|kg)$")
    fineli_id: str | None = Field(default=None, max_length=100)


class IngredientRead(IngredientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fineli_name: str | None = None
    conversion_status: str


class RecipeBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructions: str = ""
    prep_minutes: int | None = Field(default=None, ge=0)
    servings: int | None = Field(default=None, ge=1)


class RecipeCreate(RecipeBase):
    ingredients: list[IngredientBase] = []


class RecipeIngredientsUpdate(BaseModel):
    ingredients: list[IngredientBase]


class RecipeRead(RecipeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    ingredients: list[IngredientRead] = []


class SourceInfo(BaseModel):
    provider: str
    source_type: str
    external_id: str
    source_url: str | None = None
    retrieved_at: datetime
    attribution_text: str


class NutritionValues(BaseModel):
    energy_kcal: float | None = None
    energy_kj: float | None = None
    protein_g: float | None = None
    carbohydrates_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    salt_g: float | None = None
    sugars_g: float | None = None
    saturated_fat_g: float | None = None


class NutritionResponse(BaseModel):
    recipe_id: int
    values: NutritionValues
    source: SourceInfo
    status: str
    calculation_run_id: int | None = None


class FineliFood(BaseModel):
    id: str
    name: str
    food_type: str | None = None
    process: str | None = None
    ingredient_class: str | None = None
    nutrients_per_100g: NutritionValues
    source: SourceInfo


class ExternalMeal(BaseModel):
    external_id: str
    name: str
    category: str | None = None
    area: str | None = None
    instructions: str | None = None
    thumbnail_url: str | None = None
    source_url: str | None = None
    youtube_url: str | None = None
    ingredients: list[dict[str, str]] = []
    source: SourceInfo


class ExternalMealList(BaseModel):
    meals: list[ExternalMeal]
    source: SourceInfo
