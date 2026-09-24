"""Query kinds A–D of the tool-value grid — the questions every cell is scored on.

Kind E already exists in ``comparability.py`` and is not rebuilt here. These four match its
shape: generated deterministically from one seed, every question carrying the rows or papers it
came from, every answer re-derivable from the corpus so the key cannot silently drift away from
the data. Nothing here calls a model, a network or a clock.

============  ==========================================  =====================================
kind          question                                    ground truth
============  ==========================================  =====================================
A  lookup     value plus the condition it was measured    ``data/interim/annotation/gold_50.csv``
               under
B  absence    what a paper did **not** report             the ``*_reported`` booleans
C  comparison a numeric filter across papers              the filter, re-run
D  mechanism  why a physical effect happens               *no key exists* — see below
============  ==========================================  =====================================

**The question is not the answer key, and the separation is structural.** A record on disk
carries both, but :func:`question_from_record` copies across only the columns named in
:data:`TARGET_COLUMNS`, an allow-list checked against :data:`ANSWER_COLUMNS` by a test. A cell's
context builder is handed a :class:`Question` and never an :class:`AnswerKey`, so a builder that
prints the answer into its own prompt cannot be written by accident.

**Kind B is not all absences.** Two thirds of it are papers that reported nothing for the field
and one third are papers that did; a cell that answers "not reported" to everything scores 0.67
and a fabrication rate of zero, which would look like the best cell in the grid. The presence
half is what stops that.

**Kind D, and why it is scored the way it is.** There is no deterministic key for "why does a
protein corona change measured zeta". Three options were available and one had to be argued for:
score by pairwise preference between two cells' answers, judge against the passage the question
was built from, or leave the kind unscored but reported.

Pairwise preference needs a model at scoring time, which would put judgement inside the number
the talk prints — and this repo already measured its own judge panel deciding at kappa = -0.05.
Leaving the kind unscored deletes the one delta kind D exists to produce: "prose retrieval wins
here" becomes an assertion rather than a measurement.

So kind D is judged against passages — but against **every** passage in the corpus that states
the mechanism, not only the one the question was seeded from. That fixes the obvious defect of
the passage approach (a correct answer grounded somewhere else scoring zero), and it fixes it in
the direction that matters: the acceptable set is a set of *prose lines*, it exists only in the
prose substrate, and the structured table has no field that can reach it. Kind D is therefore
constructed so that it can only be accused of being rigged **in favour of** prose retrieval and
against the knowledge base — which is the direction that makes the rest of the grid honest.

What that key cannot decide is whether the explanation is *correct*; it decides whether the
explanation is *grounded*. The correctness judgement is left as an explicit seam
(``scoring.PreferenceVerdict``), supplied from outside, never computed here, and reported apart
from every model-free number.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from mnp import config
from mnp.corpus import jats, lines
from mnp.eval import comparability
from mnp.eval.comparability import functionalisation_key, material_key

RANDOM_SEED = 20260918


class QueryKind(StrEnum):
    a = "A"
    b = "B"
    c = "C"
    d = "D"
    #: Built by `comparability.py`, not here. Present so all five kinds run through one harness
    #: and one scorer instead of two.
    e = "E"


KIND_PATHS: dict[QueryKind, Path] = {
    QueryKind.a: config.QUERIES / "kind_a_lookup.csv",
    QueryKind.b: config.QUERIES / "kind_b_absence.csv",
    QueryKind.c: config.QUERIES / "kind_c_comparison.csv",
    QueryKind.d: config.QUERIES / "kind_d_mechanism.csv",
    QueryKind.e: comparability.QUERY_SET_PATH,
}

FIELDNAMES: dict[QueryKind, tuple[str, ...]] = {
    QueryKind.a: (
        "qid",
        "kind",
        "pmcid",
        "question",
        "material",
        "functionalisation",
        "medium_text",
        "quantity",
        "gold_row_id",
        "answer_value",
        "answer_unit",
        "answer_ionic_strength_reported",
        "answer_ionic_strength_mM",
        "evidence_line_ids",
        "source",
    ),
    QueryKind.b: (
        "qid",
        "kind",
        "pmcid",
        "question",
        "field",
        "answer_reported",
        "answer_value",
        "n_rows",
        "row_ids",
        "evidence_line_ids",
        "gold_cross_check",
        "source",
    ),
    QueryKind.c: (
        "qid",
        "kind",
        "question",
        "filter_json",
        "answer_pmcids",
        "answer_row_ids",
        "n_papers",
        "n_rows",
        "source",
    ),
    QueryKind.d: (
        "qid",
        "kind",
        "topic",
        "question",
        "structured_field",
        "seed_pmcid",
        "seed_line_id",
        "content_terms",
        "acceptable_line_ids",
        "n_acceptable_lines",
        "n_acceptable_papers",
        "source",
    ),
    QueryKind.e: comparability.FIELDNAMES,
}

#: Every column that is, or addresses, the answer. Nothing here may reach a `Question`.
ANSWER_COLUMNS: frozenset[str] = frozenset(
    {
        "gold_row_id",
        "answer_value",
        "answer_unit",
        "answer_ionic_strength_reported",
        "answer_ionic_strength_mM",
        "answer_reported",
        "answer_pmcids",
        "answer_row_ids",
        "row_ids",
        "n_rows",
        "n_papers",
        "evidence_line_ids",
        "seed_pmcid",
        "seed_line_id",
        "content_terms",
        "acceptable_line_ids",
        "n_acceptable_lines",
        "n_acceptable_papers",
        "gold_cross_check",
        "verdict",
        "n_blockers",
        "blockers",
        "blocker_kinds",
    }
)

#: What a static router is allowed to condition on: the question's own stated conditions.
TARGET_COLUMNS: dict[QueryKind, tuple[str, ...]] = {
    QueryKind.a: ("material", "functionalisation", "medium_text", "quantity"),
    QueryKind.b: ("field",),
    QueryKind.c: ("filter_json",),
    QueryKind.d: ("topic", "structured_field"),
    QueryKind.e: ("row_id_a", "row_id_b"),
}


@dataclass(frozen=True)
class Question:
    """What the answering agent is shown. It carries no field of the answer, by construction."""

    qid: str
    kind: QueryKind
    text: str
    scope: tuple[str, ...] = ()
    target: tuple[tuple[str, str], ...] = ()

    def targeting(self, name: str, default: str = "") -> str:
        return dict(self.target).get(name, default)


@dataclass(frozen=True)
class AnswerKey:
    """What the scorer is shown. Never passed to a cell."""

    qid: str
    kind: QueryKind
    fields: tuple[tuple[str, str], ...] = ()

    def get(self, name: str, default: str = "") -> str:
        return dict(self.fields).get(name, default) or default

    @property
    def evidence_line_ids(self) -> frozenset[str]:
        return frozenset(part for part in self.get("evidence_line_ids").split(";") if part)


def question_from_record(record: Mapping[str, str]) -> Question:
    if "qid" not in record:  # a kind E pair, whose natural key is the two row ids
        return _comparability_question(record)
    kind = QueryKind(record.get("kind") or record["qid"].split("-")[0])
    pmcid = (record.get("pmcid") or "").strip()
    target = tuple(
        (name, str(record.get(name, "")))
        for name in TARGET_COLUMNS[kind]
        if str(record.get(name, "")).strip()
    )
    return Question(
        qid=record["qid"],
        kind=kind,
        text=record["question"],
        scope=(pmcid,) if pmcid else (),
        target=target,
    )


def _comparability_question(record: Mapping[str, str]) -> Question:
    """One row of `queries/kind_e_comparability.csv` as a `Question`, carrying no verdict.

    The two row ids are targeting, not answer: they name the measurements the question already
    names in words. `verdict`, `blockers` and `blocker_kinds` stay behind in the key.
    """
    return Question(
        qid=f"E-{record['row_id_a']}__{record['row_id_b']}",
        kind=QueryKind.e,
        text=record["question"],
        scope=tuple(sorted({record["pmcid_a"], record["pmcid_b"]})),
        target=tuple((name, record[name]) for name in TARGET_COLUMNS[QueryKind.e]),
    )


def answer_from_record(record: Mapping[str, str]) -> AnswerKey:
    if "qid" not in record:
        return AnswerKey(
            qid=f"E-{record['row_id_a']}__{record['row_id_b']}",
            kind=QueryKind.e,
            fields=tuple((name, str(value)) for name, value in record.items()),
        )
    kind = QueryKind(record.get("kind") or record["qid"].split("-")[0])
    keep = ANSWER_COLUMNS | {"pmcid"}
    return AnswerKey(
        qid=record["qid"],
        kind=kind,
        fields=tuple((name, str(value)) for name, value in record.items() if name in keep),
    )


# -- the corpus, loaded once ---------------------------------------------------------------


class CorpusLine(NamedTuple):
    pmcid: str
    n: int
    line_id: str
    text: str


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool | None:
    """Tri-state: a blank gold cell is *unannotated*, and is never `False` and never `True`."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        return text in {"true", "1", "yes"}
    return bool(value)


