"""Query kind E — may these two measurements be compared, and what blocks it?

Kinds A–D are retrieval tasks: a passage somewhere states the answer and the only question is
whether the reader finds it. This one is different in kind. Whether two rows may be compared is
a predicate over a **pair** of records. No sentence in any paper states it, because no paper
knows about the other paper. The fact exists only in the join, so retrieval cannot reach it by
construction — the same argument that already applies to absence, extended to comparability,
which is what the abstract is actually about.

The answer key is therefore **derivable deterministically** from conditions already in
``out/tables/d1_zeta_table.csv``. Nothing here calls a model, a network or a clock; the only
randomness is seeded. Tokens are spent asking agents to *answer* the questions, never building
the key.

``docs/FINDINGS_comparability.md`` records the rules, the justification for each, the counts
that came out, and the sensitivity check that answers "you rigged it so nothing is comparable".

Two rules are load-bearing and are the reason this module exists rather than a dict comprehension:

* **An unreported condition blocks and is never imputed.** "DI water" is a reported medium and
  an unreported ionic strength. "Not reported" is a statement about the paper; "not present" is
  a statement about the experiment that nobody checked.
* **The reported value is never evidence.** :class:`ZetaRow` does not carry ``value``, ``sd``,
  ``n`` or ``unit`` at all, so a rule *cannot* be written that lets a similar zeta stand in for
  a similar particle. Chemically distinct particles converge after corona formation; that is the
  abstract's central point and it is structural here, not merely tested.
"""

from __future__ import annotations

import csv
import math
import random
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config
from mnp.schema.models import MeasurementConditions, MediumClass, Quantity, ValueSource

QUERY_SET_PATH = config.QUERIES / "kind_e_comparability.csv"
RANDOM_SEED = 20260918

# --- tolerances, each with the physics that sets it ---------------------------------------
#
# A tolerance is a claim about what difference is small enough to be measurement scatter
# rather than a different experiment. Every one of these is argued in the findings doc.

# kappa^-1 goes as I^-1/2, so 10 % in I is 5 % in the Debye length — inside replicate scatter.
IONIC_STRENGTH_REL_TOL = 0.10
# Reported pH carries one decimal. 0.2 admits rounding, not a different buffer point.
PH_TOL = 0.2
# eta of water moves ~2 %/degC and zeta tracks eta/epsilon, so 2 degC is ~4 % in the conversion.
TEMPERATURE_TOL_C = 2.0
# Henry's f spans 1.0 (Huckel) to 1.5 (Smoluchowski) — the factor of 1.5 the abstract names.
# 5 % of f is a tenth of that gap.
HENRY_REL_TOL = 0.05


class Comparability(StrEnum):
    comparable = "comparable"
    conditionally_comparable = "conditionally_comparable"
    not_comparable = "not_comparable"


class BlockerKind(StrEnum):
    #: The paper never said. No reader can repair this, and nothing may default it.
    unreported = "unreported"
    #: The paper said something, but not a number two rows can be compared on.
    undecidable = "undecidable"
    #: Both rows state it and they differ.
    mismatch = "mismatch"


@dataclass(frozen=True)
class Blocker:
    code: str
    field: str
    kind: BlockerKind
    detail: str = ""


#: Every value `Blocker.field` takes. Codes are finer (medium_class_mismatch and
#: medium_text_mismatch are both `medium`); a kind E answer names fields, so this list is what
#: the answer contract prints, identically for every cell.
BLOCKER_FIELDS: tuple[str, ...] = (
    "quantity",
    "material",
    "functionalisation",
    "medium",
    "ionic_strength",
    "pH",
    "temperature",
    "instrument",
    "size_measured_nm",
    "conversion_model",
)


