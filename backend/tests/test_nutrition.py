from datetime import datetime, timezone

import pytest

from app.integrations.fineli.local_client import LocalFineliClient


def fineli_food(food_id: str = "1") -> dict:
    return {
        "id": food_id,
        "name": "Test food",
        "nutrients_per_100g": {
            "energy_kcal": 100,
            "energy_kj": 418,
            "protein_g": 10,
            "carbohydrates_g": 20,
            "fat_g": 5,
            "fiber_g": 2,
            "salt_g": 1,
            "sugars_g": None,
            "saturated_fat_g": None,
        },
        "source": {
            "provider": "Fineli",
            "source_type": "dataset",
            "external_id": food_id,
            "source_url": f"https://fineli.test/{food_id}",
            "retrieved_at": datetime.now(timezone.utc),
            "attribution_text": "Source: Fineli",
        },
    }


def mock_fineli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: fineli_food(food_id),
    )


def create_recipe(client, unit: str = "g"):
    response = client.post(
        "/api/recipes",
        json={
            "title": "Nutrition test",
            "ingredients": [
                {
                    "name": "Test food",
                    "quantity": 100 if unit == "g" else 1,
                    "unit": unit,
                    "fineli_id": "1",
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()["id"], response.json()["ingredients"][0]["id"]


def test_recalculate_uses_grams_and_returns_total(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    recipe_id, _ = create_recipe(client)

    response = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert response.status_code == 200
    assert response.json()["values"]["energy_kcal"] == 100
    assert response.json()["values"]["protein_g"] == 10
    assert response.json()["status"] == "completed"


def test_recalculate_returns_partial_detailed_totals_and_snapshots(client, monkeypatch) -> None:
    food = fineli_food()
    food["detailed_nutrients"] = [
        {"code": "ENERC", "name": "Energy", "unit": "kcal", "group": "Energy", "value_per_100g": 100},
        {"code": "PROT", "name": "Protein", "unit": "g", "group": "Macronutrients", "value_per_100g": 10},
    ]
    food["nutrients_per_100g"]["fiber_g"] = None
    monkeypatch.setattr(LocalFineliClient, "get_food", lambda self, food_id: food)
    recipe = client.post(
        "/api/recipes",
        json={
            "title": "Partial estimate",
            "servings": 2,
            "ingredients": [
                {"name": "Included", "quantity": 100, "unit": "g", "fineli_id": "1"},
                {"name": "Unmatched"},
            ],
        },
    ).json()

    response = client.post(f"/api/recipes/{recipe['id']}/nutrition/recalculate")

    assert response.status_code == 200
    result = response.json()
    assert result["values"]["energy_kcal"] == pytest.approx(100)
    assert result["values"]["fiber_g"] is None
    assert result["detailed_totals"] == [
        {
            "code": "ENERC",
            "name": "Energy",
            "unit": "kcal",
            "value": 100,
            "group": "Energy",
            "per_serving": 50,
        },
        {
            "code": "PROT",
            "name": "Protein",
            "unit": "g",
            "value": 10,
            "group": "Macronutrients",
            "per_serving": 5,
        },
    ]
    assert result["coverage"] == {
        "total_ingredients": 2,
        "included_ingredients": 1,
        "ratio": 0.5,
    }
    assert [item["status"] for item in result["ingredient_results"]] == ["included", "skipped"]
    assert result["ingredient_results"][1]["reason"] == "unmatched"
    saved = client.get(f"/api/recipes/{recipe['id']}/nutrition").json()
    assert saved["ingredient_results"] == result["ingredient_results"]


def test_recalculate_with_zero_coverage_returns_unknown_totals(client) -> None:
    recipe = client.post(
        "/api/recipes",
        json={"title": "No estimate", "ingredients": [{"name": "Unmatched"}]},
    ).json()

    response = client.post(f"/api/recipes/{recipe['id']}/nutrition/recalculate")

    assert response.status_code == 200
    result = response.json()
    assert all(value is None for value in result["values"].values())
    assert result["detailed_totals"] == []
    assert result["coverage"] == {
        "total_ingredients": 1,
        "included_ingredients": 0,
        "ratio": 0,
    }
    assert result["ingredient_results"][0]["reason"] == "unmatched"


def test_recalculate_reports_unknown_quantity_and_missing_nutrients(client, monkeypatch) -> None:
    food_without_nutrients = fineli_food("2")
    food_without_nutrients["nutrients_per_100g"] = {
        key: None for key in food_without_nutrients["nutrients_per_100g"]
    }
    food_without_nutrients["detailed_nutrients"] = []

    def get_food(_self, food_id: str) -> dict:
        return food_without_nutrients if food_id == "2" else fineli_food(food_id)

    monkeypatch.setattr(LocalFineliClient, "get_food", get_food)
    recipe = client.post(
        "/api/recipes",
        json={
            "title": "Skipped reasons",
            "ingredients": [
                {"name": "No weight", "fineli_id": "1"},
                {"name": "No data", "quantity": 100, "unit": "g", "fineli_id": "2"},
            ],
        },
    ).json()

    response = client.post(f"/api/recipes/{recipe['id']}/nutrition/recalculate")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unavailable"
    assert result["coverage"]["included_ingredients"] == 0
    assert [item["reason"] for item in result["ingredient_results"]] == [
        "unknown_quantity",
        "missing_nutrients",
    ]


def test_recalculate_converts_kilograms_to_grams(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    recipe_id, _ = create_recipe(client, unit="kg")

    response = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert response.status_code == 200
    assert response.json()["values"]["energy_kcal"] == 1000


def test_recalculate_skips_missing_fineli_match(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    response = client.post(
        "/api/recipes",
        json={"title": "Unmatched", "ingredients": [{"name": "Unknown", "quantity": 100, "unit": "g"}]},
    )
    recipe_id = response.json()["id"]

    calculation = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert calculation.status_code == 200
    assert calculation.json()["status"] == "unavailable"
    assert calculation.json()["ingredient_results"][0]["reason"] == "unmatched"


def test_matching_ingredient_and_recalculation_versioning(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    recipe_id, ingredient_id = create_recipe(client)

    first = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")
    assert first.status_code == 200
    first_run_id = first.json()["calculation_run_id"]

    match = client.put(
        f"/api/recipes/{recipe_id}/ingredients/{ingredient_id}/nutrition-source",
        json={"name": "Test food", "quantity": 200, "unit": "g", "fineli_id": "1"},
    )
    assert match.status_code == 200

    assert client.get(f"/api/recipes/{recipe_id}/nutrition").status_code == 404

    second = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")
    assert second.status_code == 200
    assert second.json()["calculation_run_id"] != first_run_id
    assert second.json()["values"]["energy_kcal"] == 200


def test_fineli_match_can_be_confirmed_without_quantity(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    created = client.post(
        "/api/recipes",
        json={
            "title": "Original measures",
            "ingredients": [{"name": "Olive oil", "amount": "1 tbsp"}],
        },
    ).json()
    ingredient = created["ingredients"][0]

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients/{ingredient['id']}/nutrition-source",
        json={"fineli_id": "1"},
    )

    assert response.status_code == 200
    assert response.json()["fineli_id"] == "1"
    assert response.json()["fineli_name"] == "Test food"
    assert response.json()["amount"] == "1 tbsp"
    assert response.json()["quantity"] is None
    assert response.json()["unit"] is None
