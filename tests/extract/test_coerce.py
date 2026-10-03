import pytest

from mnp.extract import coerce
from mnp.schema.models import MediumClass, Quantity, Unit, ValueSource

# -- numbers --------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, value, sd, flags",
    [
        ("-50 ± 9.7", -50.0, 9.7, set()),
        ("−42.3", -42.3, None, set()),
        ("-42.3 mV", -42.3, None, set()),
        ("−30.2 ± 8.2 mV", -30.2, 8.2, set()),
        ("~ -30", -30.0, None, {"approx"}),
        ("≈ −30", -30.0, None, {"approx"}),
        ("about -30", -30.0, None, {"approx"}),
        ("-3.2 × 10−8", -3.2e-8, None, set()),
        ("-3.2 x 10^-8", -3.2e-8, None, set()),
        ("-3.2e-8", -3.2e-8, None, set()),
        ("-3.2·10-8", -3.2e-8, None, set()),
        (42, 42.0, None, set()),
        (-42.5, -42.5, None, set()),
        ("n.d.", None, None, {"unparseable"}),
        ("", None, None, {"unparseable"}),
        (None, None, None, {"unparseable"}),
        ("−20 to −30", None, None, {"range"}),
        ("-20 – -30", None, None, {"range"}),
    ],
)
def test_parse_number(raw, value, sd, flags):
    v, s, f = coerce.parse_number(raw)
    if value is None:
        assert v is None
    else:
        assert v == pytest.approx(value, rel=1e-9)
    assert s == (pytest.approx(sd) if sd is not None else None)
    assert set(f) == flags


# -- units ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, unit, factor",
    [
        ("mV", Unit.mV, 1.0),
        ("mv", Unit.mV, 1.0),
        ("millivolts", Unit.mV, 1.0),
        (" mV ", Unit.mV, 1.0),
        ("µm cm/Vs", Unit.um_cm_per_Vs, 1.0),
        ("μm·cm/(V·s)", Unit.um_cm_per_Vs, 1.0),
        ("um cm V-1 s-1", Unit.um_cm_per_Vs, 1.0),
        ("µmcm/Vs", Unit.um_cm_per_Vs, 1.0),
        ("10^-8 m2/Vs", Unit.um_cm_per_Vs, 1.0),
        ("10−8 m² V−1 s−1", Unit.um_cm_per_Vs, 1.0),
        ("×10-8 m2 V-1 s-1", Unit.um_cm_per_Vs, 1.0),
        ("1e-8 m^2/Vs", Unit.um_cm_per_Vs, 1.0),
        ("m2/Vs", Unit.um_cm_per_Vs, 1e8),
        ("m² V⁻¹ s⁻¹", Unit.um_cm_per_Vs, 1e8),
        ("m^2 V^-1 s^-1", Unit.um_cm_per_Vs, 1e8),
        ("V", None, 1.0),
        ("", None, 1.0),
        (None, None, 1.0),
    ],
)
def test_normalise_unit(raw, unit, factor):
    u, f = coerce.normalise_unit(raw)
    assert u is unit
    assert f == pytest.approx(factor)


def test_si_mobility_is_converted_to_the_printed_unit():
    m, flags = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": "-3.4e-8", "unit": "m2/Vs"}
    )
    assert m.unit is Unit.um_cm_per_Vs
    assert m.value == pytest.approx(-3.4)
    assert "unit_converted" in flags


