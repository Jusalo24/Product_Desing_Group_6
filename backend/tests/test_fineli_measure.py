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
        ("750g piece", 750),
        ("750 g pieces", 750),
        ("100g fine", 100),
        ("100 g fine", 100),
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


def test_estimates_chicken_breast_count_with_pounding_note() -> None:
    result = convert_measure_to_grams(
        "4 pounded to 1cm thickness",
        [],
        default_weight_g=175.0,
        ingredient_name="chicken breast",
    )

    assert result is not None
    assert result.grams == pytest.approx(700.0)
    assert result.status == "estimated"


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


@pytest.mark.parametrize(
    ("measure", "grams", "expected_status"),
    [
        ("100g/3½oz", 100.0, "exact"),
        ("25g/1oz", 25.0, "exact"),
        ("150g / 5oz", 150.0, "exact"),
        ("200ml/7fl oz", 200.0, "estimated"),
        ("400g can", 400.0, "exact"),
        ("14 oz can", pytest.approx(14 * 28.349523125, rel=1e-3), "exact"),
        ("1 x 400g can", 400.0, "exact"),
        ("2 x 400g tins", 800.0, "estimated"),
        ("1 400g tin", 400.0, "exact"),
        ("1 1/2 kg", 1500.0, "exact"),
        ("1 bunch (50g)", 50.0, "exact"),
        ("1 tblsp", 15.0, "estimated"),
        ("2 tbls", 30.0, "estimated"),
        ("1 tbsp. chopped", 15.0, "estimated"),
        ("1 heaped tbsp", 15.0, "estimated"),
        ("2 level tsp", 10.0, "estimated"),
        ("1 generous tbsp", 15.0, "estimated"),
    ],
)
def test_converts_real_world_themealdb_measures(
    measure: str, grams: float, expected_status: str
) -> None:
    result = convert_measure_to_grams(measure, [])

    assert result is not None
    assert result.grams == pytest.approx(grams)
    assert result.status == expected_status


def test_size_fallback_cloves_spice_and_density_word_boundaries() -> None:
    # Large requested when only KPL_S exists scales up from small to large
    large_from_small = convert_measure_to_grams(
        "2 large", [{"code": "KPL_S", "name": "small piece", "grams": 45.0}]
    )
    assert large_from_small is not None
    assert large_from_small.grams == pytest.approx(2 * 45.0 * (1.35 / 0.75))

    # Countable fillet uses default_weight_g
    fillets = convert_measure_to_grams("2 fillets", [], default_weight_g=175.0)
    assert fillets is not None
    assert fillets.grams == pytest.approx(350.0)

    # Whole spice cloves are ~0.1g, not 5g garlic cloves
    spice_cloves = convert_measure_to_grams("4 cloves", [], ingredient_name="Cloves")
    assert spice_cloves is not None
    assert spice_cloves.grams == pytest.approx(0.4)

    # Word-boundary density checks: buttermilk != butter, boiled potato != oil
    buttermilk = convert_measure_to_grams("100 ml", [], ingredient_name="Buttermilk")
    assert buttermilk is not None
    assert buttermilk.grams == pytest.approx(103.0)

    boiled = convert_measure_to_grams("100 ml", [], ingredient_name="Boiled potato")
    assert boiled is not None
    assert boiled.grams == pytest.approx(100.0)

    # Extended negligible phrases
    for phrase in ("a few", "pinch of salt", "handful of parsley", "salt and pepper"):
        negligible = convert_measure_to_grams(phrase, [])
        assert negligible is not None
        assert negligible.status == "negligible"