@dataclass(frozen=True)
class Verdict:
    verdict: Comparability
    blockers: tuple[Blocker, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(blocker.code for blocker in self.blockers)


# A mismatch in one of these is a *stated, quantified* difference in context: the two rows can
# still be placed on a common axis and the difference attributed to the named condition. A
# mismatch in anything else — the measurand, the particle, the instrument, the conversion
# regime — is not an axis, it is a different experiment.
_AXIS_CODES = frozenset(
    {
        "medium_class_mismatch",
        "medium_text_mismatch",
        "ionic_strength_mismatch",
        "pH_mismatch",
        "temperature_mismatch",
    }
)


# --- normalisation ------------------------------------------------------------------------
#
# Every canonicaliser below only ever merges *spellings*. None of them drops a modifier to
# reach a match, and none of them guesses: a string it does not recognise keys to itself, so
# it matches nothing but an identical string. That direction of failure is the safe one —
# an unrecognised spelling costs a comparable pair, an over-eager merge invents one.


def _norm(text: str | None) -> str | None:
    if text is None:
        return None
    flat = unicodedata.normalize("NFKC", str(text))
    flat = re.sub(r"[^0-9A-Za-z]+", " ", flat)
    flat = " ".join(flat.casefold().split())
    return flat or None


#: Exact post-normalisation spellings of a plain polymer. Composites, mixtures, core-shell
#: particles and "PS + PE" are deliberately absent: they are not polystyrene.
MATERIAL_SPELLINGS: dict[str, str] = {
    "polystyrene": "PS",
    "polystyrene ps": "PS",
    "ps": "PS",
    "ps polystyrene": "PS",
    "polystyrene ps latex": "PS",
    "polystyrene ps latex 2": "PS",
    "polyethylene": "PE",
    "polyethylene pe": "PE",
    "pe": "PE",
    "pe polyethylene": "PE",
    "high density polyethylene hdpe": "HDPE",
    "hdpe": "HDPE",
    "polyethylene hdpe": "HDPE",
    "ldpe": "LDPE",
    "ld pe": "LDPE",
    "polyethylene ldpe": "LDPE",
    "pe ldpe": "LDPE",
    "polypropylene": "PP",
    "polypropylene pp": "PP",
    "pp": "PP",
    "pet": "PET",
    "polyethylene terephthalate": "PET",
    "polyethylene terephthalate pet": "PET",
    "pet polyethylene terephthalate": "PET",
    "poly ethylene terephthalate": "PET",
    "poly ethylene terephthalate pet": "PET",
    "polyethylene terephthalate pete": "PET",
    "pete pet": "PET",
    "polyester pet": "PET",
    "polyvinyl chloride": "PVC",
    "polyvinyl chloride pvc": "PVC",
    "polyvinylchloride pvc": "PVC",
    "poly vinyl chloride pvc": "PVC",
    "pvc polyvinyl chloride": "PVC",
    "pvc": "PVC",
    "pmma": "PMMA",
    "poly methyl methacrylate": "PMMA",
    "poly methyl methacrylate pmma": "PMMA",
    "polymethyl methacrylate": "PMMA",
    "polymethyl methacrylate pmma": "PMMA",
    "polymethylmethacrylate": "PMMA",
    "pmma poly methyl methacrylate": "PMMA",
    "pla": "PLA",
    "polylactic acid": "PLA",
    "polylactic acid pla": "PLA",
    "pla polylactic acid": "PLA",
    "poly lactic acid": "PLA",
    "pbat": "PBAT",
    "pbat poly butylene adipate co terephthalate": "PBAT",
    "poly butylene adipate co terephthalate pbat": "PBAT",
    "pbat polybutylene adipate terephthalate": "PBAT",
    "ptfe": "PTFE",
    "polytetrafluoroethylene": "PTFE",
    "polytetrafluoroethylene ptfe": "PTFE",
    "polycarbonate": "PC",
    "polycarbonate pc": "PC",
    "polycaprolactone": "PCL",
    "pcl poly caprolactone": "PCL",
    "nylon 6": "PA6",
    "nylon 6 polyamide 6": "PA6",
    "polyamide 6": "PA6",
    "pa66": "PA66",
    "polyamide 6 6": "PA66",
    "polyamide 6 6 pa nylon": "PA66",
    "nylon 11 polyamide 11": "PA11",
    "nylon 11 polyamide": "PA11",
}

#: Exact post-normalisation spellings of a surface state. A string carrying a corona, an
#: ageing history, a coating, a label or a dopant is never reduced to the group underneath it.
FUNCTIONALISATION_SPELLINGS: dict[str, str] = {
    "carboxylated": "COOH",
    "carboxyl": "COOH",
    "carboxylate": "COOH",
    "carboxy": "COOH",
    "cooh": "COOH",
    "carboxylic acid": "COOH",
    "carboxylic groups": "COOH",
    "carboxylic groups cooh": "COOH",
    "carboxyl groups": "COOH",
    "carboxyl groups cooh": "COOH",
    "carboxyl group cooh functionalized": "COOH",
    "carboxyl cooh": "COOH",
    "carboxylated cooh": "COOH",
    "carboxylate cooh": "COOH",
    "carboxyl modified": "COOH",
    "carboxylate modified": "COOH",
    "carboxylate modified cooh": "COOH",
    "carboxylate coated": "COOH",
    "carboxylated anionic": "COOH",
    "carboxyl functionalized": "COOH",
    "carboxyl cooh functionalized": "COOH",
    "carboxyl cooh surface groups": "COOH",
    "surface carboxyl groups": "COOH",
    "functionalized with carboxyl groups": "COOH",
    "amine": "NH2",
    "amino": "NH2",
    "aminated": "NH2",
    "nh2": "NH2",
    "amine nh2": "NH2",
    "nh2 amino": "NH2",
    "amino nh2": "NH2",
    "amine modified": "NH2",
    "amino modified": "NH2",
    "amino modified nh2": "NH2",
    "amine functionalized": "NH2",
    "amine functionalized nh2": "NH2",
    "amino functionalized nh2": "NH2",
    "amine groups": "NH2",
    "amino groups": "NH2",
    "amino groups nh2": "NH2",
    "amine nh2 functionalized": "NH2",
    "amine group nh2": "NH2",
    "sulfate": "SO4",
    "sulphate": "SO4",
    "sulfate modified": "SO4",
    "sulfate so4": "SO4",
    "sulfate surface groups": "SO4",
    "anionic sulfate groups": "SO4",
    "amidine": "AMIDINE",
    "amidine surface groups": "AMIDINE",
    "peg": "PEG",
    "polyethylene glycol": "PEG",
    "peg pegylated": "PEG",
    "plain": "BARE",
    "pristine": "BARE",
    "unmodified": "BARE",
    "unmodified bare": "BARE",
    "unfunctionalized": "BARE",
    "nonfunctionalized": "BARE",
    "non functionalized": "BARE",
    "non functionalized nf": "BARE",
    "non functionalized plain": "BARE",
    "nonfunctionalized plain": "BARE",
    "non functionalized surface": "BARE",
    "plain not functionalized": "BARE",
    "plain non functionalized": "BARE",
    "plain unmodified": "BARE",
    "plain none": "BARE",
    "plain no surface functionalisation": "BARE",
    "none bare": "BARE",
    "none plain": "BARE",
    "none pristine": "BARE",
    "none unmodified": "BARE",
    "none plain unmodified": "BARE",
    "none plain pristine": "BARE",
    "neutral unmodified": "BARE",
    "pristine unmodified": "BARE",
    # "pristine" keys to BARE on its own, so the unaged in "pristine (unaged)" adds nothing.
    # "unaged" alone is a weathering state, not a surface chemistry (Martin, 2026-09-27).
    "pristine unaged": "BARE",
    "without functional groups": "BARE",
    "without other surface functional groups": "BARE",
}


def material_key(text: str | None) -> str | None:
    """Canonical polymer code, or the normalised literal when the spelling is unrecognised."""
    flat = _norm(text)
    if flat is None:
        return None
    return MATERIAL_SPELLINGS.get(flat, f"literal:{flat}")


def functionalisation_key(text: str | None) -> str | None:
    """Canonical surface-state code, or the normalised literal. ``None`` stays ``None``.

    ``None`` is *not reported*, and it is never ``BARE``. A paper that does not say whether its
    particles carry COOH has not told you what particle it measured.
    """
    flat = _norm(text)
    if flat is None:
        return None
    return FUNCTIONALISATION_SPELLINGS.get(flat, f"literal:{flat}")


# Ordered most specific first, matched against the instrument string after camel-case is split
# and punctuation becomes whitespace. ZEN3600 is the model number of the Zetasizer Nano ZS, so
# the two spellings key together; ZS90 has a different scattering angle and does not.
_INSTRUMENT_MODELS: tuple[tuple[str, str], ...] = (
    (r"\b(?:nano ?)?zs ?90\b|\bzen ?3690", "malvern_zetasizer_zs90"),
    (r"\b(?:nano ?)?zsp\b", "malvern_zetasizer_nano_zsp"),
    (r"\bnano ?zs\b|\bzen ?3600", "malvern_zetasizer_nano_zs"),
    (r"\bzetasizer ultra\b", "malvern_zetasizer_ultra"),
    (r"\bzeta ?pals\b", "brookhaven_zetapals"),
    (r"\bnanobrook\b", "brookhaven_nanobrook"),
    (r"\bqnano\b", "izon_qnano"),
    (r"\bstabino\b", "microtrac_stabino"),
    (r"\bzetasizer\b|\bzeta sizer\b", "malvern_zetasizer_family"),
)


def instrument_key(text: str | None) -> str | None:
    """A model-level key for the instrument, falling back to the normalised literal.

    The instrument is the only proxy this corpus has for the mobility-to-zeta conversion:
    E2b measured that **5.6 %** of papers name the conversion model at all. A family-level
    string ("Zetasizer", no model) keys to the family and therefore does *not* match a named
    model — the brief records family level as a distinct, weaker statement.
    """
    if text is None:
        return None
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(text))
    flat = _norm(split)
    if flat is None:
        return None
    for pattern, key in _INSTRUMENT_MODELS:
        if re.search(pattern, flat):
            return key
    return f"literal:{flat}"


