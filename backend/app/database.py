from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_fineli_classification_columns(db_engine=engine) -> None:
    """Add classification columns to databases created before this feature."""
    existing = {
        column["name"] for column in inspect(db_engine).get_columns("fineli_foods")
    }
    columns = {
        "food_type": "VARCHAR(100)",
        "process": "VARCHAR(100)",
        "ingredient_class": "VARCHAR(100)",
    }
    missing = [
        (name, definition)
        for name, definition in columns.items()
        if name not in existing
    ]
    if not missing:
        return
    with db_engine.begin() as connection:
        for name, definition in missing:
            connection.execute(
                text(f"ALTER TABLE fineli_foods ADD COLUMN {name} {definition}")
            )
