import pytest
from fastapi.testclient import TestClient

from app.integrations.fineli.local_client import (
    FineliFoodNotFound,
    LocalFineliClient,
)


def test_health_returns_ok(client: TestClient) -> None:
    """The health endpoint responds with its expected status payload."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_recipes_is_empty_initially(client: TestClient) -> None:
    """A fresh test database returns an empty recipe list."""
    response = client.get("/api/recipes")

    assert response.status_code == 200
    assert response.json() == []


def test_recipe_create_read_and_list(client: TestClient) -> None:
    """Created recipes and ingredients persist and appear in detail and list responses."""
    payload = {
        "title": "Tomato soup",
        "description": "A simple soup",
        "instructions": "Simmer the tomatoes.",
        "prep_minutes": 25,
        "servings": 4,
        "ingredients": [
            {"name": "Tomatoes", "amount": "500 g"},
            {"name": "Salt", "amount": "1 tsp"},
        ],
    }

    created_response = client.post("/api/recipes", json=payload)

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["id"] > 0
    assert created["title"] == payload["title"]
    assert created["description"] == payload["description"]
    assert created["instructions"] == payload["instructions"]
    assert created["prep_minutes"] == payload["prep_minutes"]
    assert created["servings"] == payload["servings"]
    assert created["created_at"]
    assert [
        {"name": item["name"], "amount": item["amount"]}
        for item in created["ingredients"]
    ] == payload["ingredients"]

    read_response = client.get(f"/api/recipes/{created['id']}")

    assert read_response.status_code == 200
    assert read_response.json() == created

    list_response = client.get("/api/recipes")

    assert list_response.status_code == 200
    assert created in list_response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"title": ""},
        {"title": "Soup", "prep_minutes": -1},
        {"title": "Soup", "servings": 0},
        {"title": "Soup", "ingredients": [{"name": ""}]},
    ],
)
def test_invalid_recipe_payload_is_rejected_without_persisting(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Invalid titles, quantities, servings, or ingredients fail validation without writes."""
    response = client.post("/api/recipes", json=payload)

    assert response.status_code == 422
    assert client.get("/api/recipes").json() == []


def test_unknown_recipe_returns_not_found(client: TestClient) -> None:
    """Reading or deleting an ID absent from the database returns 404."""
    recipe_id = 2_147_483_647

    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 404


def test_delete_removes_recipe(client: TestClient) -> None:
    """Deleting a saved recipe returns 204 and removes it from subsequent reads."""
    created_response = client.post(
        "/api/recipes",
        json={"title": "Toast", "ingredients": [{"name": "Bread"}]},
    )
    assert created_response.status_code == 201
    recipe_id = created_response.json()["id"]

    delete_response = client.delete(f"/api/recipes/{recipe_id}")

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404
    assert client.get("/api/recipes").json() == []


def test_ingredients_can_be_edited(client: TestClient) -> None:
    """Editing ingredient amounts keeps the recipe and Fineli match intact."""
    created = client.post(
        "/api/recipes",
        json={
            "title": "Porridge",
            "ingredients": [
                {
                    "name": "Oats",
                    "amount": "100 g",
                    "quantity": 100,
                    "unit": "g",
                    "fineli_id": "food-1",
                }
            ],
        },
    ).json()

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Oats",
                    "amount": "0.5 kg",
                    "quantity": 0.5,
                    "unit": "kg",
                    "fineli_id": "food-1",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["ingredients"][0]["amount"] == "0.5 kg"
    assert response.json()["ingredients"][0]["unit"] == "kg"


def test_ingredient_edit_reconciles_explicit_quantity_with_amount(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: {
            "id": food_id,
            "name": "Oats",
            "units": [],
        },
    )
    created = client.post(
        "/api/recipes",
        json={
            "title": "Porridge",
            "ingredients": [
                {
                    "name": "Oats",
                    "amount": "100 g",
                    "quantity": 100,
                    "unit": "g",
                    "fineli_id": "food-1",
                }
            ],
        },
    ).json()

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Oats",
                    "amount": "100 g",
                    "quantity": 200,
                    "unit": "g",
                    "fineli_id": "food-1",
                }
            ]
        },
    )

    assert response.status_code == 200
    ingredient = response.json()["ingredients"][0]
    assert ingredient["quantity"] == 100
    assert ingredient["unit"] == "g"
    assert ingredient["conversion_status"] == "exact"


def test_ingredient_edit_clears_match_and_quantity_when_unmatched(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/recipes",
        json={
            "title": "Plain water",
            "ingredients": [
                {
                    "name": "Water",
                    "amount": "1 l",
                    "quantity": 1000,
                    "unit": "g",
                    "fineli_id": "food-1",
                }
            ],
        },
    ).json()

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Water",
                    "amount": "1 l",
                    "quantity": 1000,
                    "unit": "g",
                    "fineli_id": None,
                }
            ]
        },
    )

    assert response.status_code == 200
    ingredient = response.json()["ingredients"][0]
    assert ingredient["fineli_id"] is None
    assert ingredient["fineli_name"] is None
    assert ingredient["quantity"] is None
    assert ingredient["unit"] is None
    assert ingredient["conversion_status"] == "unmatched"


