from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.integrations.fineli.client import ExternalProviderError

logger = logging.getLogger(__name__)


def _source(external_id: str | None = None) -> dict[str, Any]:
    return {
        "provider": "TheMealDB",
        "source_type": "external_api",
        "external_id": external_id or "collection",
        "source_url": (
            f"https://www.themealdb.com/meal/{external_id}" if external_id else "https://www.themealdb.com/"
        ),
        "retrieved_at": datetime.now(timezone.utc),
        "attribution_text": "Recipe data provided by TheMealDB",
    }


def _map_meal(item: dict[str, Any]) -> dict[str, Any]:
    meal_id = str(item.get("idMeal") or "")
    if not meal_id or not item.get("strMeal"):
        raise ExternalProviderError("TheMealDB returned a meal without id or name")
    ingredients = []
    for index in range(1, 21):
        ingredient = (item.get(f"strIngredient{index}") or "").strip()
        measure = (item.get(f"strMeasure{index}") or "").strip()
        if ingredient:
            ingredients.append({"name": ingredient, "amount": measure})
    return {
        "external_id": meal_id,
        "name": item["strMeal"],
        "category": item.get("strCategory"),
        "area": item.get("strArea"),
        "instructions": item.get("strInstructions"),
        "thumbnail_url": item.get("strMealThumb"),
        "source_url": item.get("strSource") or f"https://www.themealdb.com/meal/{meal_id}",
        "ingredients": ingredients,
        "source": _source(meal_id),
    }


class TheMealDbClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=settings.external_api_timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = httpx.URL(
            f"{settings.themealdb_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        ).copy_merge_params(params or {})
        logger.info("TheMealDB request: %s", url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalProviderError("TheMealDB request failed") from exc
        if not isinstance(payload, dict):
            raise ExternalProviderError("TheMealDB returned an invalid response")
        return payload

    def _meals(self, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        payload = self._request(path, params)
        if "meals" not in payload:
            raise ExternalProviderError("TheMealDB response did not contain meals")
        return [_map_meal(item) for item in (payload.get("meals") or []) if isinstance(item, dict)]

    def search(self, query: str) -> list[dict[str, Any]]:
        return self._meals("search.php", {"s": query})

    def get(self, external_id: str) -> dict[str, Any] | None:
        meals = self._meals("lookup.php", {"i": external_id})
        return meals[0] if meals else None

    def random(self) -> dict[str, Any]:
        meals = self._meals("random.php")
        if not meals:
            raise ExternalProviderError("TheMealDB returned no random meal")
        return meals[0]

    def filter(self, kind: str, value: str) -> list[dict[str, Any]]:
        return self._meals("filter.php", {kind: value})

    def list_values(self, kind: str) -> list[dict[str, Any]]:
        payload = self._request("list.php", {kind: "list"})
        return payload.get({"c": "meals", "a": "meals", "i": "meals"}[kind]) or []
