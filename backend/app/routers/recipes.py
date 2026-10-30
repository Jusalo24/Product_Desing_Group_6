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
    recipe.ingredients = [models.Ingredient(**i.model_dump()) for i in payload.ingredients]
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
