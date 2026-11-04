from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from app import models, schemas
from app.config import settings
from app.database import SessionLocal
from app.integrations.fineli.client import ExternalProviderError
from app.integrations.themealdb.client import TheMealDbClient

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