# -- conditions -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, mM, source, flags",
    [
        ("10 mM", 10.0, ValueSource.reported, set()),
        ("10 mM NaCl", 10.0, ValueSource.inferred_from_named_salt, set()),
        ("0.15 M", 150.0, ValueSource.reported, set()),
        ("150 mmol/L", 150.0, ValueSource.reported, set()),
        ("1 mM KCl", 1.0, ValueSource.inferred_from_named_salt, set()),
        ("10 mM CaCl2", 30.0, ValueSource.inferred_from_named_salt, {"computed_from_salt"}),
        ("10 mM Na2SO4", 30.0, ValueSource.inferred_from_named_salt, {"computed_from_salt"}),
        ("100 µM", 0.1, ValueSource.reported, set()),
        ("I = 10 mM", 10.0, ValueSource.reported, set()),
        (10, 10.0, ValueSource.reported, set()),
        ("PBS", None, ValueSource.unreported, set()),
        ("1× PBS", None, ValueSource.unreported, set()),
        ("", None, ValueSource.unreported, set()),
        (None, None, ValueSource.unreported, set()),
    ],
)
def test_parse_ionic_strength(raw, mM, source, flags):
    v, s, f = coerce.parse_ionic_strength(raw)
    assert v == (pytest.approx(mM) if mM is not None else None)
    assert s is source
    assert set(f) == flags


@pytest.mark.parametrize(
    "raw, celsius, qualifier, flags",
    [
        ("25 °C", 25.0, None, set()),
        ("25°C", 25.0, None, set()),
        ("25 C", 25.0, None, set()),
        ("25 ± 0.1 °C", 25.0, None, set()),
        ("37 degrees", 37.0, None, set()),
        ("298 K", 24.85, None, {"kelvin_converted"}),
        ("298.15 K", 25.0, None, {"kelvin_converted"}),
        ("room temperature", None, "room temperature", set()),
        ("RT", None, "RT", set()),
        ("ambient", None, "ambient", set()),
        (25, 25.0, None, set()),
        ("", None, None, set()),
        (None, None, None, set()),
    ],
)
def test_parse_temperature(raw, celsius, qualifier, flags):
    c, q, f = coerce.parse_temperature(raw)
    assert c == (pytest.approx(celsius, abs=0.01) if celsius is not None else None)
    assert q == qualifier
    assert set(f) == flags


@pytest.mark.parametrize(
    "raw, ph, text",
    [
        ("7.4", 7.4, None),
        ("pH 7.4", 7.4, None),
        (7.4, 7.4, None),
        ("7.4 ± 0.1", 7.4, None),
        ("6.8–7.2", None, "6.8-7.2"),
        ("between 6.8 and 7.2", None, "between 6.8 and 7.2"),
        ("3-10", None, "3-10"),
        ("neutral", None, "neutral"),
        ("", None, None),
        (None, None, None),
        ("15.5", None, "15.5"),
    ],
)
def test_parse_ph(raw, ph, text):
    p, t = coerce.parse_ph(raw)
    assert p == (pytest.approx(ph) if ph is not None else None)
    assert t == text


@pytest.mark.parametrize(
    "text, cls",
    [
        ("deionised water", MediumClass.DI_water),
        ("Milli-Q water", MediumClass.DI_water),
        ("ultrapure water", MediumClass.DI_water),
        ("double distilled water", MediumClass.DI_water),
        ("10 mM NaCl", MediumClass.salt_solution),
        ("1 mM KCl solution", MediumClass.salt_solution),
        ("PBS", MediumClass.buffer),
        ("10 mM HEPES, pH 7.4", MediumClass.buffer),
        ("phosphate buffer", MediumClass.buffer),
        ("DMEM with 10% FBS", MediumClass.culture_medium),
        ("RPMI 1640", MediumClass.culture_medium),
        ("perfusion medium", MediumClass.culture_medium),
        ("human plasma", MediumClass.biofluid),
        ("artificial seawater", MediumClass.environmental_water),
        ("river water", MediumClass.environmental_water),
        ("tap water", MediumClass.environmental_water),
        ("ethanol", MediumClass.other),
        ("", MediumClass.unreported),
        (None, MediumClass.unreported),
    ],
)
def test_infer_medium_class(text, cls):
    assert coerce.infer_medium_class(text) is cls


