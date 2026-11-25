from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound
from app.integrations.fineli.matching import AUTO_MATCH_CONFIDENCES, lookup_mapping
from app.integrations.themealdb.client import ExternalProviderError, TheMealDbClient
from app.routers.recipes import apply_fineli_match_to_ingredient

router = APIRouter(prefix="/external-recipes", tags=["external-recipes"])


def _saved_external_recipe(db: Session, external_id: str) -> models.Recipe | None:
    return db.scalar(
        select(models.Recipe)
        .join(models.RecipeSource)
        .options(
            selectinload(models.Recipe.ingredients),
            selectinload(models.Recipe.source),
        )
        .where(
            models.RecipeSource.provider == "TheMealDB",
            models.RecipeSource.external_id == external_id,
        )
    )


@router.post(
    "/id/{external_id}/import",
    response_model=schemas.RecipeRead,
    status_code=status.HTTP_201_CREATED,
)
def import_external_recipe(
    external_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    existing = _saved_external_recipe(db, external_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    client = TheMealDbClient()
    try:
        meal = client.get(external_id)
    except ExternalProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "external_provider_unavailable",
                "message": "External recipe provider unavailable",
            },
        ) from exc
    finally:
        client.close()

    if meal is None:
        raise HTTPException(status_code=404, detail="External recipe not found")
    if meal["external_id"] != external_id or not meal["name"]:
        raise HTTPException(status_code=502, detail="External recipe provider returned invalid meal data")

    source = meal["source"]
    retrieved_at = source.get("retrieved_at")
    if not isinstance(retrieved_at, datetime):
        retrieved_at = datetime.now(timezone.utc)
    ingredient_models: list[models.Ingredient] = []
    fineli_client = get_fineli_client(db)
    try:
        for item in meal.get("ingredients", []):
            ing = models.Ingredient(name=item["name"], amount=item.get("amount") or "")
            mapping = lookup_mapping(db, item["name"])
            if (
                mapping
                and mapping.get("fineli_id")
                and mapping.get("confidence") in AUTO_MATCH_CONFIDENCES
            ):
                try:
                    food = fineli_client.get_food(str(mapping["fineli_id"]))
                    apply_fineli_match_to_ingredient(ing, food, db)
                except FineliFoodNotFound:
                    pass
            ingredient_models.append(ing)
    finally:
        fineli_client.close()

    recipe = models.Recipe(
        title=meal["name"],
        description="",
        instructions=meal.get("instructions") or "",
        ingredients=ingredient_models,
        source=models.RecipeSource(
            provider="TheMealDB",
            external_id=external_id,
            provider_url=source.get("source_url"),
            source_url=meal.get("source_url"),
            image_url=meal.get("thumbnail_url"),
            attribution_text=source["attribution_text"],
            extra_data={
                "category": meal.get("category"),
                "area": meal.get("area"),
                "tags": meal.get("tags", []),
                "youtube_url": meal.get("youtube_url"),
                "creative_commons_confirmed": meal.get("creative_commons_confirmed"),
            },
            retrieved_at=retrieved_at,
        ),
    )
    db.add(recipe)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _saved_external_recipe(db, external_id)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return existing
    db.refresh(recipe)
    return recipe
