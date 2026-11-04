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


def test_recalculate_converts_kilograms_to_grams(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    recipe_id, _ = create_recipe(client, unit="kg")

    response = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert response.status_code == 200
    assert response.json()["values"]["energy_kcal"] == 1000


def test_recalculate_rejects_missing_fineli_match(client, monkeypatch) -> None:
    mock_fineli(monkeypatch)
    response = client.post(
        "/api/recipes",
        json={"title": "Unmatched", "ingredients": [{"name": "Unknown", "quantity": 100, "unit": "g"}]},
    )
    recipe_id = response.json()["id"]

    calculation = client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert calculation.status_code == 422


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