def test_model_supplied_medium_class_wins_when_valid_and_is_inferred_otherwise():
    m, _ = coerce.coerce_measurement(
        {"value": -30, "unit": "mV", "medium_text": "10 mM NaCl", "medium_class": "biofluid"}
    )
    assert m.conditions.medium_class is MediumClass.biofluid
    m, flags = coerce.coerce_measurement(
        {"value": -30, "unit": "mV", "medium_text": "10 mM NaCl", "medium_class": "saline"}
    )
    assert m.conditions.medium_class is MediumClass.salt_solution
    assert "medium_class_inferred" in flags


# -- the whole row ---------------------------------------------------------------


def test_coerce_measurement_builds_a_full_row_from_model_strings():
    raw = {
        "particle_name": "PS-NH2 N1",
        "material": "polystyrene",
        "functionalisation": "amine",
        "supplier": "Polysciences",
        "size_nominal_nm": "100 nm",
        "size_measured_nm": "0.112 µm",
        "quantity": "zeta potential",
        "value": "−50 ± 9.7",
        "unit": "mV",
        "n": "3",
        "conditions": {
            "medium_text": "10 mM NaCl",
            "ionic_strength": "10 mM NaCl",
            "pH": "between 6.8 and 7.2",
            "temperature": "room temperature",
            "instrument": "Zetasizer NanoZS",
        },
        "evidence_quote": "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7",
        "evidence_location": "Table 1",
    }
    m, flags = coerce.coerce_measurement(raw)
    assert m.quantity is Quantity.zeta_potential
    assert m.value == -50.0 and m.sd == 9.7 and m.n == 3
    assert m.size_nominal_nm == 100.0
    assert m.size_measured_nm == pytest.approx(112.0)
    c = m.conditions
    assert c.ionic_strength_mM == 10.0
    assert c.ionic_strength_source is ValueSource.inferred_from_named_salt
    assert c.medium_class is MediumClass.salt_solution
    assert c.pH is None and c.pH_text == "between 6.8 and 7.2"
    assert c.temperature_C is None and c.temperature_qualifier == "room temperature"
    assert c.instrument == "Zetasizer NanoZS"
    assert c.conditions_complete is True
    assert m.evidence.quote.startswith("Zeta potential in 10 mM NaCl")
    assert m.evidence.verified is False
    assert flags == []


def test_coerce_measurement_accepts_flat_condition_keys():
    m, _ = coerce.coerce_measurement(
        {"value": -30, "unit": "mV", "medium_text": "PBS", "pH": 7.4, "temperature": "25 °C"}
    )
    assert m.conditions.pH == 7.4
    assert m.conditions.temperature_C == 25.0
    assert m.conditions.medium_class is MediumClass.buffer


def test_zeta_without_a_unit_is_assumed_mv_and_flagged():
    m, flags = coerce.coerce_measurement({"quantity": "zeta", "value": "-30"})
    assert m.unit is Unit.mV
    assert "unit_assumed_mV" in flags


def test_quantity_is_inferred_from_the_unit_when_missing():
    m, _ = coerce.coerce_measurement({"value": "-2.1", "unit": "µm cm/Vs"})
    assert m.quantity is Quantity.electrophoretic_mobility


def test_unparseable_value_drops_the_row_with_a_reason():
    m, flags = coerce.coerce_measurement({"quantity": "zeta", "value": "n.d.", "unit": "mV"})
    assert m is None
    assert "value_unparseable" in flags


def test_unit_quantity_mismatch_drops_the_row():
    m, flags = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": "-30", "unit": "mV"}
    )
    assert m is None
    assert "unit_quantity_mismatch" in flags


def test_null_strings_are_treated_as_missing():
    m, _ = coerce.coerce_measurement(
        {"value": -30, "unit": "mV", "medium_text": "null", "pH": "N/A", "instrument": "none"}
    )
    assert m.conditions.medium_text is None
    assert m.conditions.pH is None and m.conditions.pH_text is None
    assert m.conditions.instrument is None


