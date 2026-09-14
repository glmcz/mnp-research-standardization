"""The characterisation schema — deliverable D2, and the extraction target for D1.

One definition serves three consumers: the JSON Schema handed to reviewers, the
one-page checklist, and the LLM extraction target. If they ever disagree, this
file is the one that is right.

Completeness is *computed*, never enforced. A paper that reports a zeta
potential and nothing else is representable here; that is the point — the stat
in D1 counts exactly those.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mnp.schema import ontology


class Quantity(StrEnum):
    zeta_potential = "zeta_potential"
    electrophoretic_mobility = "electrophoretic_mobility"


class Unit(StrEnum):
    mV = "mV"
    um_cm_per_Vs = "um_cm_per_Vs"  # 1e-8 m^2 V^-1 s^-1, the usual printed unit


UNITS_FOR_QUANTITY = {
    Quantity.zeta_potential: {Unit.mV},
    Quantity.electrophoretic_mobility: {Unit.um_cm_per_Vs},
}


class MediumClass(StrEnum):
    DI_water = "DI_water"
    buffer = "buffer"
    salt_solution = "salt_solution"
    culture_medium = "culture_medium"
    biofluid = "biofluid"
    environmental_water = "environmental_water"
    other = "other"
    unreported = "unreported"


class ValueSource(StrEnum):
    reported = "reported"
    inferred_from_named_salt = "inferred_from_named_salt"
    unreported = "unreported"


class SizeMethod(StrEnum):
    visual_sorting = "visual_sorting"
    ftir_atr = "ftir_atr"
    ftir_imaging = "ftir_imaging"
    raman_imaging = "raman_imaging"
    py_gcms = "py_gcms"
    sem_eds = "sem_eds"
    tem = "tem"
    afm = "afm"
    dls = "dls"
    nta = "nta"
    unreported = "unreported"


# Practical lower size floor of each method, in micrometres. These are what make
# concentrations from different studies non-comparable — the talk's first claim.
DETECTION_FLOOR_UM: dict[SizeMethod, float | None] = {
    SizeMethod.visual_sorting: 300.0,
    SizeMethod.ftir_atr: 500.0,
    SizeMethod.ftir_imaging: 10.0,
    SizeMethod.raman_imaging: 1.0,
    SizeMethod.py_gcms: 1.0,
    SizeMethod.sem_eds: 0.1,
    SizeMethod.tem: 0.001,
    SizeMethod.afm: 0.001,
    SizeMethod.dls: 0.001,
    SizeMethod.nta: 0.01,
    SizeMethod.unreported: None,
}


class MatrixClass(StrEnum):
    drinking_water = "drinking_water"
    fresh_water = "fresh_water"
    seawater = "seawater"
    sediment = "sediment"
    soil = "soil"
    biological_tissue = "biological_tissue"
    air = "air"
    other = "other"
    unreported = "unreported"


def _req(label: str, why: str, term: str | None = None, terms: dict | None = None):
    """Mark a field as one the checklist demands, with its ontology annotation."""
    extra: dict = {"required_for_reporting": True, "checklist_label": label, "checklist_why": why}
    if term:
        extra["x-ontology"] = {"term": term}
    if terms:
        extra["x-ontology"] = dict(terms)
    return extra


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(description="Verbatim sentence from the article.")
    location: str | None = Field(default=None, description="Section and paragraph.")
    verified: bool = Field(
        default=False,
        description="True only once the quote was found as a substring of the article text.",
    )


class MeasurementConditions(BaseModel):
    """The five conditions without which a zeta potential means nothing."""

    model_config = ConfigDict(extra="forbid")

    medium_text: str | None = Field(
        default=None,
        json_schema_extra=_req(
            "Dispersion medium, as composed",
            "A zeta potential is a property of the particle *and* its medium.",
        ),
    )
    medium_class: MediumClass = MediumClass.unreported
    ionic_strength_mM: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total ionic strength in mmol/L. Deliberately unmapped: "
            f"{ontology.UNMAPPED['ionic_strength_mM']}."
        ),
        json_schema_extra={
            "required_for_reporting": True,
            "checklist_label": "Ionic strength (mM)",
            "checklist_why": "Sets the Debye length; without it the mobility curve has no x-axis.",
        },
    )
    ionic_strength_source: ValueSource = ValueSource.unreported
    pH: float | None = Field(
        default=None,
        ge=-1,
        le=15,
        json_schema_extra=_req("pH", "Sets the dissociation of surface groups."),
    )
    pH_text: str | None = Field(
        default=None,
        description="Verbatim pH when it is not a single number, e.g. 'between 6.8 and 7.2'.",
    )
    temperature_C: float | None = Field(
        default=None,
        json_schema_extra=_req("Temperature (°C)", "Enters ε, η and kT in every model."),
    )
    temperature_qualifier: str | None = Field(
        default=None,
        description="Verbatim non-numeric temperature, e.g. 'room temperature'.",
    )
    instrument: str | None = Field(
        default=None,
        json_schema_extra=_req(
            "Instrument and model",
            "Different instruments apply different mobility-to-zeta conversions.",
        ),
    )
    instrument_settings: str | None = None

    @property
    def medium_reported(self) -> bool:
        return bool(self.medium_text) and self.medium_class is not MediumClass.unreported

    @property
    def ionic_strength_reported(self) -> bool:
        return self.ionic_strength_mM is not None and self.ionic_strength_source is not (
            ValueSource.unreported
        )

    @property
    def pH_reported(self) -> bool:
        if self.pH is not None:
            return True
        return bool(self.pH_text) and any(ch.isdigit() for ch in self.pH_text)

    @property
    def temperature_reported(self) -> bool:
        return self.temperature_C is not None or bool(self.temperature_qualifier)

    @property
    def temperature_is_nominal(self) -> bool:
        return self.temperature_C is None and bool(self.temperature_qualifier)

    @property
    def instrument_reported(self) -> bool:
        return bool(self.instrument)

    @property
    def conditions_complete(self) -> bool:
        return all(
            (
                self.medium_reported,
                self.ionic_strength_reported,
                self.pH_reported,
                self.temperature_reported,
                self.instrument_reported,
            )
        )

    @property
    def missing_conditions(self) -> list[str]:
        checks = {
            "medium": self.medium_reported,
            "ionic_strength": self.ionic_strength_reported,
            "pH": self.pH_reported,
            "temperature": self.temperature_reported,
            "instrument": self.instrument_reported,
        }
        return [k for k, ok in checks.items() if not ok]


class SurfaceMeasurement(BaseModel):
    """One reported zeta potential or electrophoretic mobility, with its conditions."""

    model_config = ConfigDict(extra="forbid")

    row_id: str | None = None
    particle_name: str | None = None
    material: str | None = Field(
        default=None, json_schema_extra=_req("Polymer / material", "Sets ε, density and chemistry.")
    )
    functionalisation: str | None = Field(
        default=None,
        json_schema_extra=_req(
            "Surface functionalisation",
            "COOH, NH2 and bare latex are different particles at the same nominal size.",
        ),
    )
    supplier: str | None = None
    size_nominal_nm: float | None = Field(default=None, gt=0)
    size_measured_nm: float | None = Field(
        default=None,
        gt=0,
        json_schema_extra=_req(
            "Measured hydrodynamic size (nm)",
            "Nominal size is the supplier's claim, not a measurement.",
            term=ontology.HYDRODYNAMIC_SIZE,
        ),
    )
    size_method: SizeMethod = SizeMethod.unreported
    quantity: Quantity = Field(
        json_schema_extra=_req(
            "Quantity measured",
            "Mobility is measured; zeta is a model-dependent conversion of it.",
            terms=ontology.QUANTITY_TERMS,
        )
    )
    value: float | None = Field(
        default=None, description="The printed number. None when only a range or a figure exists."
    )
    value_text: str | None = Field(
        default=None,
        description="Verbatim value when it is not a single number: '-5 to -14', 'not printed'.",
    )
    unit: Unit
    sd: float | None = Field(default=None, ge=0)
    n: int | None = Field(default=None, ge=1)
    conditions: MeasurementConditions = Field(default_factory=MeasurementConditions)
    medium_matches_exposure: bool | None = Field(
        default=None,
        description="Was the zeta measured in the same medium the exposure/experiment used?",
    )
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _value_present(self) -> SurfaceMeasurement:
        if self.value is None and not self.value_text:
            raise ValueError("a measurement needs a value or a verbatim value_text")
        return self

    @model_validator(mode="after")
    def _unit_matches_quantity(self) -> SurfaceMeasurement:
        allowed = UNITS_FOR_QUANTITY[self.quantity]
        if self.unit not in allowed:
            names = ", ".join(sorted(u.value for u in allowed))
            raise ValueError(f"{self.quantity.value} must be reported in {names}, got {self.unit}")
        return self


_VARIABLE_CONDITIONS = ("ionic_strength_mM", "pH", "temperature_C", "medium_class")


class SurfaceBlock(BaseModel):
    """All surface measurements for one study.

    One value is a point, not a surface. `is_titration` is the schema's answer to
    "can this paper's particle be placed on a curve?".
    """

    model_config = ConfigDict(extra="forbid")

    measurements: list[SurfaceMeasurement] = Field(default_factory=list)

    @property
    def varied_conditions(self) -> list[str]:
        varied = []
        for name in _VARIABLE_CONDITIONS:
            values = {getattr(m.conditions, name) for m in self.measurements}
            values.discard(None)
            if len(values) > 1:
                varied.append(name)
        return varied

    @property
    def is_titration(self) -> bool:
        return bool(self.varied_conditions)


class SizeRange(BaseModel):
    """A study's reported size window and what its method could actually see."""

    model_config = ConfigDict(extra="forbid")

    min_um: float = Field(
        gt=0,
        json_schema_extra=_req(
            "Lower size limit (µm)", "The single largest driver of a reported concentration."
        ),
    )
    max_um: float = Field(gt=0)
    method: SizeMethod = Field(
        default=SizeMethod.unreported,
        json_schema_extra=_req(
            "Sizing / identification method", "Each method has its own detection floor."
        ),
    )

    @model_validator(mode="after")
    def _ordered(self) -> SizeRange:
        if self.min_um >= self.max_um:
            raise ValueError(f"min_um ({self.min_um}) must be below max_um ({self.max_um})")
        return self

    @property
    def detection_floor_um(self) -> float | None:
        return DETECTION_FLOOR_UM[self.method]

    @property
    def floor_below_method_limit(self) -> bool:
        """Claimed lower limit smaller than the method can resolve."""
        floor = self.detection_floor_um
        return floor is not None and self.min_um < floor


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matrix_text: str | None = None
    matrix_class: MatrixClass = Field(
        default=MatrixClass.unreported,
        json_schema_extra=_req(
            "Environmental matrix",
            "Drinking water and fresh water are different exposure media.",
            terms=ontology.MATRIX_TERMS,
        ),
    )


