import pytest

from app.integrations.fineli.measure import convert_measure_to_grams


@pytest.mark.parametrize(
    ("measure", "grams"),
    [("200g", 200), ("1.5 kg", 1500), ("1,5 kilograms", 1500), ("1/2 kg", 500)],
)
def test_converts_metric_measures_without_dataset_units(measure: str, grams: float) -> None:
    result = convert_measure_to_grams(measure, [])

    assert result is not None
    assert result.grams == pytest.approx(grams)
    assert result.status == "exact"


def test_converts_food_specific_household_unit_and_fraction() -> None:
    result = convert_measure_to_grams(
        "1/2 tbsp",
        [{"code": "RKL", "name": "tablespoon", "grams": 13.5}],
    )

    assert result is not None
    assert result.grams == pytest.approx(6.75)
    assert result.status == "estimated"


@pytest.mark.parametrize(
    "measure",
    ["", "a pinch", "1 cup", "1-2 tbsp", "2 pieces", "1/0 kg", "0 g", "1 tbsp chopped"],
)
def test_leaves_unknown_or_ambiguous_measure_unconverted(measure: str) -> None:
    assert convert_measure_to_grams(
        measure,
        [
            {"code": "KPL_S", "name": "small piece", "grams": 12},
            {"code": "KPL_M", "name": "medium-sized piece", "grams": 20},
        ],
    ) is None


def test_finds_exact_household_unit_among_similarly_named_options() -> None:
    result = convert_measure_to_grams(
        "2 medium-sized pieces",
        [
            {"code": "KPL_S", "name": "small piece", "grams": 12},
            {"code": "KPL_M", "name": "medium-sized piece", "grams": 20},
        ],
    )

    assert result is not None
    assert result.grams == 40
