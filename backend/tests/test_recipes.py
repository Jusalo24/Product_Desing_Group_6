import pytest
from fastapi.testclient import TestClient


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
