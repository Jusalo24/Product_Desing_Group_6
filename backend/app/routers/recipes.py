from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound
from app.integrations.fineli.matching import lookup_mapping
from app.integrations.fineli.measure import convert_measure_to_grams

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _invalidate_nutrition_cache(recipe_id: int, db: Session) -> None:
    active_fact = db.scalar(
        select(models.NutritionFact).where(models.NutritionFact.recipe_id == recipe_id)
    )
    if active_fact is not None:
        db.delete(active_fact)
    active_runs = db.scalars(
        select(models.NutritionCalculationRun).where(
            models.NutritionCalculationRun.recipe_id == recipe_id,
            models.NutritionCalculationRun.is_active.is_(True),
        )
    ).all()
    for run in active_runs:
        run.is_active = False


def apply_fineli_match_to_ingredient(
    ingredient: models.Ingredient,
    food: dict,
    db: Session,
    *,
    quantity: float | None = None,
    unit: str | None = None,
) -> None:
    """Assign Fineli source metadata and convert ingredient amount into grams."""
    if quantity is not None:
        ingredient.quantity = quantity
        ingredient.unit = unit
        ingredient.conversion_status = "exact"
    elif ingredient.fineli_id != food["id"] or ingredient.quantity is None:
        mapping = lookup_mapping(db, ingredient.name)
        default_weight = mapping.get("default_weight_g") if mapping else None
        conversion = convert_measure_to_grams(
            ingredient.amount,
            food.get("units", []),
            default_weight_g=default_weight,
            ingredient_name=ingredient.name,
        )
        if conversion is None:
            ingredient.quantity = None
            ingredient.unit = None
            ingredient.conversion_status = "unknown"
        elif conversion.status == "negligible" or conversion.grams is None:
            ingredient.quantity = None
            ingredient.unit = None
            ingredient.conversion_status = "negligible"
        else:
            ingredient.quantity = conversion.grams
            ingredient.unit = "g"
            ingredient.conversion_status = conversion.status
    elif ingredient.unit in {"g", "kg"}:
        ingredient.conversion_status = "exact"

    ingredient.fineli_id = food["id"]
    ingredient.fineli_name = food["name"]


@router.get("", response_model=list[schemas.RecipeRead])
def list_recipes(db: Session = Depends(get_db)):
    stmt = (
        select(models.Recipe)
        .options(selectinload(models.Recipe.ingredients))
        .order_by(models.Recipe.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{recipe_id}", response_model=schemas.RecipeRead)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    return recipe


@router.post("", response_model=schemas.RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(payload: schemas.RecipeCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"ingredients"})
    recipe = models.Recipe(**data)
    recipe.ingredients = [
        models.Ingredient(
            **i.model_dump(),
            conversion_status="matched" if i.fineli_id else "unmatched",
        )
        for i in payload.ingredients
    ]
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    db.delete(recipe)
    db.commit()


@router.put("/{recipe_id}/ingredients", response_model=schemas.RecipeRead)
def update_ingredients(
    recipe_id: int,
    payload: schemas.RecipeIngredientsUpdate,
    db: Session = Depends(get_db),
):
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    if len(payload.ingredients) != len(recipe.ingredients):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ingredient editing cannot add or remove ingredients",
        )

    for existing, ingredient in zip(recipe.ingredients, payload.ingredients):
        existing.name = ingredient.name
        existing.amount = ingredient.amount
        existing.quantity = ingredient.quantity
        existing.unit = ingredient.unit
        existing.fineli_id = ingredient.fineli_id
        existing.conversion_status = "matched" if ingredient.fineli_id else "unmatched"
    _invalidate_nutrition_cache(recipe_id, db)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.put(
    "/{recipe_id}/ingredients/{ingredient_id}/nutrition-source",
    response_model=schemas.IngredientRead,
)
def match_ingredient(
    recipe_id: int,
    ingredient_id: int,
    payload: schemas.IngredientMatch,
    db: Session = Depends(get_db),
):
    ingredient = db.scalar(
        select(models.Ingredient).where(
            models.Ingredient.id == ingredient_id,
            models.Ingredient.recipe_id == recipe_id,
        )
    )
    if ingredient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found")
    if (payload.quantity is None) != (payload.unit is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Quantity and unit must be provided together",
        )
    client = get_fineli_client(db)
    try:
        try:
            food = client.get_food(payload.fineli_id)
        except FineliFoodNotFound as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown Fineli food id {payload.fineli_id}",
            ) from exc
    finally:
        client.close()

    apply_fineli_match_to_ingredient(
        ingredient,
        food,
        db,
        quantity=payload.quantity,
        unit=payload.unit,
    )
    _invalidate_nutrition_cache(recipe_id, db)
    db.commit()
    db.refresh(ingredient)
    return ingredient


@router.post("/{recipe_id}/ingredients/auto-match", response_model=schemas.RecipeRead)
def auto_match_ingredients(recipe_id: int, db: Session = Depends(get_db)):
    """Auto-match unmatched ingredients using ingredient_mappings or exact Fineli candidates."""
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")

    client = get_fineli_client(db)
    try:
        changed = False
        for ingredient in recipe.ingredients:
            if ingredient.fineli_id:
                continue
            mapping = lookup_mapping(db, ingredient.name)
            food = None
            if mapping and mapping.get("fineli_id"):
                try:
                    food = client.get_food(str(mapping["fineli_id"]))
                except FineliFoodNotFound:
                    food = None
            if food is None:
                continue
            apply_fineli_match_to_ingredient(ingredient, food, db)
            changed = True
        if changed:
            _invalidate_nutrition_cache(recipe_id, db)
            db.commit()
            db.refresh(recipe)
        return recipe
    finally:
        client.close()