# --- the electrokinetic conversion ---------------------------------------------------------


def debye_length_nm(ionic_strength_mM: float) -> float:
    """kappa^-1 in nm for a 1:1 electrolyte in water at 25 degC: 0.304 / sqrt(I[M]).

    The 1:1 assumption is the limitation this carries; a divalent medium has a shorter Debye
    length than this returns. The comparability key uses it only to place a row in a conversion
    regime, but `mnp.demo.harmonise` also corrects reported values with it, and that is where
    the 1:1 assumption matters most.
    """
    if ionic_strength_mM is None or ionic_strength_mM <= 0:
        return math.inf
    return 0.304 / math.sqrt(ionic_strength_mM / 1000.0)


def henry_f(kappa_a: float) -> float:
    """Henry's function by Ohshima's approximation: 1.0 at the Huckel limit, 1.5 at Smoluchowski.

    Zeta is not measured. It is a model-dependent conversion of the measured mobility, and the
    two textbook limits differ by exactly this factor of 1.5. Two rows whose ``f`` differ have
    had materially different physics applied to them, whether or not either paper says so.
    """
    if kappa_a <= 0:
        return 1.0
    if kappa_a > 700:  # exp(-kappa_a) underflows; f is flat at the Smoluchowski limit here
        return 1.5
    denominator = kappa_a * (1.0 + 2.0 * math.exp(-kappa_a))
    return 1.0 + 1.0 / (2.0 * (1.0 + 2.5 / denominator) ** 3)


