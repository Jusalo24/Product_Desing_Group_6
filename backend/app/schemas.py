from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IngredientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: str = Field(default="", max_length=100)


class IngredientRead(IngredientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RecipeBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructions: str = ""
    prep_minutes: int | None = Field(default=None, ge=0)
    servings: int | None = Field(default=None, ge=1)


class RecipeCreate(RecipeBase):
    ingredients: list[IngredientBase] = []


class RecipeRead(RecipeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    ingredients: list[IngredientRead] = []
