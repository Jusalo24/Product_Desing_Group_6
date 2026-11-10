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


class IngredientMatch(BaseModel):
    fineli_id: str = Field(min_length=1, max_length=100)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, pattern="^(g|kg)$")


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
    source: "RecipeSourceRead | None" = None


class RecipeSourceRead(BaseModel):
    provider: str
    external_id: str
    provider_url: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    attribution_text: str
    extra_data: dict = Field(default_factory=dict)
    retrieved_at: datetime


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


class DetailedNutrientTotal(BaseModel):
    code: str
    name: str
    unit: str
    value: float
    group: str | None = None
    per_serving: float | None = None


class NutritionCoverage(BaseModel):
    total_ingredients: int
    included_ingredients: int
    ratio: float


class NutritionIngredientResultRead(BaseModel):
    ingredient_id: int
    ingredient_name: str
    fineli_id: str | None = None
    fineli_name: str | None = None
    quantity_grams: float | None = None
    status: str
    reason: str | None = None
    nutrients: list[DetailedNutrientTotal] = Field(default_factory=list)


class NutritionResponse(BaseModel):
    recipe_id: int
    values: NutritionValues
    source: SourceInfo
    status: str
    calculation_run_id: int | None = None
    per_serving_values: NutritionValues | None = None
    detailed_totals: list["DetailedNutrientTotal"] = Field(default_factory=list)
    coverage: "NutritionCoverage"
    ingredient_results: list["NutritionIngredientResultRead"] = Field(default_factory=list)


class FineliFood(BaseModel):
    id: str
    name: str
    food_type: str | None = None
    process: str | None = None
    ingredient_class: str | None = None
    nutrients_per_100g: NutritionValues
    detailed_nutrients: list["DetailedNutrient"] = Field(default_factory=list)
    units: list["FineliFoodUnitRead"] = Field(default_factory=list)
    source: SourceInfo


class DetailedNutrient(BaseModel):
    code: str
    name: str
    unit: str
    group: str | None = None
    value_per_100g: float


class FineliFoodUnitRead(BaseModel):
    code: str
    name: str
    grams: float


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
