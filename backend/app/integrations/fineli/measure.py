from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

_MEASURE = re.compile(
    r"^(?P<quantity>\d+(?:[.,]\d+)?|\d+/\d+|\d+\s+\d+/\d+)\s*"
    r"(?P<unit>[a-zA-Zµμ]+(?:[\s-]+[a-zA-Zµμ]+)*)$"
)
_UNIT_CODES = {
    "g": "G",
    "gram": "G",
    "grams": "G",
    "kg": "KG",
    "kilogram": "KG",
    "kilograms": "KG",
    "tbsp": "RKL",
    "tablespoon": "RKL",
    "tablespoons": "RKL",
    "tsp": "TL",
    "teaspoon": "TL",
    "teaspoons": "TL",
    "dl": "DL",
    "deciliter": "DL",
    "deciliters": "DL",
    "decilitre": "DL",
    "decilitres": "DL",
    "l": "L",
    "liter": "L",
    "liters": "L",
    "litre": "L",
    "litres": "L",
    "small piece": "KPL_S",
    "small pieces": "KPL_S",
    "medium sized piece": "KPL_M",
    "medium sized pieces": "KPL_M",
    "big piece": "KPL_L",
    "big pieces": "KPL_L",
}


@dataclass(frozen=True)
class MeasureConversion:
    grams: float
    status: Literal["exact", "estimated"]


def _number(value: str) -> float | None:
    try:
        if "/" in value:
            parts = value.split()
            fraction = Fraction(parts[-1])
            number = float(fraction + int(parts[0])) if len(parts) == 2 else float(fraction)
        else:
            number = float(value.replace(",", "."))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _normalized_unit(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(ascii_text.replace("-", " ").split())


def convert_measure_to_grams(
    measure: str | None,
    food_units: list[dict[str, object]],
) -> MeasureConversion | None:
    if not measure:
        return None
    match = _MEASURE.fullmatch(measure.strip())
    if not match:
        return None
    quantity = _number(match.group("quantity"))
    if quantity is None:
        return None

    unit = _normalized_unit(match.group("unit"))
    code = _UNIT_CODES.get(unit)
    if code == "G":
        return MeasureConversion(quantity, "exact")
    if code == "KG":
        return MeasureConversion(quantity * 1000, "exact")
    if code is None:
        return None

    for food_unit in food_units:
        unit_code = str(food_unit.get("code") or food_unit.get("unit_code") or "").upper()
        unit_name = _normalized_unit(str(food_unit.get("name") or food_unit.get("unit_name") or ""))
        grams = food_unit.get("grams")
        try:
            grams_per_unit = float(grams)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(grams_per_unit) or grams_per_unit <= 0:
            continue
        if unit_code == code or unit_name == unit:
            return MeasureConversion(quantity * grams_per_unit, "estimated")
    return None