def test_a_range_value_is_kept_verbatim_as_text():
    m, flags = coerce.coerce_measurement(
        {"quantity": "zeta", "value": "−5 to −14", "unit": "mV",
         "evidence_quote": "a slightly anionic surface charge of approximately -5 to -14 mV"}
    )  # fmt: skip
    assert m is not None and m.value is None
    assert m.value_text == "-5 to -14"
    assert "value_is_range" in flags


def test_a_figure_only_mention_with_a_zeta_quote_is_kept_as_not_printed():
    m, flags = coerce.coerce_measurement(
        {"quantity": "zeta", "value": None, "unit": "mV",
         "conditions": {"medium_text": "ultrapure water"},
         "evidence_quote": "The zeta potential of the MPs is shown in Supplementary Fig. S1."}
    )  # fmt: skip
    assert m is not None and m.value_text == "not printed"
    assert "value_not_printed" in flags
    assert m.conditions.medium_reported is True


def test_a_null_value_without_a_zeta_quote_is_still_dropped():
    m, flags = coerce.coerce_measurement({"quantity": "zeta", "value": None, "unit": "mV"})
    assert m is None and "value_unparseable" in flags
    m, flags = coerce.coerce_measurement({"quantity": "zeta", "value": "n.d.", "unit": "mV",
                                          "evidence_quote": "zeta n.d."})  # fmt: skip
    assert m is None


def test_minus_thin_space_is_negative():
    v, _, _ = coerce.parse_number("− 43.3")
    assert v == -43.3
    v, _, _ = coerce.parse_number("− 43.3 mV")
    assert v == -43.3


def test_a_kept_text_value_does_not_also_report_itself_unparseable():
    m, flags = coerce.coerce_measurement(
        {"quantity": "zeta", "value": None, "unit": "mV",
         "evidence_quote": "The zeta potential is shown in Fig. 2."}
    )  # fmt: skip
    assert m is not None
    assert flags == ["value_not_printed"]
    m, flags = coerce.coerce_measurement(
        {"quantity": "zeta", "value": "-5 to -14", "unit": "mV",
         "evidence_quote": "a zeta potential of -5 to -14 mV"}
    )  # fmt: skip
    assert flags == ["value_is_range"]


def test_en_dash_values_parse_negative():
    assert coerce.parse_number("–13.4 ± 0.8")[0] == -13.4
    assert coerce.parse_number("–13.4 ± 0.8")[1] == 0.8
    assert coerce.parse_number("2–3")[0] is None  # still a range, still rejected


@pytest.mark.parametrize(
    "raw, value, sd",
    [
        ("-31,63", -31.63, None),
        ("-31,63 ± 0,45", -31.63, 0.45),
        ("‐30,63±1,38 mV", -30.63, 1.38),
        ("-31.63", -31.63, None),
    ],
)
def test_a_decimal_comma_is_read_as_a_decimal_point(raw, value, sd):
    v, s, _ = coerce.parse_number(raw)
    assert v == pytest.approx(value)
    assert s == (pytest.approx(sd) if sd is not None else None)


def test_a_decimal_comma_works_for_ionic_strength_too():
    v, source, _ = coerce.parse_ionic_strength("0,026 M")
    assert v == pytest.approx(26.0)
    assert source is ValueSource.reported


def test_a_citation_list_is_not_a_decimal():
    """'[4,5]' must not become 4.5; only a comma inside one number converts."""
    assert coerce.parse_number("[4,5]")[0] == pytest.approx(4.0)
    v, _, _ = coerce.parse_number("1,234")
    assert v == pytest.approx(1.234)  # a thousands separator is implausible for a zeta


@pytest.mark.parametrize(
    "unit",
    [
        "10⁻⁸ m²V⁻¹s⁻¹",
        "10⁻⁸ m² V⁻¹ s⁻¹",
        "×10⁻⁸ m²/Vs",
        "10−8 m2 V−1 s−1",
        "×10-8 m2/Vs",
    ],
)
def test_a_superscript_ten_to_the_minus_eight_is_not_multiplied_again(unit):
    """PMC11099890: '10⁻⁸ m²V⁻¹s⁻¹' was unrecognised, so -4.00 was stored as -400."""
    u, factor = coerce.normalise_unit(unit)
    assert u is Unit.um_cm_per_Vs
    assert factor == 1.0, f"{unit!r} would rescale by {factor:g}"


