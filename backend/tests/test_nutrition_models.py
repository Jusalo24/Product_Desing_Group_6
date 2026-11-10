from sqlalchemy import create_engine, inspect, text

from app.database import Base, ensure_recipe_source_columns
from app.models import (
    FineliComponent,
    FineliFoodNutrient,
    NutritionIngredientResult,
    RecipeSource,
)


def test_detailed_nutrition_and_provenance_tables_are_registered() -> None:
    expected_tables = {
        "fineli_components",
        "fineli_food_nutrients",
        "nutrition_ingredient_results",
        "recipe_sources",
    }

    assert expected_tables <= set(Base.metadata.tables)
    assert FineliComponent.__tablename__ == "fineli_components"
    assert FineliFoodNutrient.__tablename__ == "fineli_food_nutrients"
    assert NutritionIngredientResult.__tablename__ == "nutrition_ingredient_results"
    assert RecipeSource.__tablename__ == "recipe_sources"


def test_fresh_database_can_create_new_nutrition_tables() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)

    table_names = set(inspect(engine).get_table_names())
    assert {
        "fineli_components",
        "fineli_food_nutrients",
        "nutrition_ingredient_results",
        "recipe_sources",
    } <= table_names
    engine.dispose()


def test_recipe_source_migration_adds_missing_columns_and_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE recipe_sources ("
                "id INTEGER PRIMARY KEY, recipe_id INTEGER NOT NULL, "
                "provider VARCHAR(50) NOT NULL, external_id VARCHAR(100) NOT NULL, "
                "source_url VARCHAR(1000), attribution_text TEXT NOT NULL, "
                "retrieved_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO recipe_sources "
                "(id, recipe_id, provider, external_id, attribution_text) "
                "VALUES (1, 1, 'TheMealDB', 'meal-1', 'Attribution')"
            )
        )

    ensure_recipe_source_columns(engine)
    ensure_recipe_source_columns(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("recipe_sources")}
    assert {"provider_url", "image_url", "extra_data"} <= columns
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT extra_data FROM recipe_sources WHERE id = 1")
        ).scalar_one() == "{}"
    engine.dispose()