def _float(value: Any) -> float | None:
    text = _str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@cache
def gold_rows() -> tuple[dict[str, Any], ...]:
    frame = pd.read_csv(config.ANNOTATION / "gold_50.csv")
    return tuple(frame.to_dict(orient="records"))


@cache
def zeta_table() -> tuple[dict[str, Any], ...]:
    frame = pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")
    return tuple(frame.to_dict(orient="records"))


@cache
def doc_for(pmcid: str) -> lines.LinedDoc:
    article = jats.parse((config.EPMC_XML_DIR / f"{pmcid}.xml").read_bytes())
    article.pmcid = pmcid
    return lines.build_lines(article)


@cache
def corpus_lines() -> tuple[CorpusLine, ...]:
    """Every line of every paper the published table draws on. ~21 700 lines, ~4 s, no tokens."""
    out: list[CorpusLine] = []
    for pmcid in sorted({_str(row["pmcid"]) for row in zeta_table()}):
        if not (config.EPMC_XML_DIR / f"{pmcid}.xml").is_file():
            continue
        for line in doc_for(pmcid).lines:
            out.append(CorpusLine(pmcid, line.n, line.line_id, line.text))
    return tuple(out)


# -- kind A: a value and the condition it was measured under --------------------------------

KIND_A_N = 30
KIND_A_MAX_PER_PAPER = 4


