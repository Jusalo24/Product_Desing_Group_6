from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/recipes", tags=["recipes"])


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
    payload: schemas.IngredientBase,
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
    if not payload.fineli_id or payload.quantity is None or payload.unit not in {"g", "kg"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A Fineli id and g/kg quantity are required")
    ingredient.quantity = payload.quantity
    ingredient.unit = payload.unit
    ingredient.fineli_id = payload.fineli_id
    ingredient.conversion_status = "matched"
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
    db.commit()
    db.refresh(ingredient)
    return ingredient