# --- the record ----------------------------------------------------------------------------


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _as_float(value: Any) -> float | None:
    value = _clean(value)
    return None if value is None else float(value)


def _as_str(value: Any) -> str | None:
    value = _clean(value)
    return None if value is None else str(value)


@dataclass(frozen=True)
class ZetaRow:
    """One row of the published table, carrying **only** what may decide comparability.

    There is deliberately no ``value``, ``value_text``, ``sd``, ``n`` or ``unit`` field, and no
    ``size_nominal_nm``: a rule that reads them cannot be written by accident.
    """

    row_id: str
    pmcid: str
    quantity: Quantity
    material: str | None
    functionalisation: str | None
    size_measured_nm: float | None
    conditions: MeasurementConditions

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> ZetaRow:
        conditions = MeasurementConditions(
            medium_text=_as_str(mapping.get("medium_text")),
            medium_class=MediumClass(_as_str(mapping.get("medium_class")) or "unreported"),
            ionic_strength_mM=_as_float(mapping.get("ionic_strength_mM")),
            ionic_strength_source=ValueSource(
                _as_str(mapping.get("ionic_strength_source")) or "unreported"
            ),
            pH=_as_float(mapping.get("pH")),
            pH_text=_as_str(mapping.get("pH_text")),
            temperature_C=_as_float(mapping.get("temperature_C")),
            temperature_qualifier=_as_str(mapping.get("temperature_qualifier")),
            instrument=_as_str(mapping.get("instrument")),
        )
        return cls(
            row_id=str(mapping["row_id"]),
            pmcid=str(mapping["pmcid"]),
            quantity=Quantity(str(mapping["quantity"])),
            material=_as_str(mapping.get("material")),
            functionalisation=_as_str(mapping.get("functionalisation")),
            size_measured_nm=_as_float(mapping.get("size_measured_nm")),
            conditions=conditions,
        )

    @classmethod
    def comparison_fields(cls):
        return fields(cls)

    @property
    def kappa_a(self) -> float | None:
        """kappa*a from the *measured* radius. ``None`` when either input is unreported."""
        if self.size_measured_nm is None:
            return None
        if not self.conditions.ionic_strength_reported:
            return None
        length = debye_length_nm(self.conditions.ionic_strength_mM)
        if math.isinf(length):
            return 0.0
        return (self.size_measured_nm / 2.0) / length


