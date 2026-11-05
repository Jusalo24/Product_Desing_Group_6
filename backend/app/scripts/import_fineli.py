"""Import the Fineli open data package (release 20.0 CSV files) into the database.

Usage (from the backend folder):
    python -m app.scripts.import_fineli                      # reads backend/data/fineli
    python -m app.scripts.import_fineli --data-dir C:\\path\\to\\fineli

Re-running is safe: the fineli_* tables are emptied and refilled.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import Engine, delete, insert
from sqlalchemy.orm import Session

from app.database import Base, engine as default_engine
from app.models import FineliFood, FineliFoodUnit
from app.scripts.progress import ProgressBar

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "fineli"
REQUIRED_FILES = (
    "food.csv",
    "foodname_EN.csv",
    "component.csv",
    "compunit_EN.csv",
    "component_value.csv",
    "foodaddunit.csv",
    "foodunit_EN.csv",
)

# column -> (Fineli component codes in order of preference, target unit)
NUTRIENTS: dict[str, tuple[tuple[str, ...], str]] = {
    "energy_kj": (("ENERC",), "kj"),
    "protein_g": (("PROT",), "g"),
    "carbohydrates_g": (("CHOAVL",), "g"),
    "fat_g": (("FAT",), "g"),
    "fiber_g": (("FIBC", "FIBT"), "g"),
    "salt_g": (("NACL",), "g"),
    "sugars_g": (("SUGAR",), "g"),
    "saturated_fat_g": (("FASAT",), "g"),
}
WANTED_CODES = {code for codes, _ in NUTRIENTS.values() for code in codes}

# unit description (lower-case, "µ" -> "u") -> (dimension, factor to g or kJ)
UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0), "gram": ("g", 1.0),
    "mg": ("g", 1e-3), "milligram": ("g", 1e-3),
    "ug": ("g", 1e-6), "mcg": ("g", 1e-6), "microgram": ("g", 1e-6),
    "kj": ("kj", 1.0), "kilojoule": ("kj", 1.0),
}
KCAL_PER_KJ = 1 / 4.184


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a Fineli CSV: ';' separated, UTF-8 or (usually) Latin-1 encoded."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return list(csv.DictReader(text.splitlines(), delimiter=";"))


def parse_number(value: str | None) -> float | None:
    """'1698,30' -> 1698.3. Blank or non-numeric means missing (None), never 0."""
    if value is None:
        return None
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def nice_name(value: str | None) -> str | None:
    value = (value or "").strip()
    return value.capitalize() if value else None


def _component_units(data_dir: Path) -> dict[str, tuple[str, float]]:
    unit_names = {
        r["THSCODE"]: r["DESCRIPT"].strip().lower().replace("µ", "u").replace("μ", "u")
        for r in read_rows(data_dir / "compunit_EN.csv")
    }
    units: dict[str, tuple[str, float]] = {}
    for row in read_rows(data_dir / "component.csv"):
        code = row["EUFDNAME"]
        if code not in WANTED_CODES:
            continue
        description = unit_names.get(row["COMPUNIT"], "")
        if description not in UNIT_FACTORS:
            raise ValueError(
                f"Unknown unit {description!r} (code {row['COMPUNIT']!r}) for component "
                f"{code}. Add it to UNIT_FACTORS in import_fineli.py."
            )
        units[code] = UNIT_FACTORS[description]

    missing = [
        column
        for column, (codes, _) in NUTRIENTS.items()
        if not any(code in units for code in codes)
    ]
    if missing:
        raise ValueError(f"Missing component unit definitions for: {', '.join(missing)}")
    return units


def import_fineli(
    data_dir: Path,
    engine: Engine = default_engine,
    show_progress: bool = False,
) -> dict[str, int]:
    missing = [name for name in REQUIRED_FILES if not (data_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing in {data_dir}: {', '.join(missing)}")

    units = _component_units(data_dir)
    for _, (codes, target) in NUTRIENTS.items():
        for code in codes:
            if code in units and units[code][0] != target:
                raise ValueError(f"Component {code} has unexpected unit type {units[code][0]}")

    # component values: {food_id: {component_code: value in g (or kJ)}}
    values: dict[str, dict[str, float]] = {}
    component_rows = read_rows(data_dir / "component_value.csv")
    with ProgressBar("Processing nutrient values", len(component_rows), show_progress) as progress:
        for row in component_rows:
            code = row["EUFDNAME"]
            if code in WANTED_CODES and code in units:
                number = parse_number(row["BESTLOC"])
                if number is not None:
                    values.setdefault(row["FOODID"], {})[code] = number * units[code][1]
            progress.advance()

    names_en = {r["FOODID"]: nice_name(r["FOODNAME"]) for r in read_rows(data_dir / "foodname_EN.csv")}

    foods = []
    food_rows = read_rows(data_dir / "food.csv")
    with ProgressBar("Preparing food records", len(food_rows), show_progress) as progress:
        for row in food_rows:
            food_id = row["FOODID"].strip()
            found = values.get(food_id, {})
            record: dict[str, object] = {
                "id": food_id,
                "name_fi": nice_name(row["FOODNAME"]) or food_id,
                "name_en": names_en.get(food_id),
            }
            for column, (codes, _) in NUTRIENTS.items():
                record[column] = next((found[c] for c in codes if c in found), None)
            kj = record["energy_kj"]
            record["energy_kcal"] = round(kj * KCAL_PER_KJ, 1) if kj is not None else None
            foods.append(record)
            progress.advance()

    unit_names = {r["THSCODE"]: r["DESCRIPT"].strip() for r in read_rows(data_dir / "foodunit_EN.csv")}
    known_ids = {f["id"] for f in foods}
    food_units = []
    unit_rows = read_rows(data_dir / "foodaddunit.csv")
    with ProgressBar("Preparing unit conversions", len(unit_rows), show_progress) as progress:
        for row in unit_rows:
            grams = parse_number(row["MASS"])
            food_id = row["FOODID"].strip()
            if grams is not None and food_id in known_ids:
                code = row["FOODUNIT"].strip()
                food_units.append(
                    {"food_id": food_id, "unit_code": code, "unit_name": unit_names.get(code, code), "grams": grams}
                )
            progress.advance()

    with ProgressBar("Preparing Fineli database tables", 1, show_progress) as progress:
        Base.metadata.create_all(bind=engine, tables=[FineliFood.__table__, FineliFoodUnit.__table__])
        progress.advance()
    with Session(engine) as db:
        with ProgressBar("Replacing existing Fineli data", 2, show_progress) as progress:
            db.execute(delete(FineliFoodUnit))
            progress.advance()
            db.execute(delete(FineliFood))
            progress.advance()
        for model, records, label in (
            (FineliFood, foods, "Saving food records"),
            (FineliFoodUnit, food_units, "Saving unit conversions"),
        ):
            with ProgressBar(label, len(records), show_progress) as progress:
                for offset in range(0, len(records), 1000):
                    batch = records[offset : offset + 1000]
                    db.execute(insert(model), batch)
                    progress.advance(len(batch))
        db.commit()
    return {"foods": len(foods), "food_units": len(food_units), "with_energy": sum(f["energy_kj"] is not None for f in foods)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    stats = import_fineli(args.data_dir, show_progress=True)
    print(f"Imported {stats['foods']} foods ({stats['with_energy']} with energy values) "
          f"and {stats['food_units']} unit conversions from {args.data_dir}")


if __name__ == "__main__":
    main()