def test_plain_si_mobility_units_still_convert():
    for unit in ("m² V⁻¹ s⁻¹", "m2/Vs", "m^2 V^-1 s^-1"):
        u, factor = coerce.normalise_unit(unit)
        assert u is Unit.um_cm_per_Vs and factor == 1e8, unit


def test_an_implausible_converted_mobility_is_refused_not_stored():
    """No colloid has |mu| of 400 x 10^-8; a conversion that says so is wrong."""
    m, flags = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": "-4.00", "unit": "m2 V-1 s-1",
         "evidence_quote": "mobility of -4.00"}
    )  # fmt: skip
    assert m is not None
    assert m.value == pytest.approx(-4.00)
    assert "unit_conversion_refused_implausible" in flags
    assert "unit_converted" not in flags


@pytest.mark.parametrize(
    "unit, factor, why",
    [
        ("m2/Vs", 1e8, "SI: 1 m2/V/s is 1e8 x 1e-8"),
        ("m² V⁻¹ s⁻¹", 1e8, "same, superscripts"),
        ("10-8 m2/Vs", 1.0, "already the canonical scale"),
        ("10⁻⁸ m²V⁻¹s⁻¹", 1.0, "same, superscripts"),
        ("cm2/Vs", 1e4, "1 cm2 = 1e-4 m2, so 1 cm2/V/s is 1e4 x 1e-8"),
        ("cm²/Vs", 1e4, "same, superscripts"),
        ("E. M. (cm 2/Vs)", 1e4, "as printed in PMC11117817"),
        ("×10-4 cm2 V-1 s-1", 1.0, "the paper's own 1e-4 cancels the cm2, PMC11099890"),
        ("10 –4 (cm 2 V -1 s -1)", 1.0, "same with an en-dash exponent"),
        ("µm cm/Vs", 1.0, "the printed mixed unit is already 1e-8 m2/V/s"),
        ("10-9 m2/Vs", 0.1, "1e-9 m2/V/s is a tenth of the canonical 1e-8"),
    ],
)
def test_mobility_unit_factors_are_computed_from_exponent_and_area(unit, factor, why):
    u, f = coerce.normalise_unit(unit)
    assert u is Unit.um_cm_per_Vs, unit
    assert f == pytest.approx(factor, rel=1e-9), f"{unit!r}: {why}"


def test_a_nonlinear_mobility_unit_is_not_a_mobility():
    """cm4 V-3 s-1 is a different physical quantity; mislabelling it would be worse."""
    assert coerce.normalise_unit("10-10 cm4 V-3 s-1")[0] is None
    assert coerce.normalise_unit("cm4/V3s")[0] is None


def test_a_cm2_mobility_is_converted_rather_than_refused():
    m, flags = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": "-0.000141", "unit": "cm2/Vs",
         "evidence_quote": "E. M. (cm2/Vs) -0.000141"}
    )  # fmt: skip
    assert m is not None
    assert m.value == pytest.approx(-1.41, rel=1e-6)
    assert "unit_converted" in flags
    assert "unit_conversion_refused_implausible" not in flags


def test_a_negative_standard_deviation_is_read_as_a_magnitude():
    v, sd, _ = coerce.parse_number("-52.42 ± -0.26")
    assert v == pytest.approx(-52.42)
    assert sd == pytest.approx(0.26)


def test_a_mobility_row_without_a_unit_defaults_like_zeta_does():
    """A zeta row with no unit assumes mV; a mobility row was dropped instead, which
    cost one worker all three of its ingest attempts on a figure-only row."""
    m, flags = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": None, "unit": None,
         "evidence_quote": "The electrophoretic mobility of the PE was measured (Fig. 4)."}
    )  # fmt: skip
    assert m is not None
    assert m.unit is Unit.um_cm_per_Vs
    assert "unit_assumed_um_cm_per_Vs" in flags
    assert "value_not_printed" in flags


