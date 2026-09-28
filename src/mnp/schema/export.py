"""Render the models into the three reviewer artefacts.

The JSON Schema, the example instance and the checklist all come from
`models.py`. Editing the checklist by hand is therefore impossible, which is the
point: a checklist that drifts from the schema is how reporting standards die.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from mnp.schema import ontology
from mnp.schema.models import (
    Environment,
    Evidence,
    MatrixClass,
    MeasurementConditions,
    MediumClass,
    MNPCharacterisation,
    Provenance,
    Quantity,
    ReleasedEvidence,
    SizeMethod,
    SizeRange,
    Study,
    SurfaceBlock,
    SurfaceMeasurement,
    Unit,
    ValueSource,
)

SCHEMA_ID = "https://nanosolve.org/schema/mnp_characterisation.schema.json"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

# Order the checklist follows. Reporting order, not definition order: a reader
# fills in what the particle is, then what it was measured in, then how.
_CHECKLIST_ORDER: tuple[tuple[type[BaseModel], str], ...] = (
    (SurfaceMeasurement, "material"),
    (SurfaceMeasurement, "functionalisation"),
    (SurfaceMeasurement, "size_measured_nm"),
    (SurfaceMeasurement, "quantity"),
    (MeasurementConditions, "medium_text"),
    (MeasurementConditions, "ionic_strength_mM"),
    (MeasurementConditions, "pH"),
    (MeasurementConditions, "temperature_C"),
    (MeasurementConditions, "instrument"),
    (SizeRange, "min_um"),
    (SizeRange, "method"),
    (Environment, "matrix_class"),
    (Provenance, "digestion_chemistry"),
    (Provenance, "spatial_floor_um"),
    (Provenance, "size_resolved_lod"),
    (Provenance, "spiked_natural_material_control"),
    (Provenance, "procedural_blanks"),
)


def _extra(model: type[BaseModel], field: str) -> dict:
    return dict(model.model_fields[field].json_schema_extra or {})


def required_fields() -> list[tuple[str, str]]:
    """(model, field) for every field the checklist demands, in checklist order."""
    out = []
    for model, field in _CHECKLIST_ORDER:
        extra = _extra(model, field)
        if not extra.get("required_for_reporting"):
            raise AssertionError(f"{model.__name__}.{field} is in the checklist but not marked")
        out.append((model.__name__, field))
    return out


def _all_marked_fields() -> set[tuple[str, str]]:
    marked = set()
    for model in (SurfaceMeasurement, MeasurementConditions, SizeRange, Environment, Provenance):
        for name, info in model.model_fields.items():
            if (info.json_schema_extra or {}).get("required_for_reporting"):
                marked.add((model.__name__, name))
    return marked


def json_schema() -> dict:
    """Draft 2020-12 schema with x-ontology annotations on the mapped fields."""
    schema = MNPCharacterisation.model_json_schema(mode="validation")
    schema["$schema"] = DRAFT
    schema["$id"] = SCHEMA_ID
    schema["title"] = "MNP characterisation record"
    schema["description"] = (
        "Minimum multiparametric characterisation record for a micro- or "
        "nanoplastic study. Completeness is computed by consumers, not enforced "
        "here: an incomplete record is valid and is exactly what D1 counts."
    )
    # The release's own evidence columns. Defined here, unreferenced by the record, so the
    # repository keeps one schema and the release ships it whole.
    released = ReleasedEvidence.model_json_schema(mode="validation")
    schema["$defs"].update(released.pop("$defs", {}))
    schema["$defs"]["ReleasedEvidence"] = released
    return schema


def find_property(schema: dict, model: str, field: str) -> dict:
    """The property subschema for model.field. Raises KeyError if either is absent."""
    defs = schema.get("$defs", {})
    if model in defs:
        node = defs[model]
    elif schema.get("title") == model or model == "MNPCharacterisation":
        node = schema
    else:
        raise KeyError(f"no definition for {model}")
    props = node.get("properties", {})
    if field not in props:
        raise KeyError(f"{model} has no property {field}")
    return props[field]


def example_instance() -> dict:
    """A complete, honest record: every condition present, one titration point pair."""
    base_conditions = dict(
        medium_text="10 mM NaCl, unbuffered",
        medium_class=MediumClass.salt_solution,
        ionic_strength_mM=10.0,
        ionic_strength_source=ValueSource.inferred_from_named_salt,
        pH=7.2,
        temperature_C=25.0,
        instrument="Malvern Zetasizer Nano ZS",
        instrument_settings="monomodal, 3 runs of 20 s, Smoluchowski conversion",
    )
    particle = dict(
        particle_name="PS-COOH 100 nm",
        material="polystyrene",
        functionalisation="carboxylate",
        supplier="Polysciences",
        size_nominal_nm=100.0,
        size_measured_nm=112.0,
        size_method=SizeMethod.dls,
        quantity=Quantity.electrophoretic_mobility,
        unit=Unit.um_cm_per_Vs,
        medium_matches_exposure=True,
    )
    m1 = SurfaceMeasurement(
        row_id="r1",
        value=-3.42,
        sd=0.11,
        n=3,
        conditions=MeasurementConditions(**base_conditions),
        evidence=Evidence(
            quote=(
                "Electrophoretic mobility was -3.42 (0.11) x 10^-8 m2 V-1 s-1 in 10 mM "
                "NaCl at pH 7.2 and 25 C."
            ),
            location="Methods, Particle characterisation, para 2",
            verified=True,
        ),
        **particle,
    )
    m2 = SurfaceMeasurement(
        row_id="r2",
        value=-2.05,
        sd=0.09,
        n=3,
        conditions=MeasurementConditions(**{**base_conditions, "ionic_strength_mM": 100.0}),
        evidence=Evidence(
            quote=("At 100 mM NaCl the mobility fell to -2.05 (0.09) x 10^-8 m2 V-1 s-1."),
            location="Results, Fig. 2 caption",
            verified=True,
        ),
        **particle,
    )
    record = MNPCharacterisation(
        study=Study(
            pmcid="PMC0000000",
            doi="10.0000/example",
            title="Worked example, not a real study",
            year=2026,
            journal="—",
        ),
        size_range=SizeRange(min_um=0.05, max_um=5000.0, method=SizeMethod.dls),
        surface=SurfaceBlock(measurements=[m1, m2]),
        environment=Environment(
            matrix_text="treated drinking water", matrix_class=MatrixClass.drinking_water
        ),
        provenance=Provenance(
            matrix="treated drinking water",
            digestion_chemistry="proteinase K, no KOH",
            digestion_temperature_C=50.0,
            digestion_duration_h=16.0,
            separation="density separation, NaI",
            instrument="Malvern Zetasizer Nano ZS",
            modality="laser Doppler electrophoresis",
            spatial_floor_um=0.05,
            size_resolved_lod="0.05-1 um: 30 particles/L; 1-10 um: 4 particles/L",
            sampling_time="2026-03-14, 09:00-11:00",
            spectral_library="in-house, 412 reference spectra",
            match_threshold=0.7,
            spiked_natural_material_control=True,
            procedural_blanks=True,
            morphology_class_calibrated=True,
        ),
    )
    return json.loads(record.model_dump_json(by_alias=True, exclude_none=True))


@dataclass(frozen=True)
class ChecklistRow:
    path: str
    label: str
    why: str
    ontology: str


def _ontology_for(model: type[BaseModel], field: str) -> str:
    extra = _extra(model, field)
    terms = extra.get("x-ontology")
    if not terms:
        if field in ontology.UNMAPPED:
            return "— (no ontology term exists)"
        return "—"
    if "term" in terms:
        return terms["term"]
    return ", ".join(f"{k} = {v}" for k, v in terms.items())


def checklist_rows() -> list[ChecklistRow]:
    rows = []
    for model, field in _CHECKLIST_ORDER:
        extra = _extra(model, field)
        rows.append(
            ChecklistRow(
                path=f"{model.__name__}.{field}",
                label=extra["checklist_label"],
                why=extra["checklist_why"],
                ontology=_ontology_for(model, field),
            )
        )
    return rows


def checklist_markdown() -> str:
    rows = checklist_rows()
    unlisted = _all_marked_fields() - {(r.path.split(".")[0], r.path.split(".")[1]) for r in rows}
    lines = [
        "# Minimum reporting checklist — micro/nanoplastic characterisation",
        "",
        "Generated from `mnp.schema.models`. Do not edit by hand.",
        "",
        "Tick every row, or state explicitly that it was not measured. "
        "A blank row is an unreported condition, not a default.",
        "",
        "| ✓ | Report | Why it is not optional | Ontology |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| ☐ | **{r.label}** | {r.why} | `{r.ontology}` |")
    lines += [
        "",
        "## One value is not a surface",
        "",
        "A single zeta potential describes the particle *in that medium only*. "
        "Report at least two ionic strengths, or say plainly that the surface was "
        "characterised at one condition.",
        "",
        f"Ionic strength is unmapped on purpose: {ontology.UNMAPPED['ionic_strength_mM']}.",
    ]
    if unlisted:
        names = ", ".join(sorted(f"{m}.{f}" for m, f in unlisted))
        lines += ["", f"<!-- marked but not in checklist order: {names} -->"]
    return "\n".join(lines) + "\n"


def write_artefacts(out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = out_dir / "mnp_characterisation.schema.json"
    example_path = out_dir / "example_instance.json"
    checklist_path = out_dir / "checklist.md"
    schema_path.write_text(json.dumps(json_schema(), indent=2) + "\n")
    example_path.write_text(json.dumps(example_instance(), indent=2) + "\n")
    checklist_path.write_text(checklist_markdown())
    return [schema_path, example_path, checklist_path]
