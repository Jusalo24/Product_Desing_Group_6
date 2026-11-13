from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.config import settings
from app.database import SessionLocal, get_db
from app.integrations.fineli.client import ExternalProviderError
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound
from app.integrations.fineli.matching import lookup_mapping
from app.integrations.themealdb.client import TheMealDbClient
from app.routers.recipes import apply_fineli_match_to_ingredient

router = APIRouter(prefix="/external-recipes", tags=["external-recipes"])


def _cache_key(path: str, params: dict[str, str]) -> str:
    return f"themealdb:{path}:{json.dumps(params, sort_keys=True)}"


def _collection_source() -> dict:
    return {
        "provider": "TheMealDB",
        "source_type": "external_api",
        "external_id": "collection",
        "source_url": "https://www.themealdb.com/",
        "retrieved_at": datetime.now(timezone.utc),
        "attribution_text": "Recipe data provided by TheMealDB",
    }


def _json_safe_meals(meals: list[dict]) -> list[dict]:
    result = []
    for meal in meals:
        item = dict(meal)
        source = dict(item["source"])
        if isinstance(source.get("retrieved_at"), datetime):
            source["retrieved_at"] = source["retrieved_at"].isoformat()
        item["source"] = source
        result.append(item)
    return result


def _cached_meals(path: str, params: dict[str, str], loader):
    key = _cache_key(path, params)
    with SessionLocal() as db:
        entry = db.scalar(select(models.ExternalCacheEntry).where(models.ExternalCacheEntry.cache_key == key))
        now = datetime.now(timezone.utc)
        if entry and entry.expires_at.replace(tzinfo=timezone.utc) > now:
            return entry.response["meals"]
        if entry:
            db.execute(delete(models.ExternalCacheEntry).where(models.ExternalCacheEntry.id == entry.id))
            db.commit()
        meals = _json_safe_meals(loader())
        db.add(
            models.ExternalCacheEntry(
                provider="themealdb",
                cache_key=key,
                response={"meals": meals},
                expires_at=now + timedelta(seconds=settings.external_cache_ttl_seconds),
            )
        )
        db.commit()
        return meals


def _provider_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": "external_provider_unavailable", "message": "External recipe provider unavailable"},
    )


def _call_meal(method, *args):
    client = TheMealDbClient()
    try:
        return method(client, *args)
    finally:
        client.close()


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


@router.get("/search", response_model=schemas.ExternalMealList)
def search_recipes(query: str = Query(min_length=1, max_length=100)):
    try:
        meals = _cached_meals("search", {"query": query}, lambda: _call_meal(TheMealDbClient.search, query))
    except ExternalProviderError as exc:
        raise _provider_error() from exc
    return {"meals": meals, "source": meals[0]["source"] if meals else _collection_source()}


@router.get("/categories")
def categories():
    try:
        return {"values": _call_meal(TheMealDbClient.list_values, "c")}
    except ExternalProviderError as exc:
        raise _provider_error() from exc


@router.get("/areas")
def areas():
    try:
        return {"values": _call_meal(TheMealDbClient.list_values, "a")}
    except ExternalProviderError as exc:
        raise _provider_error() from exc


@router.get("/ingredients")
def ingredients():
    try:
        return {"values": _call_meal(TheMealDbClient.list_values, "i")}
    except ExternalProviderError as exc:
        raise _provider_error() from exc


@router.get("/random", response_model=schemas.ExternalMeal)
def random_recipe():
    try:
        return _call_meal(TheMealDbClient.random)
    except ExternalProviderError as exc:
        raise _provider_error() from exc


@router.get("/filter/category", response_model=schemas.ExternalMealList)
def filter_category(value: str = Query(min_length=1, max_length=100)):
    try:
        meals = _call_meal(TheMealDbClient.filter, "c", value)
    except ExternalProviderError as exc:
        raise _provider_error() from exc
    return {"meals": meals, "source": meals[0]["source"] if meals else _collection_source()}


@router.get("/filter/category/{value}", response_model=schemas.ExternalMealList)
def filter_category_path(value: str):
    return filter_category(value)


@router.get("/filter/area", response_model=schemas.ExternalMealList)
def filter_area(value: str = Query(min_length=1, max_length=100)):
    try:
        meals = _call_meal(TheMealDbClient.filter, "a", value)
    except ExternalProviderError as exc:
        raise _provider_error() from exc
    return {"meals": meals, "source": meals[0]["source"] if meals else _collection_source()}


@router.get("/filter/area/{value}", response_model=schemas.ExternalMealList)
def filter_area_path(value: str):
    return filter_area(value)


@router.get("/filter/ingredient", response_model=schemas.ExternalMealList)
def filter_ingredient(value: str = Query(min_length=1, max_length=100)):
    try:
        meals = _call_meal(TheMealDbClient.filter, "i", value)
    except ExternalProviderError as exc:
        raise _provider_error() from exc
    return {"meals": meals, "source": meals[0]["source"] if meals else _collection_source()}


@router.get("/filter/ingredient/{value}", response_model=schemas.ExternalMealList)
def filter_ingredient_path(value: str):
    return filter_ingredient(value)


@router.get("/id/{external_id}", response_model=schemas.ExternalMeal)
def get_external_recipe(external_id: str):
    try:
        meal = _call_meal(TheMealDbClient.get, external_id)
    except ExternalProviderError as exc:
        raise _provider_error() from exc
    if meal is None:
        raise HTTPException(status_code=404, detail="External recipe not found")
    return meal


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

    try:
        meal = _call_meal(TheMealDbClient.get, external_id)
    except ExternalProviderError as exc:
        raise _provider_error() from exc
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
                and mapping.get("confidence") in {"high", "manual"}
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
