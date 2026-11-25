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
    "freshly",
    "chopped",
    "finely",
    "roughly",
    "coarsely",
    "diced",
    "minced",
    "sliced",
    "thinly",
    "thickly",
    "thin",
    "thick",
    "shredded",
    "crushed",
    "grated",
    "peeled",
    "unpeeled",
    "seeded",
    "deseeded",
    "cored",
    "trimmed",
    "halved",
    "quartered",
    "cubed",
    "crumbled",
    "beaten",
    "whisked",
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
    "deveined",
    "julienned",
    "large",
    "small",
    "medium",
}

_COOKED_QUERY_WORDS = {
    "boiled",
    "fried",
    "deep",
    "roasted",
    "baked",
    "grilled",
    "steamed",
    "cooked",
    "dried",
    "smoked",
    "canned",
    "pickled",
    "salted",
}
_RAW_PROCESSES = {"RAW", "FRESH", "IND", "X", ""}

AUTO_MATCH_CONFIDENCES = frozenset({"high", "manual"})

_IRREGULAR_SINGULARS = {
    "leaves": "leaf",
    "halves": "half",
    "loaves": "loaf",
    "calves": "calf",
}
_KEEP_FINAL_S_WORDS = {
    "molasses",
    "watercress",
    "lemongrass",
    "cress",
    "hummus",
    "couscous",
    "asparagus",
    "citrus",
    "octopus",
    "hibiscus",
    "swiss",
}


def _singularize_word(word: str) -> str:
    if word in _IRREGULAR_SINGULARS:
        return _IRREGULAR_SINGULARS[word]
    if word in _KEEP_FINAL_S_WORDS or word.endswith(("ss", "us", "is")):
        return word
    if len(word) > 4 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 5 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 4 and word.endswith(("ches", "shes", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def normalize_ingredient_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    words = re.sub(r"[^a-z0-9]+", " ", ascii_text).split()
    normalized = []
    for word in words:
        if word in _REMOVED_WORDS:
            continue
        normalized.append(_singularize_word(word))
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


def _name_match_tier(normalized_name: str, normalized_query: str) -> int:
    if not normalized_name or not normalized_query:
        return 4
    if normalized_name == normalized_query:
        return 0
    if normalized_name.startswith(f"{normalized_query} "):
        return 1
    query_words = normalized_query.split()
    name_words = set(normalized_name.split())
    if query_words and all(word in name_words for word in query_words):
        return 2
    if normalized_name.startswith(normalized_query):
        return 3
    return 4


def _food_names(food: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "name_en", "name_fi"):
        raw = str(food.get(key) or "").strip()
        if raw and raw not in names:
            names.append(raw)
    return names


def rank_food_names(
    names: list[str],
    *,
    food_type: str | None,
    process: str | None,
    food_id: str,
    queries: list[str],
) -> tuple[int, int, int, int, str, str]:
    normalized_names = [normalize_ingredient_name(name) for name in names if name]
    normalized_queries = [normalize_ingredient_name(q) for q in queries if q]
    normalized_queries = [q for q in normalized_queries if q]

    best_tier = 4
    best_name = normalized_names[0] if normalized_names else ""
    best_len = min((len(name) for name in normalized_names), default=0)
    for norm_name in normalized_names:
        for norm_query in normalized_queries:
            tier = _name_match_tier(norm_name, norm_query)
            if tier < best_tier or (tier == best_tier and len(norm_name) < best_len):
                best_tier = tier
                best_name = norm_name
                best_len = len(norm_name)

    ft = str(food_type or "").upper()
    dish_penalty = 2 if ft == "SUPPLE" else 1 if ft == "DISH" else 0

    proc = str(process or "").upper()
    wants_processed = any(
        word in _COOKED_QUERY_WORDS
        for norm_query in normalized_queries
        for word in norm_query.split()
    )
    process_penalty = 0 if (wants_processed or proc in _RAW_PROCESSES) else 1

    return best_tier, dish_penalty, process_penalty, best_len, best_name, str(food_id or "")


def candidate_rank(
    food: dict[str, Any], query: str | list[str]
) -> tuple[int, int, int, int, str, str]:
    queries = [query] if isinstance(query, str) else list(query)
    return rank_food_names(
        _food_names(food),
        food_type=food.get("food_type"),
        process=food.get("process"),
        food_id=str(food.get("id") or ""),
        queries=queries,
    )


def is_exact_basic_food_match(food: dict[str, Any], ingredient_name: str) -> bool:
    """Return True when a Fineli basic food matches the normalized ingredient name 1:1."""
    normalized_query = normalize_ingredient_name(ingredient_name)
    if not normalized_query:
        return False
    food_type = str(food.get("food_type") or "").upper()
    if food_type != "FOOD":
        return False
    process = str(food.get("process") or "").upper()
    wants_processed = any(
        word in _COOKED_QUERY_WORDS for word in normalized_query.split()
    )
    if not wants_processed and process not in _RAW_PROCESSES:
        return False
    return any(
        normalize_ingredient_name(name) == normalized_query
        for name in _food_names(food)
    )


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
