from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

_UNICODE_FRACTIONS: dict[str, str] = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

_NEGLIGIBLE_PHRASES = {
    "to taste",
    "taste",
    "pinch",
    "a pinch",
    "pinch of",
    "pinches",
    "dash",
    "a dash",
    "dashes",
    "garnish",
    "for garnish",
    "to garnish",
    "for serving",
    "to serve",
    "serving",
    "as needed",
    "if needed",
    "as required",
    "optional",
    "for frying",
    "for deep frying",
    "for greasing",
    "for dusting",
    "some",
    "little",
    "a little",
    "splash",
    "a splash",
    "drizzle",
    "a drizzle",
    "handful",
    "a handful",
}

_TRAILING_MODIFIERS = {
    "chopped",
    "finely",
    "roughly",
    "coarsely",
    "diced",
    "minced",
    "sliced",
    "thinly",
    "thickly",
    "crushed",
    "grated",
    "shredded",
    "peeled",
    "unpeeled",
    "seeded",
    "deseeded",
    "cored",
    "trimmed",
    "halved",
    "quartered",
    "cubed",
    "torn",
    "crumbled",
    "drained",
    "rinsed",
    "sifted",
    "packed",
    "loosely",
    "firmly",
    "heaped",
    "heaping",
    "level",
    "beaten",
    "whisked",
    "melted",
    "softened",
    "chilled",
    "warm",
    "cold",
    "hot",
    "boiling",
    "toasted",
    "roasted",
    "baked",
    "cooked",
    "uncooked",
    "raw",
    "fresh",
    "dried",
    "ground",
    "boneless",
    "skinless",
    "divided",
    "optional",
    "plus",
    "more",
    "for",
    "garnish",
    "serve",
    "serving",
    "to",
    "taste",
    "or",
    "and",
    "in",
    "of",
    "with",
    "without",
    "removed",
    "reserved",
    "room",
    "temperature",
}

_DIRECT_MASS_FACTORS: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "gm": 1.0,
    "gms": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "kilo": 1000.0,
    "kilos": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "oz": 28.349523125,
    "ounce": 28.349523125,
    "ounces": 28.349523125,
    "lb": 453.59237,
    "lbs": 453.59237,
    "pound": 453.59237,
    "pounds": 453.59237,
}

# Volume unit -> millilitres (US cup = 240 ml nutrition standard)
_VOLUME_ML: dict[str, float] = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "millilitre": 1.0,
    "millilitres": 1.0,
    "cl": 10.0,
    "centiliter": 10.0,
    "centiliters": 10.0,
    "centilitre": 10.0,
    "centilitres": 10.0,
    "dl": 100.0,
    "deciliter": 100.0,
    "deciliters": 100.0,
    "decilitre": 100.0,
    "decilitres": 100.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "ltr": 1000.0,
    "tsp": 5.0,
    "tsps": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "tl": 5.0,
    "tbsp": 15.0,
    "tbs": 15.0,
    "tbl": 15.0,
    "tb": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "rkl": 15.0,
    "fl oz": 29.5735,
    "floz": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
    "cup": 240.0,
    "cups": 240.0,
    "c": 240.0,
    "pint": 473.176,
    "pints": 473.176,
    "pt": 473.176,
    "quart": 946.353,
    "quarts": 946.353,
    "qt": 946.353,
}

# Unit text -> candidate Fineli unit codes in preference order
_FINELI_UNIT_CODES: dict[str, tuple[str, ...]] = {
    "tbsp": ("RKL", "TBSP"),
    "tbs": ("RKL", "TBSP"),
    "tbl": ("RKL", "TBSP"),
    "tb": ("RKL", "TBSP"),
    "tablespoon": ("RKL", "TBSP"),
    "tablespoons": ("RKL", "TBSP"),
    "rkl": ("RKL", "TBSP"),
    "tsp": ("TL", "TSP"),
    "tsps": ("TL", "TSP"),
    "teaspoon": ("TL", "TSP"),
    "teaspoons": ("TL", "TSP"),
    "tl": ("TL", "TSP"),
    "dl": ("DL",),
    "deciliter": ("DL",),
    "deciliters": ("DL",),
    "decilitre": ("DL",),
    "decilitres": ("DL",),
    "l": ("L",),
    "liter": ("L",),
    "liters": ("L",),
    "litre": ("L",),
    "litres": ("L",),
    "ltr": ("L",),
    "small": ("KPL_S",),
    "small piece": ("KPL_S",),
    "small pieces": ("KPL_S",),
    "medium": ("KPL_M",),
    "medium piece": ("KPL_M",),
    "medium pieces": ("KPL_M",),
    "medium sized piece": ("KPL_M",),
    "medium sized pieces": ("KPL_M",),
    "whole": ("KPL_M", "KPL_S", "KPL_L", "KPL_VALM"),
    "piece": ("KPL_M", "KPL_S", "KPL_L", "KPL_VALM"),
    "pieces": ("KPL_M", "KPL_S", "KPL_L", "KPL_VALM"),
    "kpl": ("KPL_M", "KPL_S", "KPL_L", "KPL_VALM"),
    "large": ("KPL_L",),
    "big": ("KPL_L",),
    "large piece": ("KPL_L",),
    "large pieces": ("KPL_L",),
    "big piece": ("KPL_L",),
    "big pieces": ("KPL_L",),
    "slice": ("VIIL", "SLICE", "KPL_VALM", "KPL_M"),
    "slices": ("VIIL", "SLICE", "KPL_VALM", "KPL_M"),
    "portion": ("PORTM", "PORTL"),
    "portions": ("PORTM", "PORTL"),
}

