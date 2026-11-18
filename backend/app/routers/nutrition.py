from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound
from app.integrations.fineli.measure import convert_measure_to_grams

router = APIRouter(prefix="/recipes", tags=["nutrition"])
NUTRIENT_FIELDS = tuple(schemas.NutritionValues.model_fields)


def _grams(quantity: float, unit: str) -> float:
    return quantity * 1000 if unit == "kg" else quantity


def _source_value(source: dict[str, Any]) -> dict[str, Any]:
    result = dict(source)
    retrieved_at = result.get("retrieved_at")
    if isinstance(retrieved_at, datetime):
        result["retrieved_at"] = retrieved_at.isoformat()
    result.pop("name", None)
    return result


def _default_source() -> dict[str, Any]:
    return {
        "provider": "Fineli",
        "source_type": "dataset",
        "external_id": "20.0",
        "source_url": "https://fineli.fi/fineli/en/open-data",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "attribution_text": (
            "Source: Fineli, Finnish Institute for Health and Welfare (THL), "
            "release 20.0, CC BY 4.0"
        ),
    }


def _get_recipe(recipe_id: int, db: Session) -> models.Recipe:
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe


def _ingredient_results(
    run_id: int, db: Session
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(models.NutritionIngredientResult, models.Ingredient.name)
        .join(
            models.Ingredient,
            models.Ingredient.id == models.NutritionIngredientResult.ingredient_id,
        )
        .where(models.NutritionIngredientResult.run_id == run_id)
        .order_by(models.NutritionIngredientResult.id)
    ).all()
    return [
        {
            "ingredient_id": result.ingredient_id,
            "ingredient_name": ingredient_name,
            "fineli_id": result.source_id,
            "fineli_name": result.source_name,
            "quantity_grams": (
                float(result.quantity_grams)
                if result.quantity_grams is not None
                else None
            ),
            "status": result.status,
            "reason": result.reason,
            "nutrients": result.nutrient_contributions or [],
        }
        for result, ingredient_name in rows
    ]


def _response(
    recipe: models.Recipe,
    run: models.NutritionCalculationRun,
    fact: models.NutritionFact,
    db: Session,
) -> dict[str, Any]:
    ingredient_results = _ingredient_results(run.id, db)
    detailed: dict[tuple[str, str], dict[str, Any]] = {}
    for result in ingredient_results:
        for nutrient in result["nutrients"]:
            key = (nutrient["code"], nutrient["unit"])
            total = detailed.setdefault(
                key,
                {
                    "code": nutrient["code"],
                    "name": nutrient["name"],
                    "unit": nutrient["unit"],
                    "group": nutrient.get("group"),
                    "value": 0.0,
                },
            )
            total["value"] += float(nutrient["value"])
    servings = recipe.servings
    detailed_totals = [
        {
            **nutrient,
            "per_serving": nutrient["value"] / servings if servings else None,
        }
        for nutrient in sorted(detailed.values(), key=lambda item: (item["code"], item["unit"]))
    ]
    per_serving_values = (
        {
            field: value / servings if value is not None else None
            for field, value in fact.values.items()
        }
        if servings
        else None
    )
    included = sum(result["status"] == "included" for result in ingredient_results)
    count = len(ingredient_results)
    return {
        "recipe_id": recipe.id,
        "values": fact.values,
        "source": fact.source,
        "status": run.status,
        "calculation_run_id": run.id,
        "per_serving_values": per_serving_values,
        "detailed_totals": detailed_totals,
        "coverage": {
            "total_ingredients": count,
            "included_ingredients": included,
            "ratio": included / count if count else 0,
        },
        "ingredient_results": ingredient_results,
    }


@router.get("/{recipe_id}/nutrition", response_model=schemas.NutritionResponse)
def get_nutrition(recipe_id: int, db: Session = Depends(get_db)):
    fact = db.scalar(
        select(models.NutritionFact).where(models.NutritionFact.recipe_id == recipe_id)
    )
    if fact is None:
        _get_recipe(recipe_id, db)
        raise HTTPException(404, "Nutrition has not been calculated")
    recipe = _get_recipe(recipe_id, db)
    run = db.get(models.NutritionCalculationRun, fact.run_id)
    if run is None:
        raise HTTPException(500, "Nutrition calculation history is missing")
    return _response(recipe, run, fact, db)


