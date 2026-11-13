"""Apply additive database changes required by the application.

Usage (from the backend folder):
    python -m app.scripts.migrate_db
"""

from app.database import (
    Base,
    engine,
    ensure_fineli_classification_columns,
    ensure_fineli_search_indexes,
    ensure_recipe_source_columns,
)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_fineli_classification_columns(engine)
    ensure_recipe_source_columns(engine)
    ensure_fineli_search_indexes(engine)
    print("Database schema is up to date.")


if __name__ == "__main__":
    main()
