from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngredientMapping

ALIASES_PATH = Path(__file__).resolve().parents[2] / "data" / "fineli-ingredient-aliases.json"
MAPPINGS_PATH = Path(__file__).resolve().parents[2] / "data" / "themealdb-fineli-mappings.json"

_REMOVED_WORDS = {
    "fresh",
    "chopped",
    "finely",
    "roughly",
    "coarsely",
    "diced",
    "minced",
    "sliced",
    "thinly",
    "shredded",
    "crushed",
    "grated",
    "peeled",
    "seeded",
    "deseeded",
    "trimmed",
    "halved",
    "quartered",
    "torn",
    "drained",
    "rinsed",
    "sifted",
    "softened",
    "melted",
    "divided",
    "optional",
    "garnish",
    "boneless",
    "skinless",
    "large",
    "small",
    "medium",
}

_COOKED_QUERY_WORDS = {
    "boiled",
    "fried",
    "roasted",
    "baked",
    "grilled",
    "steamed",
    "cooked",
    "dried",
    "smoked",
    "canned",
}
_RAW_PROCESSES = {"RAW", "FRESH", "IND", "X", ""}


def normalize_ingredient_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    words = re.sub(r"[^a-z0-9]+", " ", ascii_text).split()
    normalized = []
    for word in words:
        if word in _REMOVED_WORDS:
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = f"{word[:-3]}y"
        elif len(word) > 5 and word.endswith("oes"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        normalized.append(word)
    return " ".join(normalized)


def _load_aliases() -> dict[str, str]:
    with ALIASES_PATH.open(encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
    ):
        raise ValueError(f"Invalid Fineli ingredient aliases file: {ALIASES_PATH}")
    return {
        normalize_ingredient_name(key): normalize_ingredient_name(value)
        for key, value in raw.items()
    }


def _load_seed_mappings() -> dict[str, dict[str, Any]]:
    if not MAPPINGS_PATH.is_file():
        return {}
    with MAPPINGS_PATH.open(encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, list):
        return {}
    by_name: dict[str, dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = normalize_ingredient_name(str(entry.get("mealdb_name") or entry.get("raw_name") or ""))
        if key:
            by_name[key] = entry
    return by_name


ALIASES = _load_aliases()
SEED_MAPPINGS = _load_seed_mappings()


def candidate_rank(food: dict[str, Any], query: str) -> tuple[int, int, int, int, str, str]:
    name = normalize_ingredient_name(str(food.get("name") or ""))
    if name == query:
        rank = 0
    elif name.startswith(query):
        rank = 1
    else:
        rank = 2

    food_type = str(food.get("food_type") or "").upper()
    dish_penalty = 2 if food_type == "SUPPLE" else 1 if food_type == "DISH" else 0

    process = str(food.get("process") or "").upper()
    wants_processed = any(word in _COOKED_QUERY_WORDS for word in query.split())
    process_penalty = 0 if (wants_processed or process in _RAW_PROCESSES) else 1

    return rank, dish_penalty, process_penalty, len(name), name, str(food.get("id") or "")


def suggestion_queries(value: str) -> list[str]:
    normalized = normalize_ingredient_name(value)
    if not normalized:
        return []
    queries: list[str] = []
    alias = ALIASES.get(normalized)
    if alias and alias not in queries:
        queries.append(alias)
    seed = SEED_MAPPINGS.get(normalized)
    if seed and seed.get("search_hint"):
        hint = normalize_ingredient_name(str(seed["search_hint"]))
        if hint and hint not in queries:
            queries.append(hint)
    if normalized not in queries:
        queries.append(normalized)
    return queries


def lookup_mapping(db: Session, ingredient_name: str) -> dict[str, Any] | None:
    """Return DB mapping first, falling back to static seed metadata (e.g. default_weight_g)."""
    key = normalize_ingredient_name(ingredient_name)
    if not key:
        return None
    row = db.scalar(select(IngredientMapping).where(IngredientMapping.mealdb_name == key))
    if row is not None:
        return {
            "mealdb_name": row.mealdb_name,
            "fineli_id": row.fineli_id,
            "search_hint": row.search_hint,
            "default_weight_g": row.default_weight_g,
            "confidence": row.confidence,
        }
    seed = SEED_MAPPINGS.get(key)
    if seed is not None:
        return {
            "mealdb_name": key,
            "fineli_id": seed.get("fineli_id"),
            "search_hint": seed.get("search_hint"),
            "default_weight_g": seed.get("default_weight_g"),
            "confidence": seed.get("confidence", "medium"),
        }
    return None