@pytest.mark.parametrize(
    ("amount", "quantity", "unit", "expected_status"),
    [
        ("2 tbsp", None, None, "estimated"),
        ("to taste", None, None, "negligible"),
    ],
)
def test_ingredient_edit_recalculates_quantified_and_negligible_amounts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    amount: str,
    quantity: float | None,
    unit: str | None,
    expected_status: str,
) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: {
            "id": food_id,
            "name": "Olive oil",
            "units": [{"code": "RKL", "name": "tablespoon", "grams": 15}],
        },
    )
    created = client.post(
        "/api/recipes",
        json={
            "title": "Oil",
            "ingredients": [{"name": "Olive oil", "amount": "1 tbsp"}],
        },
    ).json()

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Olive oil",
                    "amount": amount,
                    "quantity": quantity,
                    "unit": unit,
                    "fineli_id": "food-1",
                }
            ]
        },
    )

    assert response.status_code == 200
    ingredient = response.json()["ingredients"][0]
    assert ingredient["conversion_status"] == expected_status
    if expected_status == "estimated":
        assert ingredient["quantity"] == 30
        assert ingredient["unit"] == "g"
    else:
        assert ingredient["quantity"] is None
        assert ingredient["unit"] is None


def test_ingredient_edit_handles_missing_mapped_fineli_food(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_food(self, food_id: str) -> dict:
        raise FineliFoodNotFound(food_id)

    monkeypatch.setattr(LocalFineliClient, "get_food", missing_food)
    created = client.post(
        "/api/recipes",
        json={
            "title": "Missing source",
            "ingredients": [{"name": "Mystery", "amount": "100 g"}],
        },
    ).json()

    response = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Mystery",
                    "amount": "100 g",
                    "quantity": None,
                    "unit": None,
                    "fineli_id": "deleted-food",
                }
            ]
        },
    )

    assert response.status_code == 200
    ingredient = response.json()["ingredients"][0]
    assert ingredient["fineli_name"] is None
    assert ingredient["quantity"] is None
    assert ingredient["unit"] is None
    assert ingredient["conversion_status"] == "unknown"


def test_create_recipe_populates_fineli_name_and_conversion_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: {
            "id": food_id,
            "name": "Olive oil",
            "units": [{"code": "RKL", "name": "tablespoon", "grams": 13.5}],
        },
    )
    response = client.post(
        "/api/recipes",
        json={
            "title": "Dressing",
            "ingredients": [
                {
                    "name": "Olive oil",
                    "amount": "20 g",
                    "quantity": 20,
                    "unit": "g",
                    "fineli_id": "100",
                },
                {
                    "name": "Olive oil",
                    "amount": "2 tbsp",
                    "fineli_id": "100",
                },
            ],
        },
    )

    assert response.status_code == 201
    exact_ing, estimated_ing = response.json()["ingredients"]
    assert exact_ing["fineli_name"] == "Olive oil"
    assert exact_ing["conversion_status"] == "exact"
    assert estimated_ing["fineli_name"] == "Olive oil"
    assert estimated_ing["quantity"] == pytest.approx(27.0)
    assert estimated_ing["unit"] == "g"
    assert estimated_ing["conversion_status"] == "estimated"


def test_reconfirming_same_fineli_match_preserves_estimated_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: {
            "id": food_id,
            "name": "Olive oil",
            "units": [{"code": "RKL", "name": "tablespoon", "grams": 13.5}],
        },
    )
    created = client.post(
        "/api/recipes",
        json={
            "title": "Oil",
            "ingredients": [{"name": "Olive oil", "amount": "2 tbsp"}],
        },
    ).json()
    ing_id = created["ingredients"][0]["id"]

    first = client.put(
        f"/api/recipes/{created['id']}/ingredients/{ing_id}/nutrition-source",
        json={"fineli_id": "100"},
    )
    assert first.status_code == 200
    assert first.json()["conversion_status"] == "estimated"

    second = client.put(
        f"/api/recipes/{created['id']}/ingredients/{ing_id}/nutrition-source",
        json={"fineli_id": "100"},
    )
    assert second.status_code == 200
    assert second.json()["conversion_status"] == "estimated"


def test_update_ingredients_uses_mapping_default_weight(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        LocalFineliClient,
        "get_food",
        lambda self, food_id: {
            "id": food_id,
            "name": "Avocado, without skin and stone",
            "units": [],
        },
    )
    created = client.post(
        "/api/recipes",
        json={
            "title": "Guacamole",
            "ingredients": [{"name": "Avocado", "amount": "2 whole"}],
        },
    ).json()

    updated = client.put(
        f"/api/recipes/{created['id']}/ingredients",
        json={
            "ingredients": [
                {
                    "name": "Avocado",
                    "amount": "2 whole",
                    "quantity": None,
                    "unit": None,
                    "fineli_id": "11057",
                }
            ]
        },
    )
    assert updated.status_code == 200
    ing = updated.json()["ingredients"][0]
    assert ing["quantity"] == pytest.approx(300.0)
    assert ing["unit"] == "g"
    assert ing["conversion_status"] == "estimated"
