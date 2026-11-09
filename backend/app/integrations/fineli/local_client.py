"""Fineli lookups served from the locally imported dataset (no network needed)."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FineliFood

FINELI_RELEASE = "20.0"
SEARCH_LIMIT = 20


class FineliFoodNotFound(LookupError):
    """Raised when a Fineli food id is not in the local dataset."""


def _source(food_id: str, name: str) -> dict[str, Any]:
    return {
        "provider": "Fineli",
        "source_type": "dataset",
        "external_id": food_id,
        "source_url": f"https://fineli.fi/fineli/fi/elintarvikkeet/{food_id}",
        "retrieved_at": datetime.now(timezone.utc),
        "attribution_text": (
            "Source: Fineli, Finnish Institute for Health and Welfare (THL), "
            f"release {FINELI_RELEASE}, CC BY 4.0"
        ),
        "name": name,
    }


def _map_food(food: FineliFood) -> dict[str, Any]:
    name = food.name_en or food.name_fi
    return {
        "id": food.id,
        "name": name,
        "food_type": food.food_type,
        "process": food.process,
        "ingredient_class": food.ingredient_class,
        "nutrients_per_100g": {
            "energy_kcal": food.energy_kcal,
            "energy_kj": food.energy_kj,
            "protein_g": food.protein_g,
            "carbohydrates_g": food.carbohydrates_g,
            "fat_g": food.fat_g,
            "fiber_g": food.fiber_g,
            "salt_g": food.salt_g,
            "sugars_g": food.sugars_g,
            "saturated_fat_g": food.saturated_fat_g,
        },
        "source": _source(food.id, name),
    }


def _search_terms(query: str) -> list[str]:
    """Split a query into order-independent words and ignore commas."""
    return [term for term in re.split(r"[\s,]+", query.strip().lower()) if term]


def _normalized_name(name: str) -> str:
    return " ".join(re.split(r"[\s,]+", name.strip().lower()))


def _rank(food: FineliFood, terms: list[str]) -> tuple[int, int]:
    """Rank exact normalized matches, prefixes, then shorter names first."""
    names = [n.lower() for n in (food.name_en, food.name_fi) if n]
    normalized_names = [_normalized_name(name) for name in names]
    normalized_query = " ".join(terms)
    if normalized_query in normalized_names:
        position = 0
    elif any(name.startswith(normalized_query) for name in normalized_names):
        position = 1
    else:
        position = 2
    return position, min(len(n) for n in names)


class LocalFineliClient:
    """Same interface as FineliClient, backed by the fineli_foods table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def close(self) -> None:  # the session is owned by the caller
        return None

    def search_foods(self, query: str) -> list[dict[str, Any]]:
        terms = _search_terms(query)
        if not terms:
            return []
        foods = [
            food
            for food in self._db.scalars(select(FineliFood))
            if any(
                all(term in _normalized_name(name) for term in terms)
                for name in (food.name_en, food.name_fi)
                if name
            )
        ]
        foods.sort(key=lambda food: _rank(food, terms))
        return [_map_food(food) for food in foods[:SEARCH_LIMIT]]

    def get_food(self, food_id: str) -> dict[str, Any]:
        food = self._db.get(FineliFood, str(food_id))
        if food is None:
            raise FineliFoodNotFound(food_id)
        return _map_food(food)
