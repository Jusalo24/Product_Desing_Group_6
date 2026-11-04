from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ExternalProviderError(RuntimeError):
    """Raised when an external provider cannot supply a valid response."""


def _source(external_id: str, name: str | None = None) -> dict[str, Any]:
    return {
        "provider": "Fineli",
        "source_type": "api",
        "external_id": external_id,
        "source_url": f"https://fineli.fi/fineli/fi/elintarvikkeet/{external_id}",
        "retrieved_at": datetime.now(timezone.utc),
        "attribution_text": "Source: Fineli, Finnish Institute for Health and Welfare",
        "name": name,
    }


def _nutrient_value(data: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = data.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _map_food(item: dict[str, Any]) -> dict[str, Any]:
    food_id = str(item.get("id") or item.get("foodId") or item.get("code") or "")
    name = str(item.get("name") or item.get("foodName") or item.get("fiName") or "")
    nutrients = item.get("nutrients") or item.get("nutrition") or item
    if not food_id or not name:
        raise ExternalProviderError("Fineli returned a food without id or name")
    values = {
        "energy_kcal": _nutrient_value(nutrients, "energy_kcal", "energyKcal", "ENERC_KCAL"),
        "energy_kj": _nutrient_value(nutrients, "energy_kj", "energyKj", "ENERC_KJ"),
        "protein_g": _nutrient_value(nutrients, "protein_g", "protein", "PROT"),
        "carbohydrates_g": _nutrient_value(
            nutrients, "carbohydrates_g", "carbohydrates", "CHO"
        ),
        "fat_g": _nutrient_value(nutrients, "fat_g", "fat", "FAT"),
        "fiber_g": _nutrient_value(nutrients, "fiber_g", "fiber", "FIBT"),
        "salt_g": _nutrient_value(nutrients, "salt_g", "salt", "SALT"),
        "sugars_g": _nutrient_value(nutrients, "sugars_g", "sugars", "SUGAR"),
        "saturated_fat_g": _nutrient_value(
            nutrients, "saturated_fat_g", "saturatedFat", "FASAT"
        ),
    }
    return {"id": food_id, "name": name, "nutrients_per_100g": values, "source": _source(food_id, name)}


class FineliClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=settings.external_api_timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, path: str, params: dict[str, str]) -> Any:
        url = httpx.URL(
            f"{settings.fineli_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        ).copy_merge_params(params)
        logger.warning("Fineli request: %s", url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Fineli request failed: url=%s status=%s response=%s",
                url,
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise ExternalProviderError(
                f"Fineli returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Fineli request failed: url=%s error=%s", url, exc)
            raise ExternalProviderError("Fineli request failed") from exc
        except ValueError as exc:
            logger.error("Fineli returned invalid JSON: url=%s error=%s", url, exc)
            raise ExternalProviderError("Fineli request failed") from exc

    def search_foods(self, query: str) -> list[dict[str, Any]]:
        payload = self._request(settings.fineli_foods_path, {"q": query})
        items = payload.get("foods", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ExternalProviderError("Fineli returned an invalid food list")
        return [_map_food(item) for item in items if isinstance(item, dict)]

    def get_food(self, food_id: str) -> dict[str, Any]:
        payload = self._request(f"{settings.fineli_foods_path}/{food_id}", {})
        item = payload.get("food", payload) if isinstance(payload, dict) else payload
        if not isinstance(item, dict):
            raise ExternalProviderError("Fineli returned an invalid food")
        return _map_food(item)