def _particle_phrase(row: Mapping[str, Any]) -> str:
    material = _str(row.get("material"))
    functionalisation = _str(row.get("functionalisation"))
    if functionalisation:
        return f"{material}, {functionalisation}"
    return material


def _kind_a_candidates() -> list[dict[str, Any]]:
    return [
        row
        for row in gold_rows()
        if _str(row.get("quantity")) == "zeta_potential"
        and _float(row.get("value")) is not None
        and _str(row.get("medium_text"))
        and _str(row.get("material"))
        and _str(row.get("evidence_quote"))
        and (config.EPMC_XML_DIR / f"{_str(row['pmcid'])}.xml").is_file()
    ]


def _round_robin(
    groups: Mapping[str, Sequence[dict[str, Any]]], wanted: int, cap: int, rng: random.Random
) -> list[dict[str, Any]]:
    """One row per paper in a seeded paper order, going round again until `wanted` is met.

    Spreading matters: a lookup set drawn from three papers measures three parses, not thirty
    questions, and a cell that happens to read those three well would look general.
    """
    order = sorted(groups)
    rng.shuffle(order)
    picked: list[dict[str, Any]] = []
    for depth in range(cap):
        for pmcid in order:
            rows = groups[pmcid]
            if depth < len(rows) and len(picked) < wanted:
                picked.append(rows[depth])
        if len(picked) >= wanted:
            break
    return picked


def build_kind_a(seed: int = RANDOM_SEED) -> list[dict[str, str]]:
    rng = random.Random(f"{seed}:A")
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(_kind_a_candidates(), key=lambda r: _str(r["row_id"])):
        groups.setdefault(_str(row["pmcid"]), []).append(row)
    picked = _round_robin(groups, KIND_A_N, KIND_A_MAX_PER_PAPER, rng)

    records: list[dict[str, str]] = []
    for index, row in enumerate(sorted(picked, key=lambda r: _str(r["row_id"])), start=1):
        pmcid = _str(row["pmcid"])
        doc = doc_for(pmcid)
        numbers = lines.locate(doc, _str(row["evidence_quote"]))
        if not numbers:
            continue
        reported = bool(row.get("I_reported")) and _float(row.get("ionic_strength_mM")) is not None
        records.append(
            {
                "qid": f"A-{index:03d}",
                "kind": "A",
                "pmcid": pmcid,
                "question": (
                    f"In {pmcid}, what zeta potential was reported for "
                    f"{_particle_phrase(row)} particles in {_str(row['medium_text'])}, "
                    f"and at what ionic strength was that measurement made?"
                ),
                "material": _str(row.get("material")),
                "functionalisation": _str(row.get("functionalisation")),
                "medium_text": _str(row.get("medium_text")),
                "quantity": "zeta_potential",
                "gold_row_id": _str(row["row_id"]),
                "answer_value": f"{_float(row['value'])}",
                "answer_unit": _str(row.get("unit")) or "mV",
                "answer_ionic_strength_reported": str(reported),
                "answer_ionic_strength_mM": (
                    f"{_float(row.get('ionic_strength_mM'))}" if reported else ""
                ),
                "evidence_line_ids": ";".join(doc.lines[n - 1].line_id for n in numbers),
                "source": f"gold_50.csv:{_str(row['row_id'])}",
            }
        )
    return records