# --- the rules -----------------------------------------------------------------------------


def _pair_detail(a: Any, b: Any) -> str:
    """Order-independent rendering, so ``comparable(a, b) == comparable(b, a)``."""
    return " | ".join(sorted((str(a), str(b))))


def _close(a: float, b: float, *, rel: float) -> bool:
    scale = max(abs(a), abs(b))
    return True if scale == 0 else abs(a - b) / scale <= rel


def _measurand_blockers(a: ZetaRow, b: ZetaRow) -> Iterator[Blocker]:
    if a.quantity is not b.quantity:
        yield Blocker(
            "quantity_mismatch",
            "quantity",
            BlockerKind.mismatch,
            _pair_detail(a.quantity.value, b.quantity.value),
        )


def _identity_blockers(a: ZetaRow, b: ZetaRow) -> Iterator[Blocker]:
    if a.material is None or b.material is None:
        yield Blocker("material_unreported", "material", BlockerKind.unreported)
    elif material_key(a.material) != material_key(b.material):
        yield Blocker(
            "material_mismatch",
            "material",
            BlockerKind.mismatch,
            _pair_detail(material_key(a.material), material_key(b.material)),
        )

    if a.functionalisation is None or b.functionalisation is None:
        yield Blocker("functionalisation_unreported", "functionalisation", BlockerKind.unreported)
    elif functionalisation_key(a.functionalisation) != functionalisation_key(b.functionalisation):
        yield Blocker(
            "functionalisation_mismatch",
            "functionalisation",
            BlockerKind.mismatch,
            _pair_detail(
                functionalisation_key(a.functionalisation),
                functionalisation_key(b.functionalisation),
            ),
        )


