from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

ALIASES_PATH = Path(__file__).resolve().parents[2] / "data" / "fineli-ingredient-aliases.json"
_REMOVED_WORDS = {"fresh", "chopped", "finely", "diced", "minced", "large", "small", "medium"}


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


ALIASES = _load_aliases()


def candidate_rank(food: dict[str, Any], query: str) -> tuple[int, int, str, str]:
    name = normalize_ingredient_name(str(food.get("name") or ""))
    if name == query:
        rank = 0
    elif name.startswith(query):
        rank = 1
    else:
        rank = 2
    return rank, len(name), name, str(food.get("id") or "")


def suggestion_queries(value: str) -> list[str]:
    normalized = normalize_ingredient_name(value)
    if not normalized:
        return []
    alias = ALIASES.get(normalized)
    if alias and alias != normalized:
        return [alias, normalized]
    return [normalized]
