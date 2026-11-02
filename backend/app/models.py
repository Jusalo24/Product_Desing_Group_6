from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
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
