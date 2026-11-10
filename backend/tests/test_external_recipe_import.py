from datetime import datetime, timezone

from app.integrations.fineli.client import ExternalProviderError
from app.integrations.themealdb.client import TheMealDbClient


def _meal(external_id: str = "52771") -> dict:
    return {
        "external_id": external_id,
        "name": "Spicy Arrabiata Penne",
        "category": "Vegetarian",
        "area": "Italian",
        "instructions": "Cook the pasta.",
        "thumbnail_url": "https://example.test/meal.jpg",
        "source_url": "https://example.test/original",
        "youtube_url": "https://youtube.test/video",
        "tags": ["Pasta"],
        "creative_commons_confirmed": "Yes",
        "ingredients": [
            {"name": "penne rigate", "amount": "200g"},
            {"name": "olive oil", "amount": "1 tbsp"},
        ],
        "source": {
            "provider": "TheMealDB",
            "source_type": "external_api",
            "external_id": external_id,
            "source_url": f"https://www.themealdb.com/meal/{external_id}",
            "retrieved_at": datetime.now(timezone.utc),
            "attribution_text": "Recipe data provided by TheMealDB",
        },
    }


def test_import_meal_preserves_ingredients_and_source_metadata(client, monkeypatch) -> None:
    monkeypatch.setattr(TheMealDbClient, "get", lambda self, meal_id: _meal(meal_id))

    response = client.post("/api/external-recipes/id/52771/import")

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Spicy Arrabiata Penne"
    assert [item["amount"] for item in body["ingredients"]] == ["200g", "1 tbsp"]
    assert body["source"]["provider"] == "TheMealDB"
    assert body["source"]["external_id"] == "52771"
    assert body["source"]["source_url"] == "https://example.test/original"
    assert body["source"]["provider_url"] == "https://www.themealdb.com/meal/52771"
    assert body["source"]["image_url"] == "https://example.test/meal.jpg"
    assert body["source"]["extra_data"]["creative_commons_confirmed"] == "Yes"


def test_importing_same_meal_is_idempotent(client, monkeypatch) -> None:
    monkeypatch.setattr(TheMealDbClient, "get", lambda self, meal_id: _meal(meal_id))

    first = client.post("/api/external-recipes/id/52771/import")
    second = client.post("/api/external-recipes/id/52771/import")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/recipes").json()) == 1


def test_import_unknown_meal_returns_404(client, monkeypatch) -> None:
    monkeypatch.setattr(TheMealDbClient, "get", lambda self, _meal_id: None)

    response = client.post("/api/external-recipes/id/99999/import")

    assert response.status_code == 404


def test_import_provider_failure_returns_gateway_error(client, monkeypatch) -> None:
    def fail(_self, _meal_id):
        raise ExternalProviderError("provider unavailable")

    monkeypatch.setattr(TheMealDbClient, "get", fail)

    response = client.post("/api/external-recipes/id/52771/import")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "external_provider_unavailable"
