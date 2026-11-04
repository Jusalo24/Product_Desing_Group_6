import httpx

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.config import settings
from app.database import Base
from app.routers import external_recipes
from app.integrations.themealdb.client import TheMealDbClient


def meal_payload() -> dict:
    return {
        "meals": [
            {
                "idMeal": "52771",
                "strMeal": "Spicy Arrabiata Penne",
                "strCategory": "Vegetarian",
                "strArea": "Italian",
                "strInstructions": "Cook the pasta.",
                "strMealThumb": "https://example.test/meal.jpg",
                "strYoutube": "https://youtube.com/watch?v=example",
                "strIngredient1": "Penne",
                "strMeasure1": "200g",
                "strIngredient2": "Tomato",
                "strMeasure2": "1 tin",
                "strIngredient3": "",
                "strMeasure3": "",
            }
        ]
    }


def test_themealdb_client_maps_meal_and_ingredients() -> None:
    client = TheMealDbClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=meal_payload())
            )
        )
    )

    meals = client.search("Arrabiata")

    assert meals[0]["external_id"] == "52771"
    assert meals[0]["name"] == "Spicy Arrabiata Penne"
    assert meals[0]["ingredients"] == [
        {"name": "Penne", "amount": "200g"},
        {"name": "Tomato", "amount": "1 tin"},
    ]
    assert meals[0]["youtube_url"] == "https://youtube.com/watch?v=example"
    assert meals[0]["source"]["provider"] == "TheMealDB"


def test_meal_search_route_matches_frontend_contract(client, monkeypatch) -> None:
    from app.integrations.themealdb.client import TheMealDbClient

    def fake_search(self, query: str) -> list[dict]:
        assert query == "Arrabiata"
        return [
            {
                "external_id": "52771",
                "name": "Spicy Arrabiata Penne",
                "category": "Vegetarian",
                "area": "Italian",
                "instructions": "Cook the pasta.",
                "thumbnail_url": "https://example.test/meal.jpg",
                "tags": ["Pasta"],
                "youtube_url": "https://youtube.com/watch?v=example",
                "source_url": "https://example.test/recipe",
                "creative_commons_confirmed": None,
                "ingredients": [{"name": "Penne", "amount": "200g"}],
                "source": {},
            }
        ]

    monkeypatch.setattr(TheMealDbClient, "search", fake_search)

    response = client.get("/api/meals/search", params={"q": "Arrabiata"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "52771",
            "name": "Spicy Arrabiata Penne",
            "category": "Vegetarian",
            "area": "Italian",
            "instructions": "Cook the pasta.",
            "imageUrl": "https://example.test/meal.jpg",
            "tags": ["Pasta"],
            "youtubeUrl": "https://youtube.com/watch?v=example",
            "sourceUrl": "https://example.test/recipe",
            "creativeCommonsConfirmed": None,
            "ingredients": [{"name": "Penne", "measure": "200g"}],
        }
    ]


def test_themealdb_client_uses_configured_key_with_legacy_base_url(monkeypatch) -> None:
    requests = []
    client = TheMealDbClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (
                    requests.append(request)
                    or httpx.Response(200, json=meal_payload())
                )
            )
        )
    )
    monkeypatch.setattr(
        settings,
        "themealdb_api_base_url",
        "https://www.themealdb.com/api/json/v1/1",
    )
    monkeypatch.setattr(settings, "themealdb_api_key", "987")

    client.search("Arrabiata")

    assert str(requests[0].url) == (
        "https://www.themealdb.com/api/json/v1/987/search.php?s=Arrabiata"
    )


def test_themealdb_client_returns_none_for_missing_meal() -> None:
    client = TheMealDbClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"meals": None})
            )
        )
    )

    assert client.get("99999") is None


def test_themealdb_client_raises_for_invalid_response() -> None:
    client = TheMealDbClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"unexpected": []})
            )
        )
    )

    from app.integrations.fineli.client import ExternalProviderError

    try:
        client.search("anything")
    except ExternalProviderError:
        pass
    else:
        raise AssertionError("Expected ExternalProviderError")


def test_themealdb_search_cache_reuses_unexpired_response(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(external_recipes, "SessionLocal", session_factory)
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return [{"external_id": "1", "source": {"retrieved_at": "now"}}]

    first = external_recipes._cached_meals("search", {"query": "pasta"}, loader)
    second = external_recipes._cached_meals("search", {"query": "pasta"}, loader)

    assert first == second
    assert calls == 1
