import httpx

from app.integrations.fineli.client import FineliClient


def test_fineli_client_maps_food_search_response() -> None:
    payload = [
        {
            "id": 123,
            "name": "Carrot",
            "nutrients": {
                "energy_kcal": 41,
                "energy_kj": 172,
                "protein": 0.9,
                "carbohydrates": 9.6,
                "fat": 0.2,
                "fiber": 2.8,
                "salt": 0.1,
            },
        }
    ]
    client = FineliClient(
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        )
    )

    foods = client.search_foods("carrot")

    assert foods[0]["id"] == "123"
    assert foods[0]["name"] == "Carrot"
    assert foods[0]["nutrients_per_100g"]["protein_g"] == 0.9
    assert foods[0]["source"]["provider"] == "Fineli"
    assert foods[0]["source"]["external_id"] == "123"


def test_fineli_client_maps_single_food_response() -> None:
    client = FineliClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "food": {
                            "foodId": "456",
                            "foodName": "Potato",
                            "nutrition": {
                                "energyKcal": 77,
                                "energyKj": 322,
                                "protein": 2,
                                "carbohydrates": 17,
                                "fat": 0.1,
                            },
                        }
                    },
                )
            )
        )
    )

    food = client.get_food("456")

    assert food["id"] == "456"
    assert food["nutrients_per_100g"]["energy_kcal"] == 77


def test_fineli_client_raises_for_provider_error() -> None:
    client = FineliClient(
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        )
    )

    from app.integrations.fineli.client import ExternalProviderError

    try:
        client.search_foods("carrot")
    except ExternalProviderError:
        pass
    else:
        raise AssertionError("Expected ExternalProviderError")