def test_the_enum_spelling_of_the_unit_is_accepted():
    """Workers naturally write the schema's own enum name."""
    unit, factor = coerce.normalise_unit("um_cm_per_Vs")
    assert unit is Unit.um_cm_per_Vs and factor == 1.0
    m, _ = coerce.coerce_measurement(
        {"quantity": "electrophoretic mobility", "value": "-2.5", "unit": "um_cm_per_Vs",
         "evidence_quote": "mobility -2.5"}
    )  # fmt: skip
    assert m is not None and m.value == pytest.approx(-2.5)


@pytest.mark.parametrize(
    "medium",
    [
        "FSW + BPA (10 µM)",  # a co-exposure concentration, not the medium's salt
        "seawater spiked with 5 µM Cd",
        "DMEM + 2 mM glucose",
        "water containing 10 µg/L of the drug",
    ],
)
def test_a_concentration_of_something_other_than_salt_is_not_an_ionic_strength(medium):
    """PMC9687932: "FSW + BPA (10 µM)" was recorded as I = 0.01 mM, *reported*. The study
    measures how often ionic strength goes unreported, so a false 'reported' is the worst
    error it can make. Tested through the real path: the medium fallback, not the helper."""
    m, _ = coerce.coerce_measurement(
        {"quantity": "zeta potential", "value": "-30", "unit": "mV",
         "conditions": {"medium_text": medium}, "evidence_quote": "zeta -30 mV"}
    )  # fmt: skip
    assert m is not None
    assert m.conditions.ionic_strength_mM is None, f"{medium} yielded I"
    assert m.conditions.ionic_strength_reported is False


@pytest.mark.parametrize(
    "medium, expected",
    [
        ("10 mM NaCl", 10.0),
        ("1 mM KCl solution", 1.0),
        ("artificial seawater, ionic strength 600 mM", 600.0),
        ("5 mM CaCl2", 15.0),
    ],
)
def test_a_named_electrolyte_still_gives_an_ionic_strength(medium, expected):
    m, _ = coerce.coerce_measurement(
        {"quantity": "zeta potential", "value": "-30", "unit": "mV",
         "conditions": {"medium_text": medium}, "evidence_quote": "zeta -30 mV"}
    )  # fmt: skip
    assert m is not None
    assert m.conditions.ionic_strength_mM == pytest.approx(expected)
    assert m.conditions.ionic_strength_reported is True


def test_an_inequality_bound_is_not_a_value():
    """'<0 mV' means negative, not zero. Storing 0.0 would be a fabricated measurement."""
    assert coerce.parse_number("<0")[0] is None
    assert coerce.parse_number("> -30")[0] is None
    assert coerce.parse_number("≤ -12.5")[0] is None
    assert coerce.parse_number("-12.5")[0] == pytest.approx(-12.5)


# -- Martin's rules, 2026-09-13 (docs/DECISIONS_NEEDED.md, tests/edge/key.yaml C1/C2/C5) ---

PBS_RECIPE = (
    "1× PBS tablet (0.01 M phosphate buffer, 0.0027 M potassium chloride, "
    "0.137 M sodium chloride) in 200 mL deionised water"
)


def test_a_printed_composition_gives_an_ionic_strength_flagged_derived():
    """Q1, PMC4958399. A stated composition establishes the ionic strength when the sum
    follows from named species at stated concentrations: 137 + 2.7 = 139.7 mM. The
    phosphate is excluded — its speciation at pH 7.4 is never stated — so a parser that
    added it would return 149.7. The value is derived, never plainly reported."""
    mM, source, flags = coerce.parse_ionic_strength(PBS_RECIPE)
    assert mM == pytest.approx(139.7)
    assert source is ValueSource.inferred_from_named_salt
    assert "derived_from_composition" in flags