# -- kind B: absence, stated as a positive claim ---------------------------------------------


@dataclass(frozen=True)
class AbsenceField:
    """A condition a paper either reported or did not, and the words the question uses for it."""

    name: str
    asked_as: str
    column: str
    unit: str
    gold_column: str
    #: (absent questions, reported questions). The reported half is not decoration: without it
    #: a cell that answers "not reported" to everything wins the kind outright.
    wanted: tuple[int, int]


ABSENCE_FIELDS: dict[str, AbsenceField] = {
    "ionic_strength": AbsenceField(
        "ionic_strength", "ionic strength", "ionic_strength_mM", "mM", "I_reported", (10, 4)
    ),
    "pH": AbsenceField("pH", "pH", "pH", "", "pH_reported", (5, 3)),
    "temperature": AbsenceField(
        "temperature", "temperature", "temperature_C", "degrees C", "T_reported", (5, 3)
    ),
}


def _papers_by_report_state(field: AbsenceField) -> tuple[list[str], list[tuple[str, float]]]:
    """(papers that reported nothing, papers that reported exactly one value)."""
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for row in zeta_table():
        by_paper.setdefault(_str(row["pmcid"]), []).append(row)
    absent: list[str] = []
    present: list[tuple[str, float]] = []
    for pmcid in sorted(by_paper):
        rows = by_paper[pmcid]
        flags = {bool(row[f"{field.name}_reported"]) for row in rows}
        if flags == {False}:
            absent.append(pmcid)
        elif flags == {True}:
            values = {_float(row[field.column]) for row in rows}
            if len(values) == 1 and None not in values:
                present.append((pmcid, values.pop()))
    return absent, present


def _gold_cross_check(pmcid: str, field: AbsenceField, reported: bool) -> str:
    """Does the hand-annotated gold set agree that this paper did or did not report it?

    The key for kind B is the extraction's own `*_reported` boolean, so it inherits whatever the
    extraction got wrong. For the 50 papers that also carry a hand annotation the claim can be
    checked against a second reader, and this column says which questions those are.
    """
    rows = [row for row in gold_rows() if _str(row["pmcid"]) == pmcid]
    if not rows:
        return "not_in_gold"
    measured = [row for row in rows if _str(row.get("quantity"))]
    if not measured:
        # The annotator recorded this paper as reporting no measurement at all. That is a
        # statement about the extraction, not about this field, so it is neither agreement nor
        # disagreement -- and it is worth seeing, which is why it gets its own label.
        return "gold_no_measurement"
    # `bool(nan)` is True, and a blank flag in the gold sheet is nan. Reading it as "reported"
    # manufactured a disagreement out of a cell nobody filled in; hence the explicit tri-state.
    flags = {_bool(row.get(field.gold_column)) for row in measured}
    flags.discard(None)
    if not flags:
        return "gold_no_flag"
    if len(flags) != 1:
        return "gold_mixed"
    return "agree" if flags.pop() is reported else "disagree"


