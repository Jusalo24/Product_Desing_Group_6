from pathlib import Path

import pytest

from app import main
import app.scripts.import_fineli as fineli_importer
from app.integrations.fineli.local_client import LocalFineliClient
from app.models import FineliFood
from app.scripts.import_fineli import import_fineli, parse_number, read_rows

FILES = {
    "food.csv": (
        "FOODID;FOODNAME;FOODTYPE;PROCESS;EDPORT;IGCLASS;IGCLASSP;FUCLASS;FUCLASSP\n"
        "1;SOKERI;FOOD;IND;100;X;X;X;X\n"
        "2;HEDELMÄSOKERI;FOOD;IND;100;X;X;X;X\n"
        "3;SUOLA;FOOD;IND;100;X;X;X;X\n"
        "4;ÖLJY;FOOD;IND;100;X;X;X;X\n"
    ),
    "foodname_EN.csv": "FOODID;FOODNAME;LANG\n1;SUGAR;EN\n2;FRUIT SUGAR;EN\n4;OIL;EN\n",
    "component.csv": (
        "EUFDNAME;COMPUNIT;CMPCLASS;CMPCLASSP\n"
        "ENERC;KJ;A;A\nPROT;G;A;A\nCHOAVL;G;A;A\nFAT;G;A;A\nFIBT;G;A;A\n"
        "NACL;MG;A;A\nSUGAR;G;A;A\nFASAT;G;A;A\nNA;MG;A;A\n"
    ),
    "compunit_EN.csv": "THSCODE;DESCRIPT;LANG\nG;g;EN\nMG;mg;EN\nKJ;kJ;EN\n",
    "component_value.csv": (
        "FOODID;EUFDNAME;BESTLOC;ACQTYPE;METHTYPE;METHIND\n"
        "1;ENERC;1698,30;S;S;M\n1;FAT;0;F;E;M\n1;CHOAVL;99,900;S;S;M\n1;PROT;;S;S;M\n"
        "1;NA;5,0;S;S;M\n"
        "2;ENERC;1500,00;S;S;M\n2;FIBT;1,5;S;S;M\n"
        "3;NACL;39300,0;S;S;M\n"
        "4;ENERC;3700,0;S;S;M\n4;PROT;0;S;S;M\n4;CHOAVL;0;S;S;M\n4;FAT;100;S;S;M\n"
    ),
    "foodunit_EN.csv": "THSCODE;DESCRIPT;LANG\nPORTM;medium portion;EN\nTBSP;tablespoon;EN\n",
    "foodaddunit.csv": "FOODID;FOODUNIT;MASS\n1;TBSP;12,50\n1;PORTM;4,00\n99;TBSP;1,00\n",
}


def _write_fineli_files(data_dir: Path, files: dict[str, str] = FILES) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (data_dir / name).write_bytes(text.encode("latin-1"))


@pytest.fixture
def local_client(client, tmp_path: Path):
    _write_fineli_files(tmp_path)
    stats = import_fineli(tmp_path, engine=main.engine)
    assert stats == {"foods": 4, "food_units": 2, "with_energy": 3}
    return client


def test_parse_number_handles_decimal_comma_and_missing() -> None:
    assert parse_number("1698,30") == 1698.3
    assert parse_number("") is None
    assert parse_number("n/a") is None
    assert parse_number("0") == 0.0