def test_a_composition_is_read_through_the_real_ingest_path():
    m, _ = coerce.coerce_measurement(
        {"quantity": "zeta potential", "value": "-20.3", "unit": "mV",
         "conditions": {"ionic_strength_text": PBS_RECIPE},
         "evidence_quote": "zeta -20.3 mV"}
    )  # fmt: skip
    assert m is not None
    assert m.conditions.ionic_strength_mM == pytest.approx(139.7)
    assert m.conditions.ionic_strength_reported is True


@pytest.mark.parametrize(
    "raw, mM",
    [
        ("0.137 M sodium chloride", 137.0),
        ("0.0027 M potassium chloride", 2.7),
        ("10 mM calcium chloride", 30.0),
        ("1 mM magnesium sulphate", 4.0),
    ],
)
def test_a_salt_spelled_out_is_the_same_salt(raw, mM):
    """The abbreviation table alone could not read the recipe papers actually print."""
    got, source, _ = coerce.parse_ionic_strength(raw)
    assert got == pytest.approx(mM)
    assert source is ValueSource.inferred_from_named_salt


@pytest.mark.parametrize(
    "raw",
    [
        "incubated at 37 °C",
        "samples were incubated at 25 and 37 °C in a mini dry bath prior to TRPS analysis",
        "37 °C exposure",
        "cultured at 37 °C",
        "stored at 4 °C",
        "digested at 60 °C",
    ],
)
def test_a_temperature_belonging_to_another_step_is_not_reported(raw):
    """Q2, PMC4958399. Only a temperature tied to the zeta measurement counts. This was the
    single largest measured source of extraction error: row-level temperature P 0.15."""
    celsius, qualifier, flags = coerce.parse_temperature(raw)
    assert celsius is None
    assert qualifier is None
    assert "temperature_not_measurement" in flags


@pytest.mark.parametrize(
    "raw, celsius",
    [
        ("measurements were made at 25 °C", 25.0),
        ("25 ± 0.1 °C", 25.0),
        ("equilibrated to 25 °C in the measurement cell", 25.0),
        ("298 K", 24.85),
    ],
)
def test_a_measurement_temperature_still_counts(raw, celsius):
    """The guard must not swallow the temperatures the study is counting."""
    got, _, flags = coerce.parse_temperature(raw)
    assert got == pytest.approx(celsius, abs=0.01)
    assert "temperature_not_measurement" not in flags


@pytest.mark.parametrize(
    "raw",
    ["约为-30 mV", "大约 -30 mV", "约 -30 mV", "-30 mV左右"],
)
def test_chinese_approximation_markers_are_recognised(raw):
    """ "约为" is "approximately". Unflagged, it turns a hedge into an exact measurement.

    Found by a slice worker on PMC12439659, which prints 平均zeta电位约为-30 mV. The corpus
    contains Chinese-language papers, and rule 1 of the brief is that nothing may be inferred
    — silently dropping the paper's own hedge infers precision it never claimed.
    """
    value, _, flags = coerce.parse_number(raw)
    assert value == -30.0
    assert "approx" in flags, f"{raw!r} recorded as an exact value"


@pytest.mark.parametrize(
    "medium",
    [
        "NaCl buffered with 5 mM HEPES at pH 7.4",
        "NaCl solution with 5 mM HEPES",
        "KCl in 10 mM Tris",
    ],
)
def test_a_concentration_belonging_to_another_compound_is_not_the_salt_s(medium):
    """The number belongs to the buffer; the salt's own concentration is never stated.

    Same family as the "FSW + BPA (10 µM)" defect that inflated the headline metric: a named
    salt anywhere in the string used to capture any concentration anywhere in the string. Here
    it fabricates an ionic strength of 5 mM for a solution dominated by an unstated amount of
    NaCl. Found by a slice worker on PMC9974068, who had to mangle the medium text to stop it.
    """
    value, source, flags = coerce.parse_ionic_strength(medium, from_medium=True)
    assert value is None, f"fabricated {value} mM from a concentration that is not the salt's"