_COUNT_UNITS = {
    "",
    "whole",
    "piece",
    "pieces",
    "kpl",
    "small",
    "medium",
    "large",
    "big",
    "small piece",
    "small pieces",
    "medium piece",
    "medium pieces",
    "medium sized piece",
    "medium sized pieces",
    "large piece",
    "large pieces",
    "big piece",
    "big pieces",
}

_SIZE_SCALE = {
    "small": 0.75,
    "small piece": 0.75,
    "small pieces": 0.75,
    "large": 1.35,
    "big": 1.35,
    "large piece": 1.35,
    "large pieces": 1.35,
    "big piece": 1.35,
    "big pieces": 1.35,
}

_CONTAINER_UNITS = {"can", "cans", "tin", "tins", "jar", "jars", "pack", "packs", "packet", "packets", "bag", "bags", "box", "boxes", "bottle", "bottles", "carton", "cartons"}

_QTY_TOKEN = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"
_MEASURE_RANGE = re.compile(
    rf"^(?P<low>{_QTY_TOKEN})\s*(?:-|to)\s*(?P<high>{_QTY_TOKEN})\s*(?P<unit>.*)$",
    re.IGNORECASE,
)
_MEASURE_SINGLE = re.compile(
    rf"^(?P<quantity>{_QTY_TOKEN})\s*(?P<unit>.*)$",
    re.IGNORECASE,
)
_PAREN_MEASURE = re.compile(r"\(([^)]+)\)")


@dataclass(frozen=True)
class MeasureConversion:
    grams: float | None
    status: Literal["exact", "estimated", "negligible"]
    note: str | None = None


def _replace_unicode_fractions(text: str) -> str:
    for glyph, replacement in _UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d){re.escape(glyph)}", rf"\1 {replacement}", text)
        text = text.replace(glyph, replacement)
    return text


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


def _normalized_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(ascii_text.replace("-", " ").split())


def _clean_unit(raw_unit: str) -> str:
    # Drop anything after a comma (e.g. "tbsp, finely chopped")
    base = raw_unit.split(",", 1)[0].strip()
    # Remove remaining parenthetical remarks
    base = re.sub(r"\([^)]*\)", " ", base)
    normalized = _normalized_text(base).strip(".")
    if not normalized:
        return ""
    tokens = normalized.split()
    while len(tokens) > 1 and tokens[-1] in _TRAILING_MODIFIERS:
        tokens.pop()
    if len(tokens) == 1 and tokens[0] in _TRAILING_MODIFIERS:
        return ""
    return " ".join(tokens)


def _extract_quantity_and_unit(measure: str) -> tuple[float, str, bool] | None:
    cleaned = _replace_unicode_fractions(measure.strip())
    # Normalize mixed fraction hyphen like "1-1/2" to "1 1/2" (only when right side has '/')
    cleaned = re.sub(r"\b(\d+)-(\d+/\d+)\b", r"\1 \2", cleaned)

    range_match = _MEASURE_RANGE.fullmatch(cleaned)
    if range_match:
        low = _number(range_match.group("low"))
        high = _number(range_match.group("high"))
        if low is None or high is None:
            return None
        return (low + high) / 2.0, range_match.group("unit").strip(), True

    single_match = _MEASURE_SINGLE.fullmatch(cleaned)
    if single_match:
        qty = _number(single_match.group("quantity"))
        if qty is None:
            return None
        return qty, single_match.group("unit").strip(), False

    return None