def _condition_blockers(a: ZetaRow, b: ZetaRow) -> Iterator[Blocker]:
    ca, cb = a.conditions, b.conditions

    if not (ca.medium_reported and cb.medium_reported):
        yield Blocker("medium_unreported", "medium", BlockerKind.unreported)
    elif ca.medium_class is not cb.medium_class:
        yield Blocker(
            "medium_class_mismatch",
            "medium",
            BlockerKind.mismatch,
            _pair_detail(ca.medium_class.value, cb.medium_class.value),
        )
    elif _norm(ca.medium_text) != _norm(cb.medium_text):
        yield Blocker(
            "medium_text_mismatch",
            "medium",
            BlockerKind.mismatch,
            _pair_detail(ca.medium_text, cb.medium_text),
        )

    if not (ca.ionic_strength_reported and cb.ionic_strength_reported):
        yield Blocker("ionic_strength_unreported", "ionic_strength", BlockerKind.unreported)
    elif not _close(ca.ionic_strength_mM, cb.ionic_strength_mM, rel=IONIC_STRENGTH_REL_TOL):
        yield Blocker(
            "ionic_strength_mismatch",
            "ionic_strength",
            BlockerKind.mismatch,
            _pair_detail(ca.ionic_strength_mM, cb.ionic_strength_mM),
        )

    if not (ca.pH_reported and cb.pH_reported):
        yield Blocker("pH_unreported", "pH", BlockerKind.unreported)
    elif ca.pH is None or cb.pH is None:
        yield Blocker(
            "pH_not_numeric",
            "pH",
            BlockerKind.undecidable,
            _pair_detail(
                ca.pH_text if ca.pH is None else ca.pH, cb.pH_text if cb.pH is None else cb.pH
            ),
        )
    elif abs(ca.pH - cb.pH) > PH_TOL:
        yield Blocker("pH_mismatch", "pH", BlockerKind.mismatch, _pair_detail(ca.pH, cb.pH))

    if not (ca.temperature_reported and cb.temperature_reported):
        yield Blocker("temperature_unreported", "temperature", BlockerKind.unreported)
    elif ca.temperature_C is None or cb.temperature_C is None:
        yield Blocker(
            "temperature_not_numeric",
            "temperature",
            BlockerKind.undecidable,
            _pair_detail(ca.temperature_qualifier, cb.temperature_qualifier),
        )
    elif abs(ca.temperature_C - cb.temperature_C) > TEMPERATURE_TOL_C:
        yield Blocker(
            "temperature_mismatch",
            "temperature",
            BlockerKind.mismatch,
            _pair_detail(ca.temperature_C, cb.temperature_C),
        )

    if not (ca.instrument_reported and cb.instrument_reported):
        yield Blocker("instrument_unreported", "instrument", BlockerKind.unreported)
    elif instrument_key(ca.instrument) != instrument_key(cb.instrument):
        yield Blocker(
            "instrument_mismatch",
            "instrument",
            BlockerKind.mismatch,
            _pair_detail(instrument_key(ca.instrument), instrument_key(cb.instrument)),
        )


def _conversion_blockers(a: ZetaRow, b: ZetaRow) -> Iterator[Blocker]:
    """Applies to zeta only. Mobility is measured; zeta is converted from it."""
    if a.quantity is not Quantity.zeta_potential or b.quantity is not Quantity.zeta_potential:
        return
    if a.size_measured_nm is None or b.size_measured_nm is None:
        yield Blocker("size_measured_unreported", "size_measured_nm", BlockerKind.unreported)
        return
    kappa_a_a, kappa_a_b = a.kappa_a, b.kappa_a
    if kappa_a_a is None or kappa_a_b is None:
        return  # the ionic strength rule already blocked; do not double-count it
    f_a, f_b = henry_f(kappa_a_a), henry_f(kappa_a_b)
    if not _close(f_a, f_b, rel=HENRY_REL_TOL):
        yield Blocker(
            "conversion_regime_mismatch",
            "conversion_model",
            BlockerKind.mismatch,
            _pair_detail(f"ka={kappa_a_a:.3g},f={f_a:.3f}", f"ka={kappa_a_b:.3g},f={f_b:.3f}"),
        )


def _grade(blockers: Sequence[Blocker]) -> Comparability:
    if not blockers:
        return Comparability.comparable
    if all(blocker.code in _AXIS_CODES for blocker in blockers):
        return Comparability.conditionally_comparable
    return Comparability.not_comparable


def comparable(a: ZetaRow, b: ZetaRow) -> Verdict:
    """May these two measurements be compared, and what blocks it?

    ``comparable`` means a difference between the two reported numbers is attributable to the
    **particle**. ``conditionally_comparable`` means everything is stated and the rows differ
    only in a named, quantified condition, so they sit on a common axis — a titration, not a
    comparison. Anything else is ``not_comparable``, and the blockers say on which fields.
    """
    blockers = [
        *_measurand_blockers(a, b),
        *_identity_blockers(a, b),
        *_condition_blockers(a, b),
        *_conversion_blockers(a, b),
    ]
    blockers.sort(key=lambda blocker: blocker.code)
    return Verdict(_grade(blockers), tuple(blockers))


# --- the corpus ----------------------------------------------------------------------------


def load_rows(path: Path | None = None) -> list[ZetaRow]:
    frame = pd.read_csv(path or config.OUT_TABLES / "d1_zeta_table.csv")
    return [ZetaRow.from_mapping(record) for record in frame.to_dict(orient="records")]


