"""Load curated TheMealDB-to-Fineli mappings from JSON into the ingredient_mappings table.

Usage (from the backend folder):
    python -m app.scripts.import_mappings
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.database import Base, engine as default_engine
from app.integrations.fineli.matching import MAPPINGS_PATH, normalize_ingredient_name
from app.models import IngredientMapping


def import_mappings(
    mappings_path: Path = MAPPINGS_PATH,
    engine: Engine = default_engine,
) -> dict[str, int]:
    if not mappings_path.is_file():
        raise FileNotFoundError(f"Mappings file not found: {mappings_path}")

    entries = json.loads(mappings_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"Expected a JSON list in {mappings_path}")

    Base.metadata.create_all(bind=engine, tables=[IngredientMapping.__table__])

    inserted = 0
    updated = 0
    with Session(engine) as db:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_name = str(entry.get("raw_name") or entry.get("mealdb_name") or "").strip()
            mealdb_name = normalize_ingredient_name(
                str(entry.get("mealdb_name") or raw_name)
            )
            if not mealdb_name:
                continue

            existing = db.scalar(
                select(IngredientMapping).where(
                    IngredientMapping.mealdb_name == mealdb_name
                )
            )
            fineli_id = entry.get("fineli_id")
            fineli_id_str = str(fineli_id).strip() if fineli_id else None
            default_weight = entry.get("default_weight_g")
            default_weight_f = (
                float(default_weight) if default_weight is not None else None
            )
            search_hint = (
                str(entry["search_hint"]).strip() if entry.get("search_hint") else None
            )
            confidence = str(entry.get("confidence") or "medium").strip()
            notes = str(entry["notes"]).strip() if entry.get("notes") else None

            if existing is None:
                db.add(
                    IngredientMapping(
                        mealdb_name=mealdb_name,
                        raw_name=raw_name or mealdb_name,
                        fineli_id=fineli_id_str,
                        search_hint=search_hint,
                        default_weight_g=default_weight_f,
                        confidence=confidence,
                        notes=notes,
                    )
                )
                inserted += 1
            else:
                existing.raw_name = raw_name or existing.raw_name
                existing.fineli_id = fineli_id_str
                existing.search_hint = search_hint
                existing.default_weight_g = default_weight_f
                existing.confidence = confidence
                existing.notes = notes
                updated += 1
        db.commit()

    return {"inserted": inserted, "updated": updated}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=MAPPINGS_PATH)
    args = parser.parse_args()
    stats = import_mappings(args.input)
    print(f"Imported mappings: {stats['inserted']} inserted, {stats['updated']} updated.")


if __name__ == "__main__":
    main()
