from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ingredients: Mapped[list["Ingredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    source: Mapped["RecipeSource | None"] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", uselist=False
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[str] = mapped_column(String(100), default="")
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fineli_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    fineli_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conversion_status: Mapped[str] = mapped_column(
        String(30), default="unmatched", server_default="unmatched"
    )

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class NutritionCalculationRun(Base):
    __tablename__ = "nutrition_calculation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    calculation_version: Mapped[str] = mapped_column(String(30), default="1")
    is_active: Mapped[bool] = mapped_column(default=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NutritionCalculationItem(Base):
    __tablename__ = "nutrition_calculation_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("nutrition_calculation_runs.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    source_id: Mapped[str] = mapped_column(String(100))
    source_name: Mapped[str] = mapped_column(String(200))
    source_values: Mapped[dict] = mapped_column(JSON)
    quantity_grams: Mapped[float] = mapped_column(Numeric(12, 3))


class NutritionIngredientResult(Base):
    __tablename__ = "nutrition_ingredient_results"
    __table_args__ = (
        UniqueConstraint("run_id", "ingredient_id", name="uq_nutrition_result_run_ingredient"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("nutrition_calculation_runs.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity_grams: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    nutrient_contributions: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NutritionFact(Base):
    __tablename__ = "nutrition_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), unique=True
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("nutrition_calculation_runs.id"))
    values: Mapped[dict] = mapped_column(JSON)
    source: Mapped[dict] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExternalCacheEntry(Base):
    __tablename__ = "external_cache_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    cache_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    response: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FineliFood(Base):
    """One Fineli food, nutrients per 100 g. Filled by app.scripts.import_fineli."""

    __tablename__ = "fineli_foods"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # Fineli FOODID
    name_fi: Mapped[str] = mapped_column(String(300), index=True)
    name_en: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    food_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    process: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ingredient_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    energy_kj: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbohydrates_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    salt_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugars_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturated_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)


class FineliComponent(Base):
    """Fineli nutrient/component code and its display metadata."""

    __tablename__ = "fineli_components"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(30))
    group_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FineliFoodNutrient(Base):
    """One nutrient value in the Fineli dataset's unit per 100 g of food."""

    __tablename__ = "fineli_food_nutrients"

    food_id: Mapped[str] = mapped_column(
        ForeignKey("fineli_foods.id", ondelete="CASCADE"), primary_key=True
    )
    component_code: Mapped[str] = mapped_column(
        ForeignKey("fineli_components.code", ondelete="CASCADE"), primary_key=True
    )
    value_per_100g: Mapped[float] = mapped_column(Float)


class FineliFoodUnit(Base):
    """Grams per household unit (tbsp, piece, ...) for a food."""

    __tablename__ = "fineli_food_units"

    food_id: Mapped[str] = mapped_column(
        ForeignKey("fineli_foods.id", ondelete="CASCADE"), primary_key=True
    )
    unit_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    unit_name: Mapped[str] = mapped_column(String(100))
    grams: Mapped[float] = mapped_column(Float)


class RecipeSource(Base):
    """External recipe provenance; source IDs are unique per provider."""

    __tablename__ = "recipe_sources"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_recipe_source_provider_external_id"),
        UniqueConstraint("recipe_id", name="uq_recipe_source_recipe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(100))
    provider_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    attribution_text: Mapped[str] = mapped_column(Text)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    recipe: Mapped[Recipe] = relationship(back_populates="source")


class IngredientMapping(Base):
    """Curated or LLM-assisted mapping from normalized TheMealDB ingredient names to Fineli."""

    __tablename__ = "ingredient_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    mealdb_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    raw_name: Mapped[str] = mapped_column(String(200))
    fineli_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    search_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    default_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(20), default="medium", server_default="medium"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
