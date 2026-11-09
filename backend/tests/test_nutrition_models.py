from sqlalchemy import create_engine, inspect

from app.database import Base
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