@pytest.mark.parametrize(
    ("medium", "expected"),
    [
        ("10 mM NaCl", 10.0),
        ("0.137 M NaCl, 0.0027 M KCl", 139.7),
        ("NaCl (10 mM)", 10.0),
        ("150 mM NaCl with 10 mM HEPES", 150.0),
        ("10 mM CaCl2", 30.0),
    ],
)
def test_a_concentration_bound_to_its_salt_still_counts(medium, expected):
    """The fix must not cost the cases the ratified composition rule depends on."""
    value, _, _ = coerce.parse_ionic_strength(medium, from_medium=True)
    assert value is not None and abs(value - expected) <= 0.2, f"{medium!r} -> {value}"


@pytest.mark.parametrize(
    "raw",
    ["-34 to -48", "between -34 mV and -48 mV", "+21–+30", "−34 and −48", "-21 ~ -30"],
)
def test_every_way_a_paper_writes_a_range_is_seen_as_one(raw):
    """A range silently truncated to its first endpoint is a fabricated precision.

    `_RANGE` accepted only "to" and a hyphen, so "between -34 mV and -48 mV" parsed as -34.0
    with **no flag** — indistinguishable in the data from a paper that printed -34. Found by a
    sweep worker who had to rewrite the paper's own words as "X to Y" to get it recognised.
    `_PH_RANGE` already accepted "and" and en-dashes; the two were inconsistent.
    """
    value, _, flags = coerce.parse_number(raw)
    assert "range" in flags, f"{raw!r} -> {value!r}, flags {flags}"
    assert value is None, f"{raw!r} kept a single value from a range"


def test_a_unit_the_code_does_not_know_is_refused_not_assumed():
    """Nonlinear mobility is printed in cm4 V-3 s-1; assuming µm·cm/Vs corrupts the number.

    `normalise_unit` returns None for a unit it cannot read, and the caller treated None as
    "no unit was printed" and filled in the conventional one — so the row carried a
    plausible-looking number in the wrong unit, flagged `unit_assumed_...`, which asserts the
    paper printed nothing. It printed something; we could not read it. Found by a sweep worker
    who dropped eight rows by hand rather than let them through.
    """
    row = {"particle_name": "PS", "quantity": "electrophoretic mobility", "value": "3.1",
           "unit": "cm4 V-3 s-1", "evidence_quote": "mobility 3.1 cm4 V-3 s-1"}  # fmt: skip
    out, flags = coerce.coerce_measurement(row)
    assert out is None, "a value in an unreadable unit must not be recorded"
    assert "unit_unrecognised" in flags, flags
    assert not any(f.startswith("unit_assumed") for f in flags), (
        "the paper printed a unit; claiming it did not is false"
    )


def test_a_genuinely_absent_unit_is_still_assumed_and_said_so():
    """The assumption is right when nothing was printed — that is why the flag exists."""
    row = {"particle_name": "PS", "quantity": "zeta potential", "value": "-30",
           "unit": None, "evidence_quote": "zeta potential of -30"}  # fmt: skip
    out, flags = coerce.coerce_measurement(row)
    assert out is not None
    assert "unit_assumed_mV" in flags


def test_the_units_the_code_does_know_still_work():
    for raw in ("mV", "mv", "µm cm/Vs", "m2/Vs"):
        unit, _ = coerce.normalise_unit(raw)
        assert unit is not None, raw


def test_the_word_is_is_not_the_abbreviation_IS():
    """`\\bIS\\b` matched case-insensitively took the English "is" for "ionic strength", so a
    medium that says "is" anywhere had its buffer concentration recorded as one."""
    mM, source, flags = coerce.parse_ionic_strength("water that is 10 mM Tris", from_medium=True)
    assert (mM, source) == (None, ValueSource.unreported)
    assert flags == ["concentration_not_an_ionic_strength"]
    assert coerce.parse_ionic_strength("IS = 10 mM", from_medium=True)[0] == 10.0