def test_import_reports_progress_when_enabled(
    client, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_fineli_files(tmp_path)

    import_fineli(tmp_path, engine=main.engine, show_progress=True)

    output = capsys.readouterr().err
    assert "Processing nutrient values: complete" in output
    assert "Preparing food records: complete" in output
    assert "Saving unit conversions: complete" in output


def test_read_rows_handles_utf8_bom_and_finnish_characters(tmp_path: Path) -> None:
    csv_path = tmp_path / "food.csv"
    csv_path.write_text("FOODID;FOODNAME\n1;Hedelmä\n", encoding="utf-8-sig")

    assert read_rows(csv_path) == [{"FOODID": "1", "FOODNAME": "Hedelmä"}]


def test_import_converts_units_and_keeps_missing_as_null(local_client) -> None:
    food = local_client.get("/api/ingredients/1").json()
    values = food["nutrients_per_100g"]
    assert values["energy_kj"] == pytest.approx(1698.3)
    assert values["energy_kcal"] == pytest.approx(405.9, abs=0.05)
    assert values["carbohydrates_g"] == pytest.approx(99.9)
    assert values["fat_g"] == 0.0          # a real zero stays zero
    assert values["protein_g"] is None     # blank in the file stays missing
    assert food["name"] == "Sugar"
    assert food["source"]["provider"] == "Fineli"
    assert food["source"]["source_type"] == "dataset"

    salt = local_client.get("/api/ingredients/3").json()
    assert salt["nutrients_per_100g"]["salt_g"] == pytest.approx(39.3)  # mg -> g
    assert salt["name"] == "Suola"  # falls back to the Finnish name

    fiber = local_client.get("/api/ingredients/2").json()
    assert fiber["nutrients_per_100g"]["fiber_g"] == 1.5  # FIBT fallback


def test_search_matches_english_and_finnish_and_ranks_exact_first(local_client) -> None:
    names = [f["name"] for f in local_client.get("/api/ingredients/search", params={"q": "sugar"}).json()]
    assert names == ["Sugar", "Fruit sugar"]
    assert [f["id"] for f in local_client.get("/api/ingredients/search", params={"q": "hedelmä"}).json()] == ["2"]
    assert local_client.get("/api/ingredients/search", params={"q": "100%"}).json() == []


def test_unknown_food_is_404(local_client) -> None:
    assert local_client.get("/api/ingredients/424242").status_code == 404


def _recipe_with(
    client, fineli_id: str, quantity: float = 200, unit: str = "g"
) -> int:
    return client.post(
        "/api/recipes",
        json={
            "title": "Test",
            "ingredients": [{"name": "x", "quantity": quantity, "unit": unit, "fineli_id": fineli_id}],
        },
    ).json()["id"]


def test_recalculate_nutrition_from_local_dataset(local_client) -> None:
    response = local_client.post(f"/api/recipes/{_recipe_with(local_client, '4')}/nutrition/recalculate")
    assert response.status_code == 200
    values = response.json()["values"]
    assert values["fat_g"] == pytest.approx(200.0)       # 100 g/100 g * 200 g
    assert values["energy_kj"] == pytest.approx(7400.0)
    assert response.json()["source"]["provider"] == "Fineli"


def test_recalculate_converts_local_food_quantity_from_kilograms(local_client) -> None:
    response = local_client.post(
        f"/api/recipes/{_recipe_with(local_client, '4', 1, 'kg')}/nutrition/recalculate"
    )
    assert response.status_code == 200
    assert response.json()["values"]["fat_g"] == pytest.approx(1000)
    assert response.json()["values"]["energy_kj"] == pytest.approx(37000)


def test_recalculate_sums_multiple_local_food_ingredients(local_client) -> None:
    recipe = local_client.post(
        "/api/recipes",
        json={
            "title": "Mixed quantities",
            "ingredients": [
                {"name": "oil", "quantity": 1, "unit": "kg", "fineli_id": "4"},
                {"name": "oil", "quantity": 100, "unit": "g", "fineli_id": "4"},
            ],
        },
    )
    assert recipe.status_code == 201

    response = local_client.post(
        f"/api/recipes/{recipe.json()['id']}/nutrition/recalculate"
    )

    assert response.status_code == 200
    assert response.json()["values"]["fat_g"] == pytest.approx(1100)
    assert response.json()["values"]["energy_kj"] == pytest.approx(40700)


def test_recalculate_rejects_food_with_missing_required_nutrient(local_client) -> None:
    response = local_client.post(f"/api/recipes/{_recipe_with(local_client, '1')}/nutrition/recalculate")
    assert response.status_code == 422  # sugar has no protein value in the fixture


def test_recalculate_closes_local_client_when_validation_fails(
    local_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(LocalFineliClient, "close", lambda self: closed.append(True))
    recipe_id = _recipe_with(local_client, "1")

    response = local_client.post(f"/api/recipes/{recipe_id}/nutrition/recalculate")

    assert response.status_code == 422
    assert closed == [True]


def test_recalculate_rejects_unknown_fineli_id(local_client) -> None:
    response = local_client.post(f"/api/recipes/{_recipe_with(local_client, '999', 1)}/nutrition/recalculate")
    assert response.status_code == 422
    assert "999" in response.json()["detail"]


def test_import_reports_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="food.csv"):
        import_fineli(tmp_path, engine=main.engine)


def test_import_rerun_replaces_stale_food_rows(local_client, tmp_path: Path) -> None:
    replacement = dict(FILES)
    replacement["food.csv"] = (
        "FOODID;FOODNAME;FOODTYPE;PROCESS;EDPORT;IGCLASS;IGCLASSP;FUCLASS;FUCLASSP\n"
        "1;SOKERI;FOOD;IND;100;X;X;X;X\n"
    )
    _write_fineli_files(tmp_path, replacement)

    stats = import_fineli(tmp_path, engine=main.engine)

    assert stats["foods"] == 1
    assert local_client.get("/api/ingredients/1").status_code == 200
    assert local_client.get("/api/ingredients/4").status_code == 404


def test_failed_import_rolls_back_table_replacement(
    local_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement = dict(FILES)
    replacement["food.csv"] = (
        "FOODID;FOODNAME;FOODTYPE;PROCESS;EDPORT;IGCLASS;IGCLASSP;FUCLASS;FUCLASSP\n"
        "5;UUSI;FOOD;IND;100;X;X;X;X\n"
    )
    _write_fineli_files(tmp_path, replacement)
    original_insert = fineli_importer.insert

    def fail_food_insert(table):
        if table is FineliFood:
            raise RuntimeError("simulated insert failure")
        return original_insert(table)

    monkeypatch.setattr(fineli_importer, "insert", fail_food_insert)

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        import_fineli(tmp_path, engine=main.engine)

    assert local_client.get("/api/ingredients/4").status_code == 200
    assert local_client.get("/api/ingredients/5").status_code == 404


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            {
                **FILES,
                "component.csv": FILES["component.csv"].replace(
                    "ENERC;KJ;A;A\n", "ENERC;UNKNOWN;A;A\n"
                ),
            },
            "Unknown unit",
        ),
        (
            {
                **FILES,
                "component.csv": FILES["component.csv"].replace(
                    "ENERC;KJ;A;A\n", "ENERC;G;A;A\n"
                ),
            },
            "unexpected unit type g",
        ),
        (
            {
                **FILES,
                "component.csv": FILES["component.csv"].replace("ENERC;KJ;A;A\n", ""),
            },
            "Missing component unit definitions",
        ),
    ],
)
def test_import_rejects_unknown_or_missing_component_units(
    tmp_path: Path, files: dict[str, str], message: str
) -> None:
    _write_fineli_files(tmp_path, files)

    with pytest.raises(ValueError, match=message):
        import_fineli(tmp_path, engine=main.engine)