@router.post(
    "/{recipe_id}/nutrition/recalculate", response_model=schemas.NutritionResponse
)
def recalculate_nutrition(recipe_id: int, db: Session = Depends(get_db)):
    recipe = _get_recipe(recipe_id, db)
    if not recipe.ingredients:
        raise HTTPException(422, "Recipe needs at least one ingredient")
    run = models.NutritionCalculationRun(
        recipe_id=recipe_id, status="running", calculation_version="2"
    )
    db.add(run)
    db.flush()
    totals: dict[str, float | None] = {field: None for field in NUTRIENT_FIELDS}
    detailed_totals: dict[tuple[str, str], dict[str, Any]] = {}
    ingredient_rows: list[models.NutritionIngredientResult] = []
    sources: list[dict[str, Any]] = []
    client = get_fineli_client(db)
    try:
        for ingredient in recipe.ingredients:
            is_negligible = ingredient.conversion_status == "negligible"
            if not is_negligible and ingredient.quantity is None and ingredient.amount:
                parsed_measure = convert_measure_to_grams(ingredient.amount, [])
                is_negligible = parsed_measure is not None and parsed_measure.status == "negligible"
            if is_negligible and ingredient.quantity is None:
                ingredient_rows.append(
                    models.NutritionIngredientResult(
                        run_id=run.id,
                        ingredient_id=ingredient.id,
                        status="skipped",
                        reason="negligible_measure",
                        source_id=ingredient.fineli_id,
                        source_name=ingredient.fineli_name,
                    )
                )
                continue
            if not ingredient.fineli_id:
                ingredient_rows.append(
                    models.NutritionIngredientResult(
                        run_id=run.id,
                        ingredient_id=ingredient.id,
                        status="skipped",
                        reason="unmatched",
                    )
                )
                continue
            if ingredient.quantity is None or ingredient.unit not in {"g", "kg"}:
                ingredient_rows.append(
                    models.NutritionIngredientResult(
                        run_id=run.id,
                        ingredient_id=ingredient.id,
                        status="skipped",
                        reason="unknown_quantity",
                        source_id=ingredient.fineli_id,
                        source_name=ingredient.fineli_name,
                    )
                )
                continue
            try:
                food = client.get_food(ingredient.fineli_id)
            except FineliFoodNotFound:
                ingredient_rows.append(
                    models.NutritionIngredientResult(
                        run_id=run.id,
                        ingredient_id=ingredient.id,
                        status="skipped",
                        reason="food_not_found",
                        source_id=ingredient.fineli_id,
                        source_name=ingredient.fineli_name,
                    )
                )
                continue
            sources.append(_source_value(food["source"]))
            grams = _grams(float(ingredient.quantity), ingredient.unit)
            values = food.get("nutrients_per_100g", {})
            contributions: list[dict[str, Any]] = []
            for field in NUTRIENT_FIELDS:
                value = values.get(field)
                if value is not None:
                    contribution = float(value) * grams / 100
                    totals[field] = (totals[field] or 0.0) + contribution
            for nutrient in food.get("detailed_nutrients", []):
                value = nutrient.get("value_per_100g")
                if value is None:
                    continue
                contribution = float(value) * grams / 100
                code, unit = nutrient["code"], nutrient["unit"]
                key = (code, unit)
                total = detailed_totals.setdefault(
                    key,
                    {
                        "code": code,
                        "name": nutrient["name"],
                        "unit": unit,
                        "group": nutrient.get("group"),
                        "value": 0.0,
                    },
                )
                total["value"] += contribution
                contributions.append(
                    {
                        "code": code,
                        "name": nutrient["name"],
                        "unit": unit,
                        "group": nutrient.get("group"),
                        "value": contribution,
                    }
                )
            if not any(value is not None for value in values.values()) and not contributions:
                ingredient_rows.append(
                    models.NutritionIngredientResult(
                        run_id=run.id,
                        ingredient_id=ingredient.id,
                        status="skipped",
                        reason="missing_nutrients",
                        source_id=food["id"],
                        source_name=food["name"],
                        quantity_grams=grams,
                    )
                )
                continue
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
            ingredient_rows.append(
                models.NutritionIngredientResult(
                    run_id=run.id,
                    ingredient_id=ingredient.id,
                    status="included",
                    source_id=food["id"],
                    source_name=food["name"],
                    quantity_grams=grams,
                    nutrient_contributions=contributions,
                )
            )
        included = sum(result.status == "included" for result in ingredient_rows)
        run.status = (
            "completed"
            if included == len(ingredient_rows)
            else "partial"
            if included
            else "unavailable"
        )
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
        db.add_all(ingredient_rows)
        fact = db.scalar(
            select(models.NutritionFact).where(
                models.NutritionFact.recipe_id == recipe_id
            )
        )
        source = sources[0] if sources else _default_source()
        if fact is None:
            fact = models.NutritionFact(
                recipe_id=recipe_id,
                run_id=run.id,
                values=totals,
                source=source,
            )
            db.add(fact)
        else:
            fact.run_id, fact.values, fact.source = run.id, totals, source
        db.commit()
        return _response(recipe, run, fact, db)
    finally:
        client.close()