def _fully_reported(row: ZetaRow) -> bool:
    """The cheap precondition every comparable pair must satisfy.

    Each ``*_unreported`` rule fires unconditionally when its field is missing in *either* row,
    so a row failing any of them cannot be half of a comparable pair whatever it is paired with.
    That is what makes the exhaustive census cheap: it is a filter on rows, not on pairs.
    """
    return (
        row.conditions.conditions_complete
        and row.material is not None
        and row.functionalisation is not None
        and (row.quantity is not Quantity.zeta_potential or row.size_measured_nm is not None)
    )


STRATA: tuple[str, ...] = (
    "same_paper",
    "cross_paper_same_material",
    "cross_paper_different_functionalisation",
    "cross_paper_different_material",
    "both_conditions_complete",
)

STRATUM_SIZES: dict[str, int] = {
    "same_paper": 60,
    "cross_paper_same_material": 60,
    "cross_paper_different_functionalisation": 60,
    "cross_paper_different_material": 30,
    "both_conditions_complete": 60,
}


@dataclass(frozen=True)
class PairSpec:
    stratum: str
    a: ZetaRow
    b: ZetaRow
    verdict: Verdict

    @property
    def question(self) -> str:
        return (
            f"May the {self.a.quantity.value} reported in {self.a.pmcid} (row {self.a.row_id}) "
            f"be compared with the {self.b.quantity.value} reported in {self.b.pmcid} "
            f"(row {self.b.row_id})? If not, which fields block the comparison?"
        )

    def as_record(self) -> dict[str, str]:
        return {
            "stratum": self.stratum,
            "row_id_a": self.a.row_id,
            "row_id_b": self.b.row_id,
            "pmcid_a": self.a.pmcid,
            "pmcid_b": self.b.pmcid,
            "same_paper": str(self.a.pmcid == self.b.pmcid),
            "verdict": self.verdict.verdict.value,
            "n_blockers": str(len(self.verdict.blockers)),
            "blockers": ";".join(self.verdict.codes),
            "blocker_kinds": ";".join(blocker.kind.value for blocker in self.verdict.blockers),
            "blocker_fields": ";".join(
                sorted({blocker.field for blocker in self.verdict.blockers})
            ),
            "question": self.question,
        }


def _spec(stratum: str, a: ZetaRow, b: ZetaRow) -> PairSpec:
    first, second = sorted((a, b), key=lambda row: row.row_id)
    return PairSpec(stratum, first, second, comparable(first, second))


def graded_census(rows: Sequence[ZetaRow]) -> list[PairSpec]:
    """Every pair the key does not call ``not_comparable``. Exhaustive, via the precondition.

    ``conditionally_comparable`` needs the same five conditions reported as ``comparable`` does
    — it differs only in whether they *agree* — so one row filter serves both censuses.
    """
    candidates = [row for row in rows if _fully_reported(row)]
    found: list[PairSpec] = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            spec = _spec("both_conditions_complete", a, b)
            if spec.verdict.verdict is not Comparability.not_comparable:
                found.append(spec)
    return found


def comparable_census(rows: Sequence[ZetaRow]) -> list[PairSpec]:
    """Every **fully** comparable pair in the corpus. The headline number of query kind E."""
    return [
        spec for spec in graded_census(rows) if spec.verdict.verdict is Comparability.comparable
    ]


def _stratum_predicate(stratum: str):
    def same_paper(a: ZetaRow, b: ZetaRow) -> bool:
        return a.pmcid == b.pmcid

    def cross_same_material(a: ZetaRow, b: ZetaRow) -> bool:
        keys = (material_key(a.material), material_key(b.material))
        return a.pmcid != b.pmcid and None not in keys and keys[0] == keys[1]

    def cross_different_functionalisation(a: ZetaRow, b: ZetaRow) -> bool:
        keys = (
            functionalisation_key(a.functionalisation),
            functionalisation_key(b.functionalisation),
        )
        return a.pmcid != b.pmcid and None not in keys and keys[0] != keys[1]

    def cross_different_material(a: ZetaRow, b: ZetaRow) -> bool:
        keys = (material_key(a.material), material_key(b.material))
        return a.pmcid != b.pmcid and None not in keys and keys[0] != keys[1]

    def both_complete(a: ZetaRow, b: ZetaRow) -> bool:
        return a.conditions.conditions_complete and b.conditions.conditions_complete

    return {
        "same_paper": same_paper,
        "cross_paper_same_material": cross_same_material,
        "cross_paper_different_functionalisation": cross_different_functionalisation,
        "cross_paper_different_material": cross_different_material,
        "both_conditions_complete": both_complete,
    }[stratum]


