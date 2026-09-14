import json

import jsonschema
import pytest

from mnp.schema import export, ontology
from mnp.schema import models as m


def test_json_schema_declares_draft_2020_12():
    s = export.json_schema()
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["$id"].endswith("mnp_characterisation.schema.json")


def test_zeta_field_carries_the_enm_curie():
    s = export.json_schema()
    quantity = export.find_property(s, "SurfaceMeasurement", "quantity")
    assert quantity["x-ontology"]["zeta_potential"] == "ENM:0000092"
    assert quantity["x-ontology"]["electrophoretic_mobility"] == "NPO:1315"


def test_hydrodynamic_size_and_environment_terms_are_annotated():
    s = export.json_schema()
    assert export.find_property(s, "SurfaceMeasurement", "size_measured_nm")["x-ontology"] == {
        "term": "NPO:1914"
    }
    env = export.find_property(s, "Environment", "matrix_class")["x-ontology"]
    assert env["drinking_water"] == "ENVO:00003064"
    assert env["fresh_water"] == "ENVO:00002011"


def test_ionic_strength_is_deliberately_unmapped():
    s = export.json_schema()
    prop = export.find_property(s, "MeasurementConditions", "ionic_strength_mM")
    assert "x-ontology" not in prop
    assert "no ontology term" in prop["description"].lower()


def test_every_curie_resolves_to_a_known_ontology_prefix():
    for curie in ontology.ALL_TERMS.values():
        prefix, _, local = curie.partition(":")
        assert prefix in ontology.PREFIXES, curie
        assert local


def test_example_instance_validates_against_the_exported_schema():
    s = export.json_schema()
    instance = export.example_instance()
    jsonschema.validate(instance, s)


def test_schema_roundtrips_through_json_and_back_into_the_model():
    instance = export.example_instance()
    text = json.dumps(instance)
    back = m.MNPCharacterisation.model_validate(json.loads(text))
    assert json.loads(back.model_dump_json(by_alias=True, exclude_none=True)) == instance


def test_an_instance_missing_the_medium_fails_the_completeness_gate_not_the_schema():
    """The schema records what was reported; completeness is computed, never enforced."""
    s = export.json_schema()
    instance = export.example_instance()
    meas = instance["surface"]["measurements"][0]
    meas["conditions"]["medium_text"] = None
    meas["conditions"]["medium_class"] = "unreported"
    jsonschema.validate(instance, s)
    back = m.MNPCharacterisation.model_validate(instance)
    assert back.surface.measurements[0].conditions.conditions_complete is False


def test_checklist_has_exactly_one_row_per_required_field():
    rows = export.checklist_rows()
    required = export.required_fields()
    assert [r.path for r in rows] == [f"{model}.{field}" for model, field in required]
    assert len(rows) == len(set(r.path for r in rows))
    assert all(r.label and r.why for r in rows)


def test_checklist_markdown_renders_every_row_and_marks_the_unmapped_ones():
    md = export.checklist_markdown()
    rows = export.checklist_rows()
    for r in rows:
        assert r.label in md
    assert "ENM:0000092" in md
    assert md.count("\n|") >= len(rows)


def test_write_artefacts_emits_schema_example_and_checklist(tmp_path):
    written = export.write_artefacts(tmp_path)
    names = {p.name for p in written}
    assert names == {
        "mnp_characterisation.schema.json",
        "example_instance.json",
        "checklist.md",
    }
    for p in written:
        assert p.read_text().strip()


def test_find_property_raises_for_an_unknown_field():
    with pytest.raises(KeyError):
        export.find_property(export.json_schema(), "SurfaceMeasurement", "nope")
