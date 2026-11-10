from pathlib import Path

from app import main
from app.integrations.fineli.matching import normalize_ingredient_name
from app.scripts.import_fineli import import_fineli
from tests.test_fineli_local import FILES, _write_fineli_files


def test_normalizes_modifiers_accents_and_common_plurals() -> None:
    assert normalize_ingredient_name(" Fresh, chopped Spring onions ") == "spring onion"
    assert normalize_ingredient_name("Tomatoes") == "tomato"
    assert normalize_ingredient_name("Hedelmä") == "hedelma"


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