def _unit_grams_map(food_units: list[dict[str, object]]) -> tuple[dict[str, float], dict[str, float]]:
    by_code: dict[str, float] = {}
    by_name: dict[str, float] = {}
    for food_unit in food_units:
        code = str(food_unit.get("code") or food_unit.get("unit_code") or "").strip().upper()
        name = _normalized_text(str(food_unit.get("name") or food_unit.get("unit_name") or ""))
        try:
            grams = float(food_unit.get("grams"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not math.isfinite(grams) or grams <= 0:
            continue
        if code:
            by_code[code] = grams
        if name:
            by_name[name] = grams
    return by_code, by_name


def _volume_grams_from_food_units(
    ml: float,
    by_code: dict[str, float],
) -> tuple[float, str] | None:
    if "DL" in by_code:
        return (ml / 100.0) * by_code["DL"], "volume_via_fineli_dl"
    if "L" in by_code:
        return (ml / 1000.0) * by_code["L"], "volume_via_fineli_l"
    return None


def _guess_density_g_per_ml(ingredient_name: str | None) -> float:
    if not ingredient_name:
        return 1.0
    name = _normalized_text(ingredient_name)
    if any(word in name for word in ("oil", "butter", "ghee", "lard")):
        return 0.91
    if any(word in name for word in ("flour", "cocoa", "starch", "cornflour", "icing sugar", "powdered sugar")):
        return 0.55
    if any(word in name for word in ("oats", "oatmeal", "breadcrumb", "panko")):
        return 0.45
    if any(word in name for word in ("honey", "syrup", "treacle", "molasses")):
        return 1.4
    if any(word in name for word in ("sugar", "salt")):
        return 0.85
    if any(word in name for word in ("rice", "lentil", "couscous", "quinoa")):
        return 0.85
    return 1.0


def convert_measure_to_grams(
    measure: str | None,
    food_units: list[dict[str, object]],
    *,
    default_weight_g: float | None = None,
    ingredient_name: str | None = None,
) -> MeasureConversion | None:
    """Convert a free-text recipe measure into grams when possible.

    Resolution order:
    1. Non-quantitative / negligible expressions ("to taste", "pinch", "garnish").
    2. Parenthetical explicit measure on container amounts (e.g. "1 can (400g)").
    3. Direct mass units (g, kg, mg, oz, lb).
    4. Fineli food-specific household units (RKL/TBSP, TL/TSP, DL, L, KPL_*, VIIL, PORTM).
    5. Volume units bridged through Fineli's DL/L density or a general density estimate.
    6. Count / piece fallback via Fineli KPL_* or mapping default_weight_g.
    """
    if not measure or not measure.strip():
        return None

    normalized_full = _normalized_text(measure)
    if normalized_full in _NEGLIGIBLE_PHRASES:
        return MeasureConversion(grams=None, status="negligible", note="non_quantitative")

    parsed = _extract_quantity_and_unit(measure)
    if parsed is None:
        return None

    quantity, raw_unit, is_range = parsed
    by_code, by_name = _unit_grams_map(food_units)

    # Check parenthetical explicit weights like "1 can (400g)" or "2 tins (400g)"
    paren_match = _PAREN_MEASURE.search(raw_unit)
    unit_before_paren = _clean_unit(re.sub(r"\([^)]*\)", "", raw_unit))
    if paren_match and unit_before_paren in _CONTAINER_UNITS:
        inner = convert_measure_to_grams(
            paren_match.group(1),
            food_units,
            default_weight_g=default_weight_g,
            ingredient_name=ingredient_name,
        )
        if inner is not None and inner.grams is not None:
            return MeasureConversion(
                grams=quantity * inner.grams,
                status="estimated" if is_range or quantity != 1 else inner.status,
                note="container_parenthetical",
            )

    unit = _clean_unit(raw_unit)

    # 1. Direct mass
    if unit in _DIRECT_MASS_FACTORS:
        grams = quantity * _DIRECT_MASS_FACTORS[unit]
        status: Literal["exact", "estimated"] = "estimated" if is_range else "exact"
        return MeasureConversion(grams=grams, status=status, note="direct_mass")

    # 2. Exact match in Fineli food_units (by code or unit_name)
    candidate_codes = _FINELI_UNIT_CODES.get(unit, ())
    for code in candidate_codes:
        if code in by_code:
            return MeasureConversion(
                grams=quantity * by_code[code],
                status="estimated",
                note=f"fineli_unit:{code}",
            )
    if unit and unit in by_name:
        return MeasureConversion(
            grams=quantity * by_name[unit],
            status="estimated",
            note=f"fineli_unit_name:{unit}",
        )

    # 3. Volume units (bridged through Fineli DL/L if present, otherwise density fallback)
    if unit in _VOLUME_ML:
        total_ml = quantity * _VOLUME_ML[unit]
        bridged = _volume_grams_from_food_units(total_ml, by_code)
        if bridged is not None:
            grams, note = bridged
            return MeasureConversion(grams=grams, status="estimated", note=note)
        density = _guess_density_g_per_ml(ingredient_name)
        return MeasureConversion(
            grams=total_ml * density,
            status="estimated",
            note="volume_density_fallback",
        )

    # 4. Countable pieces / bare numbers ("2", "2 whole", "3 cloves", "2 large")
    if unit in {"clove", "cloves"}:
        per_clove = default_weight_g if default_weight_g and default_weight_g > 0 else 5.0
        return MeasureConversion(
            grams=quantity * per_clove,
            status="estimated",
            note="garlic_clove_estimate",
        )

    if unit in _COUNT_UNITS:
        scale = _SIZE_SCALE.get(unit, 1.0)
        for fallback_code in ("KPL_M", "KPL_S", "KPL_L", "KPL_VALM"):
            if fallback_code in by_code:
                applied_scale = scale if fallback_code == "KPL_M" else 1.0
                return MeasureConversion(
                    grams=quantity * by_code[fallback_code] * applied_scale,
                    status="estimated",
                    note=f"fineli_piece:{fallback_code}",
                )
        if default_weight_g is not None and math.isfinite(default_weight_g) and default_weight_g > 0:
            return MeasureConversion(
                grams=quantity * default_weight_g * scale,
                status="estimated",
                note="mapping_default_weight",
            )

    return None