class Provenance(BaseModel):
    """The minimum provenance the expert transcripts demand (section 7).

    No existing ontology encodes this block; that gap is the contribution.
    """

    model_config = ConfigDict(extra="forbid")

    matrix: str | None = None
    digestion_chemistry: str | None = Field(
        default=None,
        json_schema_extra=_req(
            "Digestion chemistry",
            "KOH dissolves polymers below ~100 nm; proteinase K does not.",
        ),
    )
    digestion_temperature_C: float | None = None
    digestion_duration_h: float | None = None
    separation: str | None = None
    instrument: str | None = None
    modality: str | None = None
    spatial_floor_um: float | None = Field(
        default=None,
        gt=0,
        json_schema_extra=_req("Spatial floor (µm)", "What the optics could not have seen."),
    )
    size_resolved_lod: str | None = Field(
        default=None,
        json_schema_extra=_req(
            "Size-resolved limit of detection",
            "A single LOD hides the fact that it varies with size.",
        ),
    )
    sampling_time: str | None = None
    spectral_library: str | None = None
    match_threshold: float | None = None
    spiked_natural_material_control: bool | None = Field(
        default=None,
        json_schema_extra=_req(
            "Spiked natural-material false-positive control",
            "The only control that catches pigment-as-polymer assignments.",
        ),
    )
    procedural_blanks: bool | None = Field(
        default=None,
        json_schema_extra=_req("Procedural blanks", "Reported, not silently subtracted."),
    )
    morphology_class_calibrated: bool | None = None