def _split_sample(
    pool: Sequence[str],
    annotated: frozenset[str] | set[str],
    used: set[str],
    wanted: int,
    rng: random.Random,
) -> list[str]:
    """Half the absences from papers a human also annotated, half from the wider corpus.

    The key for kind B is the extraction's own `*_reported` boolean, so it inherits the
    extraction's mistakes. Drawing every question from the 50 hand-annotated papers would make
    the key checkable and the sample unrepresentative; drawing none from them would make the
    headline metric rest on an unverified label. Half of each, and `gold_cross_check` on every
    row says which half a question came from.
    """
    confirmed = sorted(p for p in pool if p in annotated and p not in used)
    rest = sorted(p for p in pool if p not in annotated and p not in used)
    take = min(wanted // 2, len(confirmed))
    picked = rng.sample(confirmed, take)
    picked += rng.sample(rest, wanted - take)
    return picked


def build_kind_b(seed: int = RANDOM_SEED) -> list[dict[str, str]]:
    rng = random.Random(f"{seed}:B")
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for row in zeta_table():
        by_paper.setdefault(_str(row["pmcid"]), []).append(row)

    annotated = {_str(row["pmcid"]) for row in gold_rows()}
    used: set[str] = set()
    chosen: list[tuple[AbsenceField, str, float | None]] = []
    for name in sorted(ABSENCE_FIELDS):
        field = ABSENCE_FIELDS[name]
        absent, present = _papers_by_report_state(field)
        n_absent, n_present = field.wanted
        for pmcid in _split_sample(absent, annotated, used, n_absent, rng):
            used.add(pmcid)
            chosen.append((field, pmcid, None))
        pool = [pair for pair in present if pair[0] not in used]
        for pmcid, value in rng.sample(pool, n_present):
            used.add(pmcid)
            chosen.append((field, pmcid, value))

    chosen.sort(key=lambda item: (item[0].name, item[1]))
    records: list[dict[str, str]] = []
    for index, (field, pmcid, value) in enumerate(chosen, start=1):
        rows = by_paper[pmcid]
        reported = value is not None
        evidence = (
            ";".join(
                sorted(
                    {
                        part
                        for row in rows
                        for part in _str(row.get("evidence_line_ids")).split(";")
                        if part
                    }
                )
            )
            if reported
            else ""
        )
        records.append(
            {
                "qid": f"B-{index:03d}",
                "kind": "B",
                "pmcid": pmcid,
                "question": (
                    f"What {field.asked_as} was used for the zeta-potential and "
                    f"electrophoretic-mobility measurements reported in {pmcid}?"
                ),
                "field": field.name,
                "answer_reported": str(reported),
                "answer_value": f"{value}" if reported else "",
                "n_rows": str(len(rows)),
                "row_ids": ";".join(sorted(_str(row["row_id"]) for row in rows)),
                "evidence_line_ids": evidence,
                "gold_cross_check": _gold_cross_check(pmcid, field, reported),
                "source": f"d1_zeta_table.csv:{pmcid}:{field.name}_reported",
            }
        )
    return records


# -- kind C: a numeric filter across papers ---------------------------------------------------

KIND_C_N = 10
#: A filter matching one paper measures nothing and one matching half the corpus is not a query.
KIND_C_MIN_PAPERS = 2
KIND_C_MAX_PAPERS = 40
#: Two questions from each template family. An unstratified draw was five-tenths size filters.
KIND_C_FAMILIES: tuple[str, ...] = (
    "ionic_strength",
    "pH",
    "size",
    "functionalisation",
    "medium_class",
)
KIND_C_PER_FAMILY = 2

_QUANTITY_WORDS = {
    "zeta_potential": "zeta potential",
    "electrophoretic_mobility": "electrophoretic mobility",
}


@dataclass(frozen=True)
class FilterSpec:
    """A structured filter over the published table. The question *is* this, in words."""

    quantity: str | None = None
    material: str | None = None
    functionalisation: str | None = None
    medium_class: str | None = None
    ionic_strength_min: float | None = None
    ionic_strength_max: float | None = None
    pH_min: float | None = None
    pH_max: float | None = None
    size_min: float | None = None
    size_max: float | None = None

    def as_json(self) -> str:
        payload = {name: value for name, value in sorted(vars(self).items()) if value is not None}
        return json.dumps(payload, sort_keys=True)


def filter_from_record(record: Mapping[str, str]) -> FilterSpec:
    return FilterSpec(**json.loads(record["filter_json"]))


def apply_filter(table: Iterable[Mapping[str, Any]], spec: FilterSpec) -> list[Mapping[str, Any]]:
    """The filter, run. `None` in a field means the field is not constrained.

    A row whose value is unreported never matches a numeric range. That is the same rule the
    comparability key uses and for the same reason: absence is not a number, and a range that
    quietly admitted unreported rows would answer a different question.
    """
    out: list[Mapping[str, Any]] = []
    for row in table:
        if spec.quantity and _str(row.get("quantity")) != spec.quantity:
            continue
        if spec.material and material_key(_str(row.get("material")) or None) != spec.material:
            continue
        if spec.functionalisation and (
            functionalisation_key(_str(row.get("functionalisation")) or None)
            != spec.functionalisation
        ):
            continue
        if spec.medium_class and _str(row.get("medium_class")) != spec.medium_class:
            continue
        pairs = (
            (spec.ionic_strength_min, spec.ionic_strength_max, "ionic_strength_mM"),
            (spec.pH_min, spec.pH_max, "pH"),
            (spec.size_min, spec.size_max, "size_measured_nm"),
        )
        for low, high, column in pairs:
            if low is None and high is None:
                continue
            value = _float(row.get(column))
            if value is None or (low is not None and value < low):
                break
            if high is not None and value > high:
                break
        else:
            out.append(row)
    return out


def _kind_c_candidates() -> list[tuple[str, FilterSpec, str]]:
    """Every filter the generator may draw from: (family, filter, the English it is asked in).

    The family is what the sample is stratified on. An unstratified draw from this list came
    out five-tenths size filters and zero ionic-strength filters, which would have measured
    numeric filtering on the one condition the abstract is not about.
    """
    out: list[tuple[str, FilterSpec, str]] = []
    for material in ("PS", "PE", "PET", "PVC", "PP", "PMMA"):
        for low, high in ((0.0, 10.0), (10.0, 100.0), (100.0, 200.0), (200.0, 1000.0)):
            out.append(
                (
                    "ionic_strength",
                    FilterSpec(
                        quantity="zeta_potential",
                        material=material,
                        ionic_strength_min=low,
                        ionic_strength_max=high,
                    ),
                    f"Which papers report a zeta potential for {material} particles measured "
                    f"at an ionic strength between {low:g} and {high:g} mM?",
                )
            )
        for low, high in ((2.0, 5.0), (5.0, 7.0), (7.0, 9.0)):
            out.append(
                (
                    "pH",
                    FilterSpec(
                        quantity="zeta_potential",
                        material=material,
                        pH_min=low,
                        pH_max=high,
                    ),
                    f"Which papers report a zeta potential for {material} particles measured "
                    f"at a pH between {low:g} and {high:g}?",
                )
            )
        for low, high in ((0.0, 100.0), (100.0, 500.0), (500.0, 5000.0)):
            out.append(
                (
                    "size",
                    FilterSpec(
                        quantity="zeta_potential",
                        material=material,
                        size_min=low,
                        size_max=high,
                    ),
                    f"Which papers report a zeta potential for {material} particles whose "
                    f"measured size is between {low:g} and {high:g} nm?",
                )
            )
    for material in ("PS", "PE", "PET"):
        for functionalisation in ("COOH", "NH2", "BARE"):
            out.append(
                (
                    "functionalisation",
                    FilterSpec(
                        quantity="zeta_potential",
                        material=material,
                        functionalisation=functionalisation,
                    ),
                    f"Which papers report a zeta potential for {material} particles "
                    f"functionalised as {functionalisation}?",
                )
            )
    for medium in ("DI_water", "buffer", "salt_solution", "culture_medium", "environmental_water"):
        for material in ("PS", "PE"):
            out.append(
                (
                    "medium_class",
                    FilterSpec(quantity="zeta_potential", material=material, medium_class=medium),
                    f"Which papers report a zeta potential for {material} particles measured "
                    f"in {medium.replace('_', ' ')}?",
                )
            )
    for low, high in ((100.0, 200.0), (10.0, 50.0)):
        out.append(
            (
                "ionic_strength",
                FilterSpec(
                    quantity="electrophoretic_mobility",
                    ionic_strength_min=low,
                    ionic_strength_max=high,
                ),
                f"Which papers report an electrophoretic mobility measured at an ionic "
                f"strength between {low:g} and {high:g} mM?",
            )
        )
    return out


def build_kind_c(seed: int = RANDOM_SEED) -> list[dict[str, str]]:
    rng = random.Random(f"{seed}:C")
    table = zeta_table()
    usable: dict[str, list[tuple[FilterSpec, str, list[Mapping[str, Any]]]]] = {}
    seen: set[tuple[str, ...]] = set()
    for family, spec, text in _kind_c_candidates():
        rows = apply_filter(table, spec)
        pmcids = tuple(sorted({_str(row["pmcid"]) for row in rows}))
        if not KIND_C_MIN_PAPERS <= len(pmcids) <= KIND_C_MAX_PAPERS or pmcids in seen:
            continue
        seen.add(pmcids)
        usable.setdefault(family, []).append((spec, text, rows))
    picked: list[tuple[FilterSpec, str, list[Mapping[str, Any]]]] = []
    for family in KIND_C_FAMILIES:
        pool = usable.get(family, [])
        picked += rng.sample(pool, min(KIND_C_PER_FAMILY, len(pool)))
    picked.sort(key=lambda item: item[0].as_json())

    records: list[dict[str, str]] = []
    for index, (spec, text, rows) in enumerate(picked, start=1):
        pmcids = sorted({_str(row["pmcid"]) for row in rows})
        records.append(
            {
                "qid": f"C-{index:03d}",
                "kind": "C",
                "question": f"{text} List every PMCID.",
                "filter_json": spec.as_json(),
                "answer_pmcids": ";".join(pmcids),
                "answer_row_ids": ";".join(sorted(_str(row["row_id"]) for row in rows)),
                "n_papers": str(len(pmcids)),
                "n_rows": str(len(rows)),
                "source": "d1_zeta_table.csv:filter",
            }
        )
    return records


# -- kind D: mechanism, the kind the knowledge base has no field for --------------------------

KIND_D_N = 10
#: Below this a topic is one paper's opinion rather than a mechanism the corpus states.
MIN_ACCEPTABLE_LINES = 8

#: A line only counts as stating a mechanism if it also carries a causal connective. Without
#: this, "protein corona" in a methods list would count as an explanation of anything.
CAUSAL_CUES: tuple[str, ...] = (
    "because",
    "due to",
    "owing to",
    "leads to",
    "lead to",
    "results in",
    "result in",
    "resulting in",
    "attributed to",
    "attributable to",
    "caused by",
    "thereby",
    "thus",
    "therefore",
    "explains",
    "explained by",
    "responsible for",
    "as a result",
    "consequently",
    "which reduces",
    "which increases",
)


@dataclass(frozen=True)
class MechanismTopic:
    """A mechanism, the words the corpus states it in, and the question asked about it.

    `subject` and `effect` are both required in a line, so a passage naming the cause without
    naming what it does to the measurement is not evidence for this question.
    """

    name: str
    question: str
    subject: tuple[str, ...]
    effect: tuple[str, ...]


def _topic(name: str, question: str, subject: Sequence[str], effect: Sequence[str]):
    return MechanismTopic(name, question, tuple(subject), tuple(effect))


MECHANISM_TOPICS: dict[str, MechanismTopic] = {
    topic.name: topic
    for topic in (
        _topic(
            "protein_corona",
            "Why does a protein corona change the zeta potential measured for a plastic particle?",
            ["protein corona", "biomolecular corona", "corona formation", "protein adsorption"],
            ["zeta", "charge", "surface charge", "mobility"],
        ),
        _topic(
            "double_layer",
            "Why does raising the ionic strength of the medium reduce the magnitude of a "
            "measured zeta potential?",
            ["ionic strength", "electrolyte concentration", "salt concentration", "debye"],
            ["double layer", "screening", "screened", "compress", "shield"],
        ),
        _topic(
            "ph_dissociation",
            "Why does the pH of the dispersion change the sign and magnitude of a particle's "
            "zeta potential?",
            ["ph"],
            ["deprotonat", "protonat", "dissociat", "isoelectric", "carboxyl"],
        ),
        _topic(
            "nom",
            "Why does natural organic matter in environmental water change a particle's "
            "measured surface charge?",
            ["natural organic matter", "humic", "fulvic", "dissolved organic"],
            ["zeta", "charge", "adsorb", "coat"],
        ),
        _topic(
            "divalent",
            "Why do divalent cations such as Ca2+ destabilise a plastic-particle suspension "
            "more than monovalent ones?",
            ["ca2+", "calcium", "divalent", "mg2+", "cacl2"],
            ["aggregat", "charge", "screening", "bridg", "destabil"],
        ),
        _topic(
            "uv_ageing",
            "Why does UV weathering make a plastic particle's zeta potential more negative?",
            ["uv", "weather", "photo-ox", "photooxidat", "aging", "ageing"],
            ["carbonyl", "carboxyl", "zeta", "charge", "oxidis", "oxidiz"],
        ),
        _topic(
            "functionalisation",
            "Why do carboxyl- and amine-functionalised particles of the same polymer carry "
            "opposite surface charges?",
            ["carboxyl", "amine", "amino", "-cooh", "nh2", "sulfate"],
            ["positive", "negative", "zeta", "charge", "sign"],
        ),
        _topic(
            "dlvo",
            "Why does a zeta potential close to zero predict that a suspension will aggregate?",
            ["dlvo", "colloidal stability", "electrostatic repulsion", "aggregation"],
            ["zeta", "charge", "stability", "barrier", "repuls"],
        ),
        _topic(
            "conversion_model",
            "Why does the choice between the Smoluchowski and Huckel limits change the zeta "
            "potential obtained from a measured mobility?",
            ["smoluchowski", "hückel", "huckel", "henry"],
            ["mobility", "zeta", "convert", "approximation", "equation"],
        ),
        _topic(
            "surfactant",
            "Why does a surfactant or dispersant used to suspend particles change the zeta "
            "potential that is then measured?",
            ["surfactant", "sds", "tween", "stabiliser", "stabilizer", "dispersant"],
            ["zeta", "charge", "adsorb", "coat"],
        ),
        _topic(
            "biofilm",
            "Why does an eco-corona or biofilm on a plastic particle change its measured "
            "surface charge?",
            ["biofilm", "eco-corona", "ecocorona", "eps", "extracellular polymeric"],
            ["zeta", "charge", "surface"],
        ),
        _topic(
            "size_effect",
            "Why does particle size affect how much adsorbed material changes a measured zeta "
            "potential?",
            ["specific surface area", "surface-to-volume", "curvature"],
            ["zeta", "charge", "adsorption"],
        ),
    )
}


def acceptable_lines(corpus: Iterable[CorpusLine], topic: MechanismTopic) -> set[str]:
    """Every line in the corpus that states this mechanism. The answer key for one kind D question.

    Corpus-wide rather than one seed passage, because the known defect of judging an
    explanation against the passage it was written from is that a correct answer grounded
    somewhere else scores zero.
    """
    found: set[str] = set()
    for line in corpus:
        low = line.text.lower()
        if not any(cue in low for cue in topic.subject):
            continue
        if not any(cue in low for cue in topic.effect):
            continue
        if not any(cue in low for cue in CAUSAL_CUES):
            continue
        found.add(line.line_id)
    return found


def build_kind_d(seed: int = RANDOM_SEED) -> list[dict[str, str]]:
    rng = random.Random(f"{seed}:D")
    corpus = corpus_lines()
    by_id = {line.line_id: line for line in corpus}
    usable = []
    for name in sorted(MECHANISM_TOPICS):
        topic = MECHANISM_TOPICS[name]
        ids = acceptable_lines(corpus, topic)
        papers = {by_id[line_id].pmcid for line_id in ids}
        if len(ids) >= MIN_ACCEPTABLE_LINES and len(papers) > 1:
            usable.append((topic, sorted(ids), sorted(papers)))
    picked = rng.sample(usable, KIND_D_N) if len(usable) > KIND_D_N else usable
    picked.sort(key=lambda item: item[0].name)

    records: list[dict[str, str]] = []
    for index, (topic, ids, papers) in enumerate(picked, start=1):
        seed_id = rng.choice(ids)
        seed_line = by_id[seed_id]
        low = seed_line.text.lower()
        terms = sorted({cue for cue in (*topic.subject, *topic.effect) if cue in low})
        records.append(
            {
                "qid": f"D-{index:03d}",
                "kind": "D",
                "topic": topic.name,
                "question": topic.question,
                # The point of the kind. If a mechanism were answerable from the table, kind D
                # would not be testing what it exists to test.
                "structured_field": "none",
                "seed_pmcid": seed_line.pmcid,
                "seed_line_id": seed_id,
                "content_terms": ";".join(terms),
                "acceptable_line_ids": ";".join(ids),
                "n_acceptable_lines": str(len(ids)),
                "n_acceptable_papers": str(len(papers)),
                "source": f"corpus_lines:{topic.name}",
            }
        )
    return records


# -- reading and writing -----------------------------------------------------------------------

_BUILDERS = {
    QueryKind.a: build_kind_a,
    QueryKind.b: build_kind_b,
    QueryKind.c: build_kind_c,
    QueryKind.d: build_kind_d,
    QueryKind.e: lambda seed=RANDOM_SEED: [
        pair.as_record() for pair in comparability.build_query_set(comparability.load_rows(), seed)
    ],
}


def build(kind: QueryKind, seed: int = RANDOM_SEED) -> list[dict[str, str]]:
    return _BUILDERS[QueryKind(kind)](seed)


def write_query_set(kind: QueryKind, records: Sequence[Mapping[str, str]]) -> Path:
    target = KIND_PATHS[QueryKind(kind)]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES[QueryKind(kind)])
        writer.writeheader()
        writer.writerows(records)
    return target


def read_records(kind: QueryKind) -> list[dict[str, str]]:
    path = KIND_PATHS[QueryKind(kind)]
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_questions(kind: QueryKind) -> list[Question]:
    return [question_from_record(record) for record in read_records(kind)]


def read_answer_key(kind: QueryKind) -> list[AnswerKey]:
    return [answer_from_record(record) for record in read_records(kind)]


def counts() -> dict[str, int]:
    return {kind.value: len(read_records(kind)) for kind in QueryKind}


_WORD = re.compile(r"[a-z]+")


def question_terms(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(text.lower()))


#: Kind E is regenerated by `python -m mnp.eval.comparability`, which owns it.
GENERATED_HERE = (QueryKind.a, QueryKind.b, QueryKind.c, QueryKind.d)


if __name__ == "__main__":  # pragma: no cover - regeneration entry point
    for _kind in GENERATED_HERE:
        _written = write_query_set(_kind, build(_kind))
        print(f"wrote {_written} ({len(read_records(_kind))} questions)")
