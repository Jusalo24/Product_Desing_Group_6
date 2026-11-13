import json
from datetime import datetime, timezone
from pathlib import Path

from app import main
from app.integrations.fineli.matching import normalize_ingredient_name, suggestion_queries
from app.integrations.themealdb.client import TheMealDbClient
from app.scripts.import_fineli import import_fineli
from app.scripts.import_mappings import import_mappings
from tests.test_fineli_local import FILES, _write_fineli_files


def test_normalizes_modifiers_accents_and_common_plurals() -> None:
    assert normalize_ingredient_name(" Fresh, chopped Spring onions ") == "spring onion"
    assert normalize_ingredient_name("Tomatoes") == "tomato"
    assert normalize_ingredient_name("Hedelmä") == "hedelma"


def test_ingredient_aliases_broaden_search_without_replacing_user_query() -> None:
    assert suggestion_queries("Penne rigate") == ["macaroni pasta", "penne rigate"]
    assert suggestion_queries("Eggplant") == ["aubergine", "eggplant"]
    assert suggestion_queries("Green onions") == ["onion", "green onion"]
    assert suggestion_queries("plain flour") == ["wheat flour", "plain flour"]
    assert suggestion_queries("vegetable stock") == ["vegetable bouillon", "vegetable stock"]


def test_suggestions_rank_exact_candidates_and_do_not_mutate_matches(
    client, tmp_path: Path
) -> None:
    _write_fineli_files(tmp_path, FILES)
    import_fineli(tmp_path, engine=main.engine)
    recipe = client.post(
        "/api/recipes",
        json={"title": "Unmatched", "ingredients": [{"name": "sugars", "amount": "100 g"}]},
    ).json()

    response = client.get("/api/ingredients/suggestions", params={"q": "sugars"})

    assert response.status_code == 200
    assert [food["name"] for food in response.json()] == ["Sugar", "Fruit sugar"]
    assert len(response.json()) <= 5
    saved_ingredient = client.get(f"/api/recipes/{recipe['id']}").json()["ingredients"][0]
    assert saved_ingredient["fineli_id"] is None


def test_suggestion_query_must_be_nonempty(client) -> None:
    response = client.get("/api/ingredients/suggestions", params={"q": " "})

    assert response.status_code == 422


def test_import_mappings_and_auto_match_workflow(client, tmp_path: Path, monkeypatch) -> None:
    _write_fineli_files(tmp_path, FILES)
    import_fineli(tmp_path, engine=main.engine)

    mappings_file = tmp_path / "mappings.json"
    mappings_file.write_text(
        json.dumps(
            [
                {
                    "mealdb_name": "white sugar",
                    "raw_name": "White Sugar",
                    "fineli_id": "1",
                    "search_hint": "sugar",
                    "default_weight_g": 4.0,
                    "confidence": "high",
                    "notes": "Test mapping",
                }
            ]
        ),
        encoding="utf-8",
    )
    stats = import_mappings(mappings_file, engine=main.engine)
    assert stats == {"inserted": 1, "updated": 0}

    # Re-importing is idempotent
    stats_rerun = import_mappings(mappings_file, engine=main.engine)
    assert stats_rerun == {"inserted": 0, "updated": 1}

    # Manual recipe auto-match uses IngredientMapping and FineliFoodUnit (TBSP = 12.5g for id=1)
    created = client.post(
        "/api/recipes",
        json={
            "title": "Sweet tea",
            "ingredients": [{"name": "White Sugar", "amount": "2 tbsp"}],
        },
    ).json()
    matched = client.post(f"/api/recipes/{created['id']}/ingredients/auto-match")
    assert matched.status_code == 200
    ing = matched.json()["ingredients"][0]
    assert ing["fineli_id"] == "1"
    assert ing["fineli_name"] == "Sugar"
    assert ing["quantity"] == 25.0
    assert ing["unit"] == "g"
    assert ing["conversion_status"] == "estimated"

    # External import also pre-matches high-confidence mapped ingredients
    monkeypatch.setattr(
        TheMealDbClient,
        "get",
        lambda self, meal_id: {
            "external_id": meal_id,
            "name": "Sugar syrup",
            "category": "Dessert",
            "area": "British",
            "instructions": "Dissolve sugar.",
            "thumbnail_url": None,
            "source_url": None,
            "youtube_url": None,
            "tags": [],
            "creative_commons_confirmed": None,
            "ingredients": [{"name": "White Sugar", "amount": "1 tbsp"}],
            "source": {
                "provider": "TheMealDB",
                "source_type": "external_api",
                "external_id": meal_id,
                "source_url": f"https://www.themealdb.com/meal/{meal_id}",
                "retrieved_at": datetime.now(timezone.utc),
                "attribution_text": "Recipe data provided by TheMealDB",
            },
        },
    )
    imported = client.post("/api/external-recipes/id/88888/import")
    assert imported.status_code == 201
    imported_ing = imported.json()["ingredients"][0]
    assert imported_ing["fineli_id"] == "1"
    assert imported_ing["quantity"] == 12.5
    assert imported_ing["unit"] == "g"


def test_search_prefers_basic_food_over_composite_dish(client, tmp_path: Path) -> None:
    files = dict(FILES)
    files["food.csv"] = (
        "FOODID;FOODNAME;FOODTYPE;PROCESS;EDPORT;IGCLASS;IGCLASSP;FUCLASS;FUCLASSP\n"
        "10;OMENAKEITTO;DISH;BOIL;100;X;X;X;X\n"
        "11;OMENA;FOOD;RAW;100;X;X;X;X\n"
    )
    files["foodname_EN.csv"] = (
        "FOODID;FOODNAME;LANG\n"
        "10;APPLE SOUP;EN\n"
        "11;APPLE;EN\n"
    )
    _write_fineli_files(tmp_path, files)
    import_fineli(tmp_path, engine=main.engine)

    results = client.get("/api/ingredients/search", params={"q": "apple"}).json()
    assert [food["id"] for food in results] == ["11", "10"]
