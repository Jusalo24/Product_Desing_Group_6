import pytest

from app.integrations.fineli.measure import convert_measure_to_grams


@pytest.mark.parametrize(
    ("measure", "grams"),
    [
        ("200g", 200),
        ("1.5 kg", 1500),
        ("1,5 kilograms", 1500),
        ("1/2 kg", 500),
        ("1½ kg", 1500),
        ("4 oz", pytest.approx(113.398, rel=1e-3)),
        ("1 lb", pytest.approx(453.592, rel=1e-3)),
        ("200g, drained", 200),
        ("1 can (400g)", 400),
    ],
)
def test_converts_metric_and_imperial_mass_measures(measure: str, grams: float) -> None:
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


def test_converts_range_and_trailing_modifiers() -> None:
    units = [{"code": "RKL", "name": "tablespoon", "grams": 13.5}]

    range_result = convert_measure_to_grams("1-2 tbsp", units)
    assert range_result is not None
    assert range_result.grams == pytest.approx(20.25)
    assert range_result.status == "estimated"

    chopped_result = convert_measure_to_grams("1 tbsp chopped", units)
    assert chopped_result is not None
    assert chopped_result.grams == pytest.approx(13.5)
    assert chopped_result.status == "estimated"


def test_bridges_volume_measures_via_fineli_dl_and_density_fallback() -> None:
    # Flour: 1 dl = 65 g -> 1 cup (240 ml = 2.4 dl) = 156 g
    flour_cup = convert_measure_to_grams(
        "1 cup",
        [{"code": "DL", "name": "decilitre", "grams": 65.0}],
        ingredient_name="Wheat flour",
    )
    assert flour_cup is not None
    assert flour_cup.grams == pytest.approx(156.0)
    assert flour_cup.status == "estimated"

    # Without Fineli DL unit, falls back to ingredient density (oil ~0.91 g/ml)
    oil_tbs = convert_measure_to_grams("2 tbs", [], ingredient_name="Olive oil")
    assert oil_tbs is not None
    assert oil_tbs.grams == pytest.approx(30 * 0.91)
    assert oil_tbs.status == "estimated"

    # Water / generic liquid fallback: 150 ml = 150 g
    water_ml = convert_measure_to_grams("150 ml", [])
    assert water_ml is not None
    assert water_ml.grams == pytest.approx(150.0)
    assert water_ml.status == "estimated"


def test_converts_countable_pieces_cloves_and_bare_numbers() -> None:
    egg_units = [{"code": "KPL_M", "name": "medium-sized piece", "grams": 55.0}]

    bare_eggs = convert_measure_to_grams("2", egg_units)
    assert bare_eggs is not None
    assert bare_eggs.grams == pytest.approx(110.0)
    assert bare_eggs.status == "estimated"

    large_eggs = convert_measure_to_grams("2 large", egg_units)
    assert large_eggs is not None
    assert large_eggs.grams == pytest.approx(2 * 55.0 * 1.35)
    assert large_eggs.status == "estimated"

    cloves = convert_measure_to_grams("3 cloves", [])
    assert cloves is not None
    assert cloves.grams == pytest.approx(15.0)
    assert cloves.status == "estimated"

    default_piece = convert_measure_to_grams("2 whole", [], default_weight_g=110.0)
    assert default_piece is not None
    assert default_piece.grams == pytest.approx(220.0)
    assert default_piece.status == "estimated"


@pytest.mark.parametrize(
    "measure",
    ["a pinch", "to taste", "For garnish", "as needed", "drizzle"],
)
def test_marks_non_quantitative_measures_as_negligible(measure: str) -> None:
    result = convert_measure_to_grams(measure, [])

    assert result is not None
    assert result.grams is None
    assert result.status == "negligible"


@pytest.mark.parametrize(
    "measure",
    ["", "   ", "2 pieces", "1/0 kg", "0 g", "-5 g"],
)
def test_leaves_invalid_or_unmapped_piece_measure_unconverted(measure: str) -> None:
    assert convert_measure_to_grams(measure, []) is None


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
