from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.integrations.fineli.client import ExternalProviderError, FineliClient

router = APIRouter(prefix="/recipes", tags=["nutrition"])
REQUIRED = ("energy_kcal", "protein_g", "carbohydrates_g", "fat_g")


def _grams(quantity: float, unit: str) -> float:
    return quantity * 1000 if unit == "kg" else quantity


def _source_value(source: dict) -> dict:
    result = dict(source)
    retrieved_at = result.get("retrieved_at")
    if isinstance(retrieved_at, datetime):
        result["retrieved_at"] = retrieved_at.isoformat()
    result.pop("name", None)
    return result


def _get_recipe(recipe_id: int, db: Session) -> models.Recipe:
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe


@router.get("/{recipe_id}/nutrition", response_model=schemas.NutritionResponse)
def get_nutrition(recipe_id: int, db: Session = Depends(get_db)):
    fact = db.scalar(select(models.NutritionFact).where(models.NutritionFact.recipe_id == recipe_id))
    if fact is None:
        _get_recipe(recipe_id, db)
        raise HTTPException(404, "Nutrition has not been calculated")
    run = db.get(models.NutritionCalculationRun, fact.run_id)
    return {
        "recipe_id": recipe_id,
        "values": fact.values,
        "source": fact.source,
        "status": run.status if run else "completed",
        "calculation_run_id": fact.run_id,
    }


@router.post("/{recipe_id}/nutrition/recalculate", response_model=schemas.NutritionResponse)
def recalculate_nutrition(recipe_id: int, db: Session = Depends(get_db)):
    recipe = _get_recipe(recipe_id, db)
    run = models.NutritionCalculationRun(
        recipe_id=recipe_id, status="running", calculation_version="1"
    )
    db.add(run)
    db.flush()
    total = {field: 0.0 for field in schemas.NutritionValues.model_fields}
    sources: list[dict] = []
    if not recipe.ingredients:
        raise HTTPException(422, "Recipe needs at least one ingredient")
    try:
        client = FineliClient()
        for ingredient in recipe.ingredients:
            if not ingredient.fineli_id or ingredient.quantity is None or ingredient.unit not in {"g", "kg"}:
                raise HTTPException(422, "All ingredients need a Fineli match and g/kg quantity")
            food = client.get_food(ingredient.fineli_id)
            values = food["nutrients_per_100g"]
            if any(values.get(field) is None for field in REQUIRED):
                raise HTTPException(422, "A required nutrient is missing from Fineli")
            grams = _grams(float(ingredient.quantity), ingredient.unit)
            db.add(
                models.NutritionCalculationItem(
                    run_id=run.id,
                    ingredient_id=ingredient.id,
                    source_id=food["id"],
                    source_name=food["name"],
                    source_values=values,
                    quantity_grams=grams,
                )
            )
            for field, value in values.items():
                if value is not None:
                    total[field] += float(value) * grams / 100
            sources.append(_source_value(food["source"]))
        client.close()
        run.status = "completed"
        run.is_active = True
        run.created_at = datetime.now(timezone.utc)
        previous = db.scalars(
            select(models.NutritionCalculationRun).where(
                models.NutritionCalculationRun.recipe_id == recipe_id,
                models.NutritionCalculationRun.id != run.id,
                models.NutritionCalculationRun.is_active.is_(True),
            )
        ).all()
        for old_run in previous:
            old_run.is_active = False
        fact = db.scalar(select(models.NutritionFact).where(models.NutritionFact.recipe_id == recipe_id))
        if fact is None:
            fact = models.NutritionFact(recipe_id=recipe_id, run_id=run.id, values=total, source=sources[0])
            db.add(fact)
        else:
            fact.run_id, fact.values, fact.source = run.id, total, sources[0]
        db.commit()
        return {
            "recipe_id": recipe_id,
            "values": total,
            "source": sources[0],
            "status": run.status,
            "calculation_run_id": run.id,
        }
    except HTTPException:
        run.status, run.error_code = "failed", "invalid_ingredient"
        db.rollback()
        raise
    except ExternalProviderError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Fineli unavailable") from exc
