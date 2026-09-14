import pytest
from pydantic import ValidationError

from mnp.schema import models as m


def _conditions(**over):
    base = dict(
        medium_text="10 mM NaCl",
        medium_class=m.MediumClass.salt_solution,
        ionic_strength_mM=10.0,
        ionic_strength_source=m.ValueSource.inferred_from_named_salt,
        pH=7.0,
        temperature_C=25.0,
        instrument="Malvern Zetasizer Nano ZS",
    )
    base.update(over)
    return m.MeasurementConditions(**base)


def _measurement(**over):
    base = dict(
        particle_name="PS-COOH 100 nm",
        material="polystyrene",
        quantity=m.Quantity.zeta_potential,
        value=-42.0,
        unit=m.Unit.mV,
        conditions=_conditions(),
    )
    base.update(over)
    return m.SurfaceMeasurement(**base)


def test_conditions_complete_requires_all_five_reported_conditions():
    assert _measurement().conditions.conditions_complete is True


@pytest.mark.parametrize(
    "field",
    ["medium_text", "ionic_strength_mM", "pH", "temperature_C", "instrument"],
)
def test_conditions_complete_is_false_when_any_single_condition_is_missing(field):
    over = {field: None}
    if field == "medium_text":
        over["medium_class"] = m.MediumClass.unreported
    if field == "ionic_strength_mM":
        over["ionic_strength_source"] = m.ValueSource.unreported
    assert _conditions(**over).conditions_complete is False


def test_ionic_strength_inferable_from_a_named_salt_counts_as_reported():
    c = _conditions(
        ionic_strength_mM=10.0,
        ionic_strength_source=m.ValueSource.inferred_from_named_salt,
    )
    assert c.ionic_strength_reported is True
    assert c.conditions_complete is True


def test_di_water_reports_a_medium_but_not_an_ionic_strength():
    c = _conditions(
        medium_text="deionised water",
        medium_class=m.MediumClass.DI_water,
        ionic_strength_mM=None,
        ionic_strength_source=m.ValueSource.unreported,
    )
    assert c.medium_reported is True
    assert c.ionic_strength_reported is False
    assert c.conditions_complete is False


def test_room_temperature_is_a_reported_temperature_carrying_a_flag():
    c = _conditions(temperature_C=None, temperature_qualifier="room temperature")
    assert c.temperature_reported is True
    assert c.temperature_is_nominal is True
    assert c.conditions_complete is True


def test_a_numeric_ph_range_counts_as_reported_but_prose_does_not():
    assert _conditions(pH=None, pH_text="between 6.8 and 7.2").pH_reported is True
    assert _conditions(pH=None, pH_text="neutral").pH_reported is False
    assert _conditions(pH=None, pH_text=None).pH_reported is False


def test_a_range_or_figure_only_value_is_kept_as_text_not_dropped():
    r = _measurement(value=None, value_text="-5 to -14")
    assert r.value is None and r.value_text == "-5 to -14"
    with pytest.raises(ValidationError):
        _measurement(value=None, value_text=None)


def test_unit_must_match_the_quantity():
    with pytest.raises(ValidationError):
        _measurement(quantity=m.Quantity.electrophoretic_mobility, unit=m.Unit.mV)
    ok = _measurement(
        quantity=m.Quantity.electrophoretic_mobility,
        unit=m.Unit.um_cm_per_Vs,
        value=-3.1,
    )
    assert ok.unit is m.Unit.um_cm_per_Vs


def test_a_single_zeta_value_cannot_stand_in_for_a_surface():
    """The talk's third claim, encoded: one measurement is never a titration."""
    r = m.SurfaceBlock(measurements=[_measurement()])
    assert r.is_titration is False
    two = m.SurfaceBlock(
        measurements=[
            _measurement(conditions=_conditions(ionic_strength_mM=1.0)),
            _measurement(conditions=_conditions(ionic_strength_mM=100.0)),
        ]
    )
    assert two.is_titration is True
    assert two.varied_conditions == ["ionic_strength_mM"]


def test_detection_floor_comes_from_the_sizing_method():
    sr = m.SizeRange(min_um=20.0, max_um=5000.0, method=m.SizeMethod.ftir_imaging)
    assert sr.detection_floor_um == m.DETECTION_FLOOR_UM[m.SizeMethod.ftir_imaging]
    assert sr.floor_below_method_limit is False
    optimistic = m.SizeRange(min_um=0.05, max_um=5000.0, method=m.SizeMethod.ftir_imaging)
    assert optimistic.floor_below_method_limit is True


def test_size_range_rejects_an_inverted_range():
    with pytest.raises(ValidationError):
        m.SizeRange(min_um=10.0, max_um=1.0, method=m.SizeMethod.py_gcms)


def test_every_gold_annotation_column_maps_onto_the_schema():
    """The extraction target IS the schema surface block; the gold set is its columns."""
    mapping = m.gold_column_paths()
    assert set(mapping) == set(m.GOLD_COLUMNS)
    for column, path in mapping.items():
        if path is None:
            continue
        model, _, attr = path.rpartition(".")
        cls = getattr(m, model)
        fields = set(cls.model_fields) | {
            n for n, v in vars(cls).items() if isinstance(v, property)
        }
        assert attr in fields, f"{column} -> {path} does not exist"


def test_provenance_block_carries_the_fields_the_transcripts_demand():
    required = {
        "matrix",
        "digestion_chemistry",
        "digestion_temperature_C",
        "digestion_duration_h",
        "separation",
        "instrument",
        "modality",
        "spatial_floor_um",
        "size_resolved_lod",
        "sampling_time",
        "spectral_library",
        "match_threshold",
        "spiked_natural_material_control",
        "procedural_blanks",
        "morphology_class_calibrated",
    }
    assert required <= set(m.Provenance.model_fields)


def test_evidence_quote_is_marked_unverified_until_checked():
    e = m.Evidence(quote="zeta potential was -42 mV", location="Methods, para 3")
    assert e.verified is False