def _sample_stratum(
    rows: Sequence[ZetaRow], stratum: str, wanted: int, rng: random.Random
) -> list[PairSpec]:
    predicate = _stratum_predicate(stratum)
    pool = rows
    if stratum == "both_conditions_complete":
        pool = [row for row in rows if row.conditions.conditions_complete]
    elif stratum == "same_paper":
        by_paper: dict[str, list[ZetaRow]] = {}
        for row in rows:
            by_paper.setdefault(row.pmcid, []).append(row)
        pool = [row for row in rows if len(by_paper[row.pmcid]) > 1]
    seen: set[tuple[str, str]] = set()
    picked: list[PairSpec] = []
    attempts = 0
    limit = wanted * 4000
    while len(picked) < wanted and attempts < limit:
        attempts += 1
        a, b = rng.choice(pool), rng.choice(pool)
        if a.row_id == b.row_id or not predicate(a, b):
            continue
        key = tuple(sorted((a.row_id, b.row_id)))
        if key in seen:
            continue
        seen.add(key)
        picked.append(_spec(stratum, a, b))
    return picked


def build_query_set(rows: Sequence[ZetaRow], seed: int = RANDOM_SEED) -> list[PairSpec]:
    """The kind E query set: stratified samples plus **every** fully comparable pair.

    The census is unioned in rather than sampled, because "how many pairs in this corpus are
    fully comparable" is the measurement this query set exists to make. Sampling it away would
    hide the answer, and a stratified sample of 1 785 105 pairs would almost surely contain no
    positive at all. The conditionally comparable pairs come in for the same reason: they are
    the near misses, and an eval set of nothing but obvious noes measures nothing.
    """
    rng = random.Random(seed)
    picked: dict[tuple[str, str], PairSpec] = {}
    for stratum in STRATA:
        for spec in _sample_stratum(rows, stratum, STRATUM_SIZES[stratum], rng):
            picked.setdefault((spec.a.row_id, spec.b.row_id), spec)
    for spec in graded_census(rows):
        picked.setdefault((spec.a.row_id, spec.b.row_id), spec)
    return sorted(picked.values(), key=lambda spec: (spec.stratum, spec.a.row_id, spec.b.row_id))


FIELDNAMES: tuple[str, ...] = (
    "stratum",
    "row_id_a",
    "row_id_b",
    "pmcid_a",
    "pmcid_b",
    "same_paper",
    "verdict",
    "n_blockers",
    "blockers",
    "blocker_kinds",
    "blocker_fields",
    "question",
)


def write_query_set(pairs: Sequence[PairSpec], path: Path | None = None) -> Path:
    target = path or QUERY_SET_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(pair.as_record() for pair in pairs)
    return target


def read_query_set(path: Path | None = None) -> list[dict[str, str]]:
    with (path or QUERY_SET_PATH).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def stratum_counts(records: Iterable[dict[str, str]]) -> dict[str, int]:
    return dict(Counter(record["stratum"] for record in records))


def sample_pairs(
    rows: Sequence[ZetaRow], n: int, seed: int = RANDOM_SEED
) -> list[tuple[ZetaRow, ZetaRow]]:
    """Uniform seeded sample of distinct unordered pairs, for the corpus-wide distribution."""
    rng = random.Random(seed)
    seen: set[tuple[str, str]] = set()
    out: list[tuple[ZetaRow, ZetaRow]] = []
    while len(out) < n:
        a, b = rng.choice(rows), rng.choice(rows)
        if a.row_id == b.row_id:
            continue
        key = tuple(sorted((a.row_id, b.row_id)))
        if key in seen:
            continue
        seen.add(key)
        out.append((a, b))
    return out


def blocker_distribution(pairs: Iterable[tuple[ZetaRow, ZetaRow]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for a, b in pairs:
        counts.update(comparable(a, b).codes)
    return counts


if __name__ == "__main__":  # pragma: no cover - regeneration entry point
    written = write_query_set(build_query_set(load_rows()))
    print(f"wrote {written}")