class Study(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pmcid: str | None = None
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    journal: str | None = None


class MNPCharacterisation(BaseModel):
    """Top-level instance: one study, characterised."""

    model_config = ConfigDict(extra="forbid")

    study: Study = Field(default_factory=Study)
    size_range: SizeRange | None = None
    surface: SurfaceBlock = Field(default_factory=SurfaceBlock)
    environment: Environment = Field(default_factory=Environment)
    provenance: Provenance = Field(default_factory=Provenance)


class AnnotationMeta(BaseModel):
    """Who annotated a gold row and what they noticed. Gold set only."""

    model_config = ConfigDict(extra="forbid")

    annotator: str | None = None
    notes: str | None = None


class ZetaReport(BaseModel):
    """What the extraction model returns for one paper.

    Its measurement type *is* SurfaceMeasurement — extraction and schema cannot
    drift, because there is only one class.
    """

    model_config = ConfigDict(extra="forbid")

    pmcid: str
    doi: str | None = None
    measurements: list[SurfaceMeasurement] = Field(default_factory=list)
    model: str | None = None
    prompt_sha256: str | None = None


GOLD_COLUMNS = (
    "pmcid",
    "doi",
    "row_id",
    "particle_name",
    "material",
    "functionalisation",
    "supplier",
    "size_nominal_nm",
    "size_measured_nm",
    "medium_text",
    "medium_class",
    "ionic_strength_mM",
    "I_reported",
    "I_inferable_from_named_salt",
    "pH",
    "pH_reported",
    "temperature_C",
    "T_reported",
    "instrument",
    "instrument_reported",
    "quantity",
    "value",
    "value_text",
    "unit",
    "sd",
    "n",
    "medium_matches_exposure",
    "evidence_quote",
    "evidence_location",
    "annotator",
    "notes",
)

_GOLD_PATHS = {
    "pmcid": "ZetaReport.pmcid",
    "doi": "ZetaReport.doi",
    "row_id": "SurfaceMeasurement.row_id",
    "particle_name": "SurfaceMeasurement.particle_name",
    "material": "SurfaceMeasurement.material",
    "functionalisation": "SurfaceMeasurement.functionalisation",
    "supplier": "SurfaceMeasurement.supplier",
    "size_nominal_nm": "SurfaceMeasurement.size_nominal_nm",
    "size_measured_nm": "SurfaceMeasurement.size_measured_nm",
    "medium_text": "MeasurementConditions.medium_text",
    "medium_class": "MeasurementConditions.medium_class",
    "ionic_strength_mM": "MeasurementConditions.ionic_strength_mM",
    "I_reported": "MeasurementConditions.ionic_strength_reported",
    "I_inferable_from_named_salt": "MeasurementConditions.ionic_strength_source",
    "pH": "MeasurementConditions.pH",
    "pH_reported": "MeasurementConditions.pH_reported",
    "temperature_C": "MeasurementConditions.temperature_C",
    "T_reported": "MeasurementConditions.temperature_reported",
    "instrument": "MeasurementConditions.instrument",
    "instrument_reported": "MeasurementConditions.instrument_reported",
    "quantity": "SurfaceMeasurement.quantity",
    "value": "SurfaceMeasurement.value",
    "value_text": "SurfaceMeasurement.value_text",
    "unit": "SurfaceMeasurement.unit",
    "sd": "SurfaceMeasurement.sd",
    "n": "SurfaceMeasurement.n",
    "medium_matches_exposure": "SurfaceMeasurement.medium_matches_exposure",
    "evidence_quote": "Evidence.quote",
    "evidence_location": "Evidence.location",
    "annotator": "AnnotationMeta.annotator",
    "notes": "AnnotationMeta.notes",
}


def gold_column_paths() -> dict[str, str | None]:
    """Every gold-annotation column, and where it lives in the schema."""
    return dict(_GOLD_PATHS)


BOOLEAN_REPORTED_FIELDS = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
)
